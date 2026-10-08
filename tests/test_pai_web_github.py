"""Deferred concrete provider schema/ref and scope tests."""
import json
import pytest
from tests.pai_runtime_fixtures import pai,allow
from prm.runtime.web import BraveSearchProvider,GitHubReadProvider
from prm.public_web import PublicWebBounds
from prm.capabilities import CapabilityDenied


def test_brave_discovery_is_distinct_from_document_read(monkeypatch):
    from prm.runtime import web
    calls=[]
    def http(url,**kwargs):
        calls.append((url,kwargs));return {'content_type':'application/json','body':json.dumps({'web':{'results':[{'url':'https://example.test/source','title':'Source','description':'Discovery only'}]}}).encode()}
    monkeypatch.setattr(web,'_https_get',http)
    provider=BraveSearchProvider(token='synthetic_search_credential')
    hits=provider.search_public('explicit public query',bounds=PublicWebBounds(('example.test',)))
    assert len(calls)==1 and hits[0]['snippet']=='Discovery only'
    assert '/web/search?' in calls[0][0] and 'q=explicit+public+query' in calls[0][0]


def test_github_ref_and_paths_are_exact_and_revocation_denies(pai,monkeypatch):
    from prm.runtime import web
    import base64
    grant=allow(pai,'github.repository_context','owner/repository','public','project.context',provider='provider_github',connection=None,operation='read')
    sha='a'*40;calls=[]
    def http(url,**kwargs):
        calls.append(url)
        value={'sha':sha} if '/commits/' in url else {'path':'README.md','size':10,'encoding':'base64','content':base64.b64encode(b'Fixture ref content').decode(),'sha':'b'*40}
        return {'content_type':'application/json','body':json.dumps(value).encode()}
    monkeypatch.setattr(web,'_https_get',http)
    provider=GitHubReadProvider(registry=pai.root.registry,owner_ref=pai.root.owner_ref,repository_ref='owner/repository',ref='main',upper_bound=0)
    result=provider.read_repository_context('owner/repository')
    assert result['observed_ref']==sha and 'ref='+sha in calls[1]
    pai.root.registry.revoke_grant(grant.grant_id,owner_ref=pai.root.owner_ref)
    count=len(calls)
    with pytest.raises(CapabilityDenied):provider.read_repository_context('owner/repository')
    assert len(calls)==count


def test_github_revocation_between_commit_and_content_is_not_hidden_as_partial(pai,monkeypatch):
    from prm.runtime import web
    grant=allow(pai,'github.repository_context','owner/repository','public','project.context',provider='provider_github',connection=None,operation='read')
    calls=[]
    def http(url,**kwargs):
        calls.append(url)
        return {'content_type':'application/json','body':json.dumps({'sha':'a'*40}).encode()}
    monkeypatch.setattr(web,'_https_get',http)
    original=pai.root.registry.execute_reserved
    def revoke_after_read(*args,**kwargs):
        result=original(*args,**kwargs)
        pai.root.registry.revoke_grant(grant.grant_id,owner_ref=pai.root.owner_ref)
        return result
    monkeypatch.setattr(pai.root.registry,'execute_reserved',revoke_after_read)
    provider=GitHubReadProvider(registry=pai.root.registry,owner_ref=pai.root.owner_ref,repository_ref='owner/repository',ref='main',upper_bound=0)
    with pytest.raises(CapabilityDenied):provider.read_repository_context('owner/repository')
    assert len(calls)==1


@pytest.mark.parametrize('changed',[{'size':None},{'size':True},{'size':128001},{'sha':'invalid'}])
def test_github_invalid_file_identity_metadata_is_rejected(pai,monkeypatch,changed):
    from prm.runtime import web
    from prm.storage.postgres import StorageError
    allow(pai,'github.repository_context','owner/repository','public','project.context',provider='provider_github',connection=None,operation='read')
    def http(url,**kwargs):
        value={'sha':'a'*40} if '/commits/' in url else {'path':'README.md','size':0,'encoding':'base64','content':'','sha':'b'*40,**changed}
        return {'content_type':'application/json','body':json.dumps(value).encode()}
    monkeypatch.setattr(web,'_https_get',http)
    provider=GitHubReadProvider(registry=pai.root.registry,owner_ref=pai.root.owner_ref,repository_ref='owner/repository',ref='main',upper_bound=0)
    with pytest.raises(StorageError,match='scope or size'):provider.read_repository_context('owner/repository')
