"""Exact-owner Graph OAuth/PKCE lifecycle; encrypted credentials outside Git."""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
from urllib.parse import urlsplit,urlencode
from urllib.request import Request,ProxyHandler,build_opener
from psycopg.types.json import Jsonb
from prm.storage.postgres import PostgresStore,StorageError,StateConflict
from prm.briefs import brief_owner_ref_from_authenticated_private_tuple
from prm.capabilities import CapabilityDenied
from .model import NoRedirect

DDL=(
    'CREATE SCHEMA pa_connections',
    'CREATE TABLE pa_connections.meta(version integer PRIMARY KEY,checksum text NOT NULL)',
    '''CREATE TABLE pa_connections.accounts(owner text NOT NULL,id text NOT NULL,account_ref text NOT NULL,
       scopes jsonb NOT NULL,revision bigint NOT NULL,status text NOT NULL,secret_ref text,expires timestamptz,
       PRIMARY KEY(owner,id))''',
    '''CREATE TABLE pa_connections.flows(owner text NOT NULL,state_digest text NOT NULL,connection_ref text NOT NULL,
       account_ref text NOT NULL,scopes jsonb NOT NULL,verifier_ref text NOT NULL,redirect text NOT NULL,
       expires timestamptz NOT NULL,expected_revision bigint NOT NULL,consumed boolean NOT NULL DEFAULT false,PRIMARY KEY(owner,state_digest))''',
    'GRANT USAGE ON SCHEMA pa_connections TO pa_test_app',
    'GRANT SELECT ON pa_connections.meta TO pa_test_app',
    'GRANT SELECT,INSERT,UPDATE ON pa_connections.accounts,pa_connections.flows TO pa_test_app',
)
CHECKSUM=hashlib.sha256('\n'.join(DDL).encode()).hexdigest()


def install_connections(target):
    if target.user!='pa_test_migrator':raise StorageError('dedicated synthetic migrator required')
    with PostgresStore(target).transaction() as tx:
        tx.conn.execute('SELECT pg_advisory_xact_lock(%s)',(87291016,))
        if tx.conn.execute("SELECT to_regclass('pa_connections.meta') AS meta").fetchone()['meta'] is None:
            for statement in DDL:tx.conn.execute(statement)
            tx.conn.execute('INSERT INTO pa_connections.meta VALUES(1,%s)',(CHECKSUM,))
        else:_check(tx.conn)


def _check(conn):
    if conn.execute('SELECT version,checksum FROM pa_connections.meta').fetchall()!=[{'version':1,'checksum':CHECKSUM}]:raise StorageError('connection schema differs')


class TokenVault:
    def __init__(self,*,directory,encryption_key):
        from cryptography.fernet import Fernet
        self._cipher=Fernet(encryption_key);self.path=Path(directory)
        if not self.path.is_absolute() or self.path.is_symlink():raise StorageError('explicit private credential directory required')
        self.path.mkdir(parents=True,exist_ok=True,mode=0o700);self.path=self.path.resolve();os.chmod(self.path,0o700)
    def put(self,value):
        data=json.dumps(value,ensure_ascii=False).encode()
        if len(data)>64000:raise StorageError('credential bundle exceeds bound')
        ref='sealed_'+secrets.token_hex(16);path=self.path/ref
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as output:output.write(self._cipher.encrypt(data));output.flush();os.fsync(output.fileno())
        return ref
    def get(self,ref):
        if not re.fullmatch(r'sealed_[a-f0-9]{32}',ref):raise StorageError('invalid credential reference')
        path=self.path/ref
        if path.is_symlink() or path.stat().st_mode&0o077 or path.stat().st_size>100000:raise StorageError('credential permissions or size differ')
        try:return json.loads(self._cipher.decrypt(path.read_bytes()))
        except Exception:raise StorageError('credential unavailable') from None
    def delete(self,ref):
        if not re.fullmatch(r'sealed_[a-f0-9]{32}',ref):raise StorageError('invalid credential reference')
        (self.path/ref).unlink(missing_ok=True)


class GraphOAuth:
    SCOPES=frozenset({'User.Read','offline_access','Mail.ReadBasic','Mail.Read','Mail.Send','Mail.ReadWrite','Calendars.Read','Calendars.ReadWrite','Contacts.Read'})
    def __init__(self,*,target,vault,client_id,tenant,redirect_uri,authority='https://login.microsoftonline.com',graph_origin='https://graph.microsoft.com',synthetic=False):
        if not re.fullmatch(r'[A-Za-z0-9-]{1,100}',tenant) or not client_id:raise StorageError('explicit client and tenant required')
        self.store=PostgresStore(target);self.vault=vault;self.client_id=client_id;self.tenant=tenant;self.redirect=redirect_uri
        self.authority=authority.rstrip('/');self.graph_origin=graph_origin.rstrip('/');self.synthetic=synthetic
        for url in (self.authority,self.graph_origin):
            parsed=urlsplit(url)
            if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {'','/'}:raise StorageError('fixed OAuth origin required')
            if synthetic:
                if parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or not parsed.port:raise StorageError('literal loopback synthetic OAuth origin required')
            elif url not in {'https://login.microsoftonline.com','https://graph.microsoft.com'}:raise StorageError('selected Graph origins required')
        parsed=urlsplit(redirect_uri)
        if parsed.username or parsed.fragment or parsed.query or not (parsed.scheme=='https' or (parsed.scheme=='http' and parsed.hostname in {'127.0.0.1','localhost'})):
            raise StorageError('exact secure or loopback OAuth redirect required')

    def _owner(self,chat_id,actor_id,owner_chat_id):
        owner=brief_owner_ref_from_authenticated_private_tuple(chat_id,actor_id,owner_chat_id)
        if owner is None:raise CapabilityDenied('private owner tuple required')
        return owner

    def _http(self,url,*,form=None,token=None):
        origin=self.authority if form is not None else self.graph_origin
        if not url.startswith(origin+'/'):raise StorageError('OAuth destination substituted')
        headers={'Accept':'application/json'}
        if token:
            if '\n' in token or '\r' in token:raise StorageError('invalid credential')
            headers['Authorization']='Bearer '+token
        data=None
        if form is not None:headers['Content-Type']='application/x-www-form-urlencoded';data=urlencode(form).encode()
        try:
            with build_opener(ProxyHandler({}),NoRedirect()).open(Request(url,data=data,headers=headers),timeout=8) as response:
                raw=response.read(128001)
                if len(raw)>128000 or response.headers.get_content_type()!='application/json':raise StorageError('OAuth response bound or type differs')
                return json.loads(raw)
        except Exception:raise StorageError('OAuth transport unavailable; no credential detail logged') from None

    def begin(self,*,connection_ref,account_ref,scopes,chat_id,actor_id,owner_chat_id):
        owner=self._owner(chat_id,actor_id,owner_chat_id)
        if not re.fullmatch(r'connection_[a-z0-9_-]{3,120}',connection_ref) or not account_ref or len(account_ref)>128:
            raise StorageError('bounded exact connection and account refs required')
        if not isinstance(scopes,tuple) or not scopes or not set(scopes)<=self.SCOPES or 'User.Read' not in scopes:
            raise StorageError('explicit selected Graph scopes required')
        state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(48);ref=self.vault.put({'verifier':verifier})
        digest=hashlib.sha256(state.encode()).hexdigest();challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        try:
            with self.store.transaction() as tx:
                _check(tx.conn);now=tx.conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
                tx.conn.execute('INSERT INTO pa_connections.accounts(owner,id,account_ref,scopes,revision,status) VALUES(%s,%s,%s,%s,1,%s) ON CONFLICT DO NOTHING',
                                (owner,connection_ref,account_ref,Jsonb(list(scopes)),'awaiting_handshake'))
                prior=tx.conn.execute('SELECT revision,account_ref FROM pa_connections.accounts WHERE owner=%s AND id=%s FOR UPDATE',(owner,connection_ref)).fetchone()
                if prior['account_ref']!=account_ref:raise CapabilityDenied('a new account requires a new connection identity')
                tx.conn.execute('INSERT INTO pa_connections.flows(owner,state_digest,connection_ref,account_ref,scopes,verifier_ref,redirect,expires,expected_revision) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (owner,digest,connection_ref,account_ref,Jsonb(list(scopes)),ref,self.redirect,now+timedelta(minutes=10),prior['revision']))
        except Exception:self.vault.delete(ref);raise
        return self.authority+'/'+self.tenant+'/oauth2/v2.0/authorize?'+urlencode({'client_id':self.client_id,'response_type':'code',
            'redirect_uri':self.redirect,'scope':' '.join(scopes),'state':state,'code_challenge':challenge,'code_challenge_method':'S256','response_mode':'query'})

    def _validate_bundle(self,value,scopes):
        if (not isinstance(value,dict) or not isinstance(value.get('access_token'),str) or not value['access_token']
            or value.get('token_type','').casefold()!='bearer' or type(value.get('expires_in'))is not int or not 1<=value['expires_in']<=86400):
            raise StorageError('OAuth handshake incomplete')
        actual=set(value.get('scope','').split())
        required=set(scopes)-{'offline_access'}
        if not required<=actual or not actual<=set(scopes):raise StorageError('provider token scope differs from exact selection')
        return value

    def callback(self,*,state,code,redirect_uri,chat_id,actor_id,owner_chat_id):
        owner=self._owner(chat_id,actor_id,owner_chat_id)
        if redirect_uri!=self.redirect or not isinstance(code,str) or not 0<len(code)<=4096 or not isinstance(state,str) or len(state)>200:
            raise CapabilityDenied('OAuth callback substitution denied')
        digest=hashlib.sha256(state.encode()).hexdigest()
        with self.store.transaction() as tx:
            _check(tx.conn)
            row=tx.conn.execute('SELECT * FROM pa_connections.flows WHERE owner=%s AND state_digest=%s FOR UPDATE',(owner,digest)).fetchone()
            now=tx.conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
            if not row or row['consumed'] or row['expires']<=now or row['redirect']!=self.redirect:raise CapabilityDenied('OAuth state unavailable')
            tx.conn.execute('UPDATE pa_connections.flows SET consumed=true WHERE owner=%s AND state_digest=%s',(owner,digest))
        # One-use state commits before potentially ambiguous token exchange.
        try:
            verifier=self.vault.get(row['verifier_ref'])['verifier']
            bundle=self._validate_bundle(self._http(self.authority+'/'+self.tenant+'/oauth2/v2.0/token',form={
                'client_id':self.client_id,'grant_type':'authorization_code','code':code,'redirect_uri':self.redirect,'code_verifier':verifier,'scope':' '.join(row['scopes'])}),row['scopes'])
            identity=self._http(self.graph_origin+'/v1.0/me?$select=id',token=bundle['access_token'])
            if identity.get('id')!=row['account_ref']:raise CapabilityDenied('authenticated Graph account differs from selected account')
            secret=self.vault.put(bundle)
            try:
                with self.store.transaction() as tx:
                    prior=tx.conn.execute('SELECT revision FROM pa_connections.accounts WHERE owner=%s AND id=%s FOR UPDATE',(owner,row['connection_ref'])).fetchone()
                    if prior is None or prior['revision']!=row['expected_revision']:raise CapabilityDenied('connection revoked or replaced during handshake')
                    tx.conn.execute('''INSERT INTO pa_connections.accounts VALUES(%s,%s,%s,%s,%s,'connected',%s,%s)
                        ON CONFLICT(owner,id) DO UPDATE SET account_ref=excluded.account_ref,scopes=excluded.scopes,revision=excluded.revision,
                        status='connected',secret_ref=excluded.secret_ref,expires=excluded.expires''',
                        (owner,row['connection_ref'],row['account_ref'],Jsonb(row['scopes']),prior['revision']+1 if prior else 1,secret,
                         datetime.now(timezone.utc)+timedelta(seconds=bundle['expires_in'])))
            except Exception:self.vault.delete(secret);raise
            return self.status(owner=owner,connection_ref=row['connection_ref'])
        finally:self.vault.delete(row['verifier_ref'])

    def credential(self,*,owner,connection_ref,account_ref):
        with self.store.transaction() as tx:
            _check(tx.conn)
            row=tx.conn.execute('SELECT * FROM pa_connections.accounts WHERE owner=%s AND id=%s FOR UPDATE',(owner,connection_ref)).fetchone()
            now=tx.conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
            if not row or row['status']!='connected' or row['account_ref']!=account_ref:raise CapabilityDenied('current connection unavailable')
            bundle=self.vault.get(row['secret_ref'])
            if row['expires']<=now+timedelta(seconds=30):
                if not bundle.get('refresh_token'):raise CapabilityDenied('interactive reconnect required')
                refreshed=self._validate_bundle(self._http(self.authority+'/'+self.tenant+'/oauth2/v2.0/token',form={'client_id':self.client_id,
                    'grant_type':'refresh_token','refresh_token':bundle['refresh_token'],'scope':' '.join(row['scopes'])}),row['scopes'])
                if 'refresh_token' not in refreshed:refreshed['refresh_token']=bundle['refresh_token']
                secret=self.vault.put(refreshed)
                tx.conn.execute('UPDATE pa_connections.accounts SET secret_ref=%s,expires=%s WHERE owner=%s AND id=%s',
                    (secret,now+timedelta(seconds=refreshed['expires_in']),owner,connection_ref))
                bundle=refreshed
            return bundle['access_token']

    def revoke(self,*,connection_ref,chat_id,actor_id,owner_chat_id):
        owner=self._owner(chat_id,actor_id,owner_chat_id)
        with self.store.transaction() as tx:
            row=tx.conn.execute('SELECT secret_ref FROM pa_connections.accounts WHERE owner=%s AND id=%s FOR UPDATE',(owner,connection_ref)).fetchone()
            tx.conn.execute('UPDATE pa_connections.accounts SET status=%s,revision=revision+1,secret_ref=NULL WHERE owner=%s AND id=%s',
                            ('disconnected',owner,connection_ref))
            tx.conn.execute('UPDATE pa_connections.flows SET consumed=true WHERE owner=%s AND connection_ref=%s',(owner,connection_ref))
        if row and row['secret_ref']:self.vault.delete(row['secret_ref'])
        # Provider-wide token restriction is not claimed by local disconnect.
        return {'status':'disconnected','provider_token_revocation':'operator_or_provider_required'}

    def status(self,*,owner,connection_ref):
        with self.store.transaction() as tx:
            _check(tx.conn)
            row=tx.conn.execute('SELECT account_ref,scopes,revision,status,expires FROM pa_connections.accounts WHERE owner=%s AND id=%s',(owner,connection_ref)).fetchone()
            return row or {'status':'not_connected'}
