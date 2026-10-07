"""Loopback authenticated report endpoint and private artifact lifecycle."""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile

from prm.briefs import _storage_document,brief_owner_ref_from_authenticated_private_tuple
from prm.storage.postgres import StorageError


class PrivateReportRuntime:
    def __init__(self,root,*,artifact_root):
        self.root=root;self.path=Path(artifact_root)
        if not self.path.is_absolute() or self.path.is_symlink():raise StorageError('explicit private artifact directory required')
        self.path.mkdir(parents=True,exist_ok=True,mode=0o700);self.path=self.path.resolve();os.chmod(self.path,0o700)
        self.sessions={}

    def issue_session(self,*,chat_id,actor_id,owner_chat_id,ttl_seconds=300):
        owner=brief_owner_ref_from_authenticated_private_tuple(chat_id,actor_id,owner_chat_id)
        if owner!=self.root.owner_ref or not 1<=ttl_seconds<=3600:raise StorageError('private owner session required')
        now=datetime.now(timezone.utc)
        self.sessions={key:value for key,value in self.sessions.items() if value[1]>now}
        if len(self.sessions)>=64:raise StorageError('reader session capacity reached')
        token=secrets.token_urlsafe(32);digest=hashlib.sha256(token.encode()).hexdigest()
        self.sessions[digest]=(owner,now+timedelta(seconds=ttl_seconds));return token

    def revoke(self,token):self.sessions.pop(hashlib.sha256(token.encode()).hexdigest(),None)

    def artifact(self,token,*,brief_id,version,format):
        if format not in {'html','markdown','pdf'}:raise StorageError('unsupported report format')
        digest=hashlib.sha256(token.encode()).hexdigest();session=self.sessions.get(digest)
        if session is None or session[0]!=self.root.owner_ref or session[1]<=datetime.now(timezone.utc):return None
        document=self.root.briefs.get_persisted_document(authenticated_chat_id=self.root.owner_chat_id,
            authenticated_actor_id=self.root.owner_chat_id,authenticated_owner_chat_id=self.root.owner_chat_id,brief_id=brief_id,version=version)
        if document is None:return None
        key=hashlib.sha256((self.root.owner_ref+document.content_digest+format).encode()).hexdigest()
        path=self.path/(key+'.'+format)
        if not path.exists():
            with tempfile.TemporaryDirectory(prefix='pa-render-',dir=self.path) as temp:
                source=Path(temp)/'input.json';out=Path(temp)/'output'
                source.write_text(json.dumps(_storage_document(document),ensure_ascii=False));os.chmod(source,0o600)
                env={'PATH':os.environ.get('PATH','/usr/bin:/bin'),'LANG':'C.UTF-8',
                     'PYTHONPATH':str(Path(__file__).resolve().parents[2])}
                try:
                    subprocess.run([sys.executable,'-m','prm.runtime.render','--input',str(source),'--output',str(out),'--format',format],
                        env=env,cwd=temp,check=True,timeout=18,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                except Exception:raise StorageError('isolated report rendering unavailable') from None
                os.chmod(out,0o600);os.replace(out,path)
        if path.is_symlink() or path.stat().st_size>16000000:raise StorageError('invalid stored artifact')
        return path.read_bytes(),{'html':'text/html; charset=utf-8','markdown':'text/markdown; charset=utf-8','pdf':'application/pdf'}[format]

    def server(self,*,port=0):
        runtime=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                pieces=self.path.split('/')
                if len(pieces)!=5 or pieces[1]!='report':self.send_error(404);return
                token=self.headers.get('Authorization','')
                if not token.startswith('Bearer '):self.send_error(401);return
                try:
                    if not pieces[3].isdigit():raise ValueError('invalid version')
                    result=runtime.artifact(token[7:],brief_id=pieces[2],version=int(pieces[3]),format=pieces[4])
                except Exception:self.send_error(404);return
                if result is None:self.send_error(404);return
                body,content_type=result
                self.send_response(200);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(body)))
                self.send_header('Cache-Control','no-store');self.send_header('X-Robots-Tag','noindex, nofollow, noarchive')
                self.send_header('Referrer-Policy','no-referrer');self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; img-src data:; frame-ancestors 'none'")
                self.end_headers();self.wfile.write(body)
        return ThreadingHTTPServer(('127.0.0.1',port),Handler)
