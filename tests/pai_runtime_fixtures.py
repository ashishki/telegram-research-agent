"""Deferred full-runtime fixtures. No server/database starts at import time."""
from datetime import datetime,timedelta,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace
from urllib.parse import urlsplit,parse_qs
import json
import pytest

from prm.briefs import brief_owner_ref_from_authenticated_private_tuple
from prm.capabilities import CapabilityGrant,ProviderPolicy
from prm.storage.testing import PostgresSandbox
from prm.storage.policy import DurableCapabilityRegistry
from prm.runtime.setup import install_runtime
from prm.runtime.operations import OperationsRuntime
from prm.runtime.composition import AssistantRuntime
from prm.runtime.model import ModelEndpoint


@pytest.fixture
def pai(tmp_path):
    requests=[];moment=datetime.now(timezone.utc)
    class Provider(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,value,status=200):
            raw=json.dumps(value).encode();self.send_response(status);self.send_header('Content-Type','application/json')
            self.send_header('request-id','synthetic_provider_request');self.end_headers();self.wfile.write(raw)
        def do_POST(self):
            raw=self.rfile.read(int(self.headers.get('Content-Length',0)))
            if self.path.endswith('/token'):
                form=parse_qs(raw.decode());requests.append(('oauth',self.path,form))
                scopes=form.get('scope',['User.Read'])[0].replace('offline_access','').strip()
                self.reply({'access_token':'synthetic_access_fixture','refresh_token':'synthetic_refresh_fixture','token_type':'Bearer','expires_in':3600,'scope':scopes});return
            if self.path=='/chat/completions':
                body=json.loads(raw);requests.append(('model',self.path,body));text='Синтетический ответ на текущий вопрос.'
                for message in body['messages']:
                    value=message.get('content')
                    if isinstance(value,str) and value.startswith('Untrusted cited archive evidence: '):
                        evidence=json.loads(value.split(': ',1)[1]);text=evidence[0]['text']+' ('+evidence[0]['source_ref']+').' if evidence else text
                    if isinstance(value,str) and value.startswith('Untrusted verified reads: '):
                        evidence=json.loads(value.split(': ',1)[1]);text=evidence[0]['support_span']+' ('+evidence[0]['source_url']+').' if evidence else text
                self.reply({'model':'fixture_model','choices':[{'finish_reason':'stop','message':{'content':text}}],
                    'usage':{'prompt_tokens':40,'completion_tokens':12,'prompt_tokens_details':{'cached_tokens':10},'completion_tokens_details':{'reasoning_tokens':4}}});return
            if self.path.startswith('/v1.0/me/'):
                body=json.loads(raw) if raw else {};requests.append(('write',self.path,body))
                self.reply({'id':'synthetic_event_created','changeKey':'version_1'},201 if self.path.endswith('/events') else 202);return
            self.reply({'error':'unsupported'},404)
        def do_GET(self):
            requests.append(('read',self.path,{}));parsed=urlsplit(self.path);query=parse_qs(parsed.query)
            if parsed.path=='/v1.0/me':self.reply({'id':'account_synthetic'});return
            if '/messages/delta' in parsed.path or parsed.path.endswith('/messages'):
                page=query.get('$skiptoken',['1'])[0]
                message={'id':'message_'+page,'subject':'Selected message '+page,'from':{'emailAddress':{'address':'sender@example.test'}},
                    'receivedDateTime':moment.isoformat(),'conversationId':'conversation_synthetic','parentFolderId':'inbox','webLink':'https://outlook.example.test/mail/'+page}
                key='@odata.nextLink' if page=='1' else '@odata.deltaLink';token='2' if page=='1' else 'last'
                self.reply({'value':[message],key:f'http://127.0.0.1:{self.server.server_port}'+parsed.path+'?'+('$skiptoken=' if page=='1' else '$deltatoken=')+token});return
            if parsed.path.endswith('/calendarView'):
                def event(key,start,end):return {'id':key,'subject':key,'start':{'dateTime':start.isoformat(),'timeZone':'UTC'},
                    'end':{'dateTime':end.isoformat(),'timeZone':'UTC'},'changeKey':'etag_1','webLink':'https://outlook.example.test/calendar/'+key,'type':'singleInstance'}
                self.reply({'value':[event('event_a',moment+timedelta(hours=1),moment+timedelta(hours=2)),event('event_b',moment+timedelta(minutes=90),moment+timedelta(hours=3))]});return
            if parsed.path.endswith('/contacts'):
                self.reply({'value':[{'id':'contact_a','displayName':'Alex','emailAddresses':[{'address':'alex.a@example.test'}]},
                                     {'id':'contact_b','displayName':'Alex','emailAddresses':[{'address':'alex.b@example.test'}]}]});return
            self.reply({'error':'unsupported'},404)
    server=ThreadingHTTPServer(('127.0.0.1',0),Provider);thread=Thread(target=server.serve_forever);thread.start()
    try:
        with PostgresSandbox() as pg:
            install_runtime(pg.migrator,expected_base_version=0)
            owner=brief_owner_ref_from_authenticated_private_tuple('42','42','42');refs=('request_full','job_full','day_full','month_full')
            registry=DurableCapabilityRegistry(pg.app,budget_refs=refs,job_budget=True)
            for kind,ref in zip(('request','job','day','month'),refs):registry.configure_window(owner=owner,ref=ref,kind=kind,capacity=10000,starts=moment-timedelta(days=1),ends=moment+timedelta(days=1))
            root=AssistantRuntime(target=pg.app,settings=SimpleNamespace(db_path=':memory:'),owner_ref=owner,owner_chat_id='42',registry=registry,
                model_endpoint=ModelEndpoint('provider_openai','connection_fixture',f'http://127.0.0.1:{server.server_port}/chat/completions','fixture_model','',synthetic_http=True),
                model_upper_bound=1,history_retention_seconds=3600)
            ops=OperationsRuntime(pg.app);state=ops.status();ops.permit_synthetic_egress(expected_epoch=state['execution']['epoch'],operator_request_ref='synthetic_operator_fixture')
            yield SimpleNamespace(root=root,pg=pg,requests=requests,origin=f'http://127.0.0.1:{server.server_port}',now=moment,path=tmp_path,ops=ops)
    finally:server.shutdown();thread.join(timeout=5);server.server_close()


def allow(pai,capability,resource,data_class,purpose,*,provider='provider_openai',connection='connection_fixture',operation='model_egress',identifier=None):
    import uuid
    grant=CapabilityGrant(identifier or 'grant_'+uuid.uuid4().hex,pai.root.owner_ref,connection,capability,(resource,),(operation,),(data_class,),purpose,
        ProviderPolicy((provider,),maximum_request_count=1000),pai.now-timedelta(days=1),pai.now+timedelta(days=1),1)
    pai.root.registry.register_grant(grant);return grant


def request(pai,index,text):
    ack=pai.root.ingress.receive({'update_id':index,'message':{'chat':{'id':42,'type':'private'},'from':{'id':42},'text':text}})
    ref=pai.root.worker().run_once()
    return ack,pai.root.queue.store.get(pai.root.owner_ref,'result',ref).payload


def graph(pai):
    from cryptography.fernet import Fernet
    from prm.runtime.connections import TokenVault,GraphOAuth
    from prm.runtime.graph import GraphTransport
    vault=TokenVault(directory=pai.path/'vault',encryption_key=Fernet.generate_key())
    manager=GraphOAuth(target=pai.pg.app,vault=vault,client_id='synthetic_client',tenant='synthetic',redirect_uri='http://127.0.0.1/callback',
        authority=pai.origin,graph_origin=pai.origin,synthetic=True)
    actor={'chat_id':'42','actor_id':'42','owner_chat_id':'42'}
    url=manager.begin(connection_ref='connection_graph_fixture',account_ref='account_synthetic',scopes=('User.Read','offline_access','Mail.ReadBasic','Calendars.Read','Contacts.Read','Mail.Send','Calendars.ReadWrite'),**actor)
    state=parse_qs(urlsplit(url).query)['state'][0]
    manager.callback(state=state,code='synthetic_code',redirect_uri='http://127.0.0.1/callback',**actor)
    return manager,GraphTransport(registry=pai.root.registry,connections=manager,owner_ref=pai.root.owner_ref,
        connection_ref='connection_graph_fixture',account_ref='account_synthetic',upper_bound=0),actor
