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
import re

from prm.briefs import _storage_document,brief_owner_ref_from_authenticated_private_tuple
from prm.storage.postgres import StorageError


class PrivateReportRuntime:
    def __init__(self,root,*,artifact_root):
        self.root=root;self.path=Path(artifact_root)
        if not self.path.is_absolute() or self.path.is_symlink():raise StorageError('explicit private artifact directory required')
        self.path.mkdir(parents=True,exist_ok=True,mode=0o700);self.path=self.path.resolve();os.chmod(self.path,0o700)
        self.sessions={}
        self.root_digest=hashlib.sha256(str(self.path).encode()).hexdigest()

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
        from prm.capabilities import AuthorizationRequest
        for scope in self.root.briefs.source_scopes(brief_id,version):
            request=AuthorizationRequest(**scope)
            if not self.root.registry.authorize(request).allowed:return None
            if request.provider_ref=='provider_microsoft_graph' and request.connection_ref:
                with self.root.queue.store.transaction() as tx:
                    account=tx.conn.execute('SELECT status FROM pa_connections.accounts WHERE owner=%s AND id=%s',
                        (self.root.owner_ref,request.connection_ref)).fetchone()
                    if not account or account['status']!='connected':return None
        key=hashlib.sha256(('\x1f'.join((self.root.owner_ref,document.brief_id,str(document.version),document.content_digest,format))).encode()).hexdigest()
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
                os.chmod(out,0o600)
                from .deletion import lineage_lock
                try:
                    with self.root.queue.store.transaction() as tx:
                        lineage_lock(tx.conn,self.root.owner_ref)
                        parent_ref=self.root.briefs._document_ref(document.brief_id)
                        if tx.get(self.root.owner_ref,'result',parent_ref,version=document.version) is None:
                            raise StorageError('report deleted while rendering')
                        indexed=tx.conn.execute('''INSERT INTO pa_artifacts.files(owner,key,parent_namespace,parent_ref,root_digest,content_digest)
                            VALUES(%s,%s,'result',%s,%s,%s) ON CONFLICT(owner,key) DO UPDATE SET
                            parent_namespace=excluded.parent_namespace,parent_ref=excluded.parent_ref,root_digest=excluded.root_digest,
                            content_digest=excluded.content_digest WHERE NOT pa_artifacts.files.deleted RETURNING key''',
                            (self.root.owner_ref,path.name,parent_ref,self.root_digest,document.content_digest)).fetchone()
                        if indexed is None:raise StorageError('deleted artifact cannot be restored')
                        os.replace(out,path)
                except Exception:
                    path.unlink(missing_ok=True)
                    raise
        from .deletion import lineage_lock
        with self.root.queue.store.transaction() as tx:
            lineage_lock(tx.conn,self.root.owner_ref)
            parent_ref=self.root.briefs._document_ref(document.brief_id)
            indexed=tx.conn.execute('SELECT deleted,root_digest FROM pa_artifacts.files WHERE owner=%s AND key=%s',
                (self.root.owner_ref,path.name)).fetchone()
            if tx.get(self.root.owner_ref,'result',parent_ref,version=document.version) is None or not indexed or indexed['deleted'] or indexed['root_digest']!=self.root_digest:
                return None
            if path.is_symlink() or path.stat().st_size>16000000:raise StorageError('invalid stored artifact')
            body=path.read_bytes()
        return body,{'html':'text/html; charset=utf-8','markdown':'text/markdown; charset=utf-8','pdf':'application/pdf'}[format]

    def cleanup_deleted(self):
        with self.root.queue.store.transaction() as tx:
            rows=tx.conn.execute('SELECT key FROM pa_artifacts.files WHERE owner=%s AND root_digest=%s AND deleted AND cleanup_pending ORDER BY key',
                (self.root.owner_ref,self.root_digest)).fetchall()
        removed=0
        for row in rows:
            key=row['key']
            if not re.fullmatch(r'[a-f0-9]{64}\.(?:html|markdown|pdf)',key):raise StorageError('invalid private artifact key')
            path=self.path/key
            if path.is_symlink():raise StorageError('private artifact cleanup refuses a substituted path')
            path.unlink(missing_ok=True)
            with self.root.queue.store.transaction() as tx:
                tx.conn.execute('UPDATE pa_artifacts.files SET cleanup_pending=false WHERE owner=%s AND key=%s AND deleted',(self.root.owner_ref,key))
            removed+=1
        return removed

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
