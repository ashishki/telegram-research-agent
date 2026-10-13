"""Native ordinary questions -> bounded public discovery/read; no live access."""
from datetime import timedelta
import pytest,json
from tests.pai_runtime_fixtures import pai,allow,request
from tests.test_daily_conversation import plan,FakePlanner
from prm.public_web import PublicWebBounds
from prm.runtime.research import DurableResearchWorker
from prm.runtime.web import project_public_query


class Provider:
    def __init__(self,pai,*,date=None,final_url=None):self.pai=pai;self.date=date or pai.now.isoformat();self.final_url=final_url;self.calls=[]
    def search_public(self,query,*,bounds):
        self.calls.append(('search',query,bounds.max_fetches))
        return [{'source_url':'https://official.example.test/alpha','snippet':'STALE DISCOVERY CANARY price999','published_at':'malformed'}]
    def fetch_public(self,url,*,bounds):
        self.calls.append(('fetch',url));return {'status':200,'final_url':self.final_url or url,'headers':{'content-type':'text/plain'},
            'body':b'Service Alpha price is 20 dollars.','published_at':self.date}


def configure(pai,monkeypatch,**changes):
    import prm.public_web as public
    monkeypatch.setattr(public,'_reject_private_resolution',lambda host:None)
    root=pai.root;provider=Provider(pai,**changes);root.public_web_provider=provider;root.public_web_bounds=PublicWebBounds(('official.example.test',),max_fetches=3);root.public_upper_bound=0
    root.intent_planner=FakePlanner(plan(intent='web_search',steps=[{'tool':'web.search','argument':'Service Alpha'}],source_filters=['public'],max_tool_calls=3))
    return provider


def grants(pai):
    for cap,ref,purpose in [('web.search',pai.root.public_search_ref,'public.search'),('web.fetch',pai.root.public_fetch_ref,'public.fetch')]:
        allow(pai,cap,ref,'public',purpose,provider='provider_public_web',connection=None,operation='read')


def test_plain_current_question_uses_native_public_plan_without_private_history(pai,monkeypatch):
    provider=configure(pai,monkeypatch);grants(pai)
    state=pai.root.conversations.record_response('42',text='PRIVATE REMEMBERED CANARY',topic='private')
    pai.root.conversations.record_origin(state.object_refs[0].response_ref,('private_connector_content',))
    _,ack=request(pai,123000,'Сколько стоит Service Alpha?')
    assert ack['status']=='queued'
    ref=DurableResearchWorker(pai.root).run_once();result=pai.root.queue.store.get(pai.root.owner_ref,'result',ref).payload
    assert provider.calls[0]==('search','Service Alpha',2) and len(provider.calls)==2
    assert '20 dollars' in result['text'] and '999' not in result['text']
    assert 'PRIVATE REMEMBERED CANARY' not in json.dumps(provider.calls)
    assert result['answer_payload']['source_coverage']['selected_count']==1 and result['data_classes']==['public']


@pytest.mark.parametrize('date',['malformed','1999-01-01T00:00:00Z','2999-01-01T00:00:00Z'])
def test_unknown_stale_or_future_publication_never_establishes_current_fact(pai,monkeypatch,date):
    provider=configure(pai,monkeypatch,date=date);grants(pai)
    request(pai,123010,'Сколько стоит Service Alpha?')
    ref=DurableResearchWorker(pai.root).run_once();result=pai.root.queue.store.get(pai.root.owner_ref,'result',ref).payload
    assert '20 dollars' not in result['text'] and result['answer_payload']['status']=='insufficient_evidence'
    assert result['answer_payload']['source_coverage']['projection_rejected_count']==1 and not pai.requests


def test_missing_permission_redirect_and_private_query_do_not_leak(pai,monkeypatch):
    provider=configure(pai,monkeypatch)
    request(pai,123020,'Сколько стоит Service Alpha?')
    ref=DurableResearchWorker(pai.root).run_once();assert not provider.calls
    grants(pai);provider.final_url='https://official.example.test/other'
    request(pai,123021,'Сколько стоит Service Alpha?')
    ref=DurableResearchWorker(pai.root).run_once();result=pai.root.queue.store.get(pai.root.owner_ref,'result',ref).payload
    assert result['answer_payload']['status']=='insufficient_evidence'
    provider.calls.clear()
    _,answer=request(pai,123022,'Проверь Service Alpha для моего проекта PRIVATE PROJECT CANARY')
    assert answer['status']=='clarify' and not provider.calls


def test_public_projection_cannot_add_context_or_copy_private_owner_markers():
    assert project_public_query('Сколько стоит Service Alpha?','Service Alpha')=='Service Alpha'
    for text,query in [('Сколько стоит Service Alpha?','Service Alpha SECRET'),('мой проект PRIVATE CANARY','PRIVATE CANARY'),('my mail owner@example.test','owner@example.test')]:
        assert project_public_query(text,query) is None

@pytest.mark.parametrize('text,query',[
    ('What does my email say about Service Alpha renewal for PRIVATE_CANARY?','PRIVATE_CANARY'),
    ('Проверь новости о ProjectSecret из моей почты','ProjectSecret'),
    pytest.param('Проверь новости о ProjectSecret из своей почты','ProjectSecret',id='reflexive_source'),
    pytest.param('Проверь новости о ProjectSecret по нашим сообщениям','ProjectSecret',id='collective_source'),
    pytest.param('What does the email I received say about PRIVATE_CANARY?','PRIVATE_CANARY',id='received_source'),
])
def test_natural_private_source_forms_do_not_queue_public_discovery(pai,monkeypatch,text,query):
    provider=configure(pai,monkeypatch);grants(pai)
    pai.root.intent_planner=FakePlanner(plan(intent='web_search',steps=[{'tool':'web.search','argument':query}],source_filters=['public'],max_tool_calls=3))
    _,answer=request(pai,123100,text)
    assert answer['status']=='clarify' and not provider.calls
    assert DurableResearchWorker(pai.root).run_once() is None and not pai.requests

def test_http_last_modified_remains_modification_not_publication(monkeypatch):
    import prm.public_web as public
    from datetime import datetime,timezone
    now=datetime.now(timezone.utc).isoformat();url='https://official.example.test/alpha'
    monkeypatch.setattr(public,'_https_get',lambda *args,**kwargs:{'status':200,'final_url':url,'headers':{'content-type':'text/plain','last-modified':now},'body':b'Service Alpha price is 20 dollars.'})
    monkeypatch.setattr(public,'_reject_private_resolution',lambda host:None)
    provider=public.HttpPublicWebProvider(search_endpoint='https://search.example.test/query')
    result=public._fetch_candidate(provider,{'source_url':url},bounds=PublicWebBounds(('official.example.test',)))
    assert result['publication_time'] is None and result['published_at'] is None
    assert result['modified_time'] and result['freshness_basis']=='modification'

@pytest.mark.parametrize('text,query',[
    ('Проверь новости о ProjectSecret из своей почты','ProjectSecret'),
    ('Проверь новости о ProjectSecret по нашим сообщениям','ProjectSecret'),
    ('What does the email I received say about PRIVATE_CANARY?','PRIVATE_CANARY'),
])
def test_automatic_public_projection_requires_question_without_private_source_cues(text,query):
    assert project_public_query(text,query) is None
