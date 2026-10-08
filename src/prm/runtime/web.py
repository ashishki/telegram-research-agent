"""Concrete Brave discovery and exact-ref GitHub reads with current policy."""
from __future__ import annotations
import base64
import hashlib
import json
import re
from urllib.parse import urlencode,quote,urlsplit
from prm.capabilities import AuthorizationRequest,CapabilityDenied
from prm.contracts import PublicWebAccess
from prm.public_web import HttpPublicWebProvider,PublicWebBounds,PublicWebTransportError,_https_get,_validate_https_url
from prm.storage.postgres import StorageError


class BraveSearchProvider(HttpPublicWebProvider):
    def __init__(self,*,token):
        if not isinstance(token,str) or not token or '\r' in token or '\n' in token:
            raise StorageError('explicit search credential required')
        self._token=token
        super().__init__(search_endpoint='https://api.search.brave.com/res/v1/web/search')

    def search_public(self,query,*,bounds):
        url=self._search_endpoint+'?'+urlencode({'q':query,'count':bounds.max_search_results})
        response=_https_get(url,timeout_seconds=min(8,bounds.timeout_seconds),max_bytes=bounds.max_response_bytes,
                            headers={'X-Subscription-Token':self._token})
        if response['content_type']!='application/json':raise PublicWebTransportError('search_content_type')
        value=json.loads(response['body']);rows=value.get('web',{}).get('results',[])
        if not isinstance(rows,list):raise PublicWebTransportError('search_payload')
        return [{'source_url':row['url'],'title':row.get('title',''),'snippet':row.get('description',''),
                 'published_at':row.get('page_age')} for row in rows[:bounds.max_search_results] if isinstance(row,dict) and isinstance(row.get('url'),str)]


class AuthorizedPublicWeb:
    def __init__(self,provider,registry,access,*,guard=None):
        self.provider,self.registry,self.access,self.guard=provider,registry,access,guard
        self.fetch_index=0

    def _run(self,decision,call):
        def transport():
            if self.guard:self.guard()
            return call()
        return self.registry.execute_prepared(decision.reservation,transport)

    def search_public(self,query,*,bounds):
        return self._run(self.access.search_authorization,lambda:self.provider.search_public(query,bounds=bounds))

    def fetch_public(self,source_ref,*,bounds):
        parsed=_validate_https_url(source_ref)
        if parsed.hostname not in bounds.trusted_source_hosts:raise CapabilityDenied('document host outside selected primary sources')
        if self.fetch_index>=len(self.access.fetch_authorizations):raise CapabilityDenied('document call bound exhausted')
        decision=self.access.fetch_authorizations[self.fetch_index];self.fetch_index+=1
        return self._run(decision,lambda:self.provider.fetch_public(source_ref,bounds=bounds))


def reserve_public_access(root,query,*,request_ref,search_ref,fetch_ref,bounds,upper_bound):
    operation='public_'+hashlib.sha256(request_ref.encode()).hexdigest()[:32]
    def reserve(capability,purpose,resource,index):
        return root.registry.authorize_and_reserve(AuthorizationRequest(owner_ref=root.owner_ref,connection_ref=None,
            capability=capability,resource_ref=resource,operation='read',data_class='public',provider_ref='provider_public_web',
            purpose=purpose,operation_ref=operation+index),upper_bound=upper_bound)
    search=reserve('web.search','public.search',search_ref,'_search')
    decisions=[search]
    for index in range(bounds.max_fetches):decisions.append(reserve('web.fetch','public.fetch',fetch_ref,'_fetch_'+str(index)))
    if not all(decision.allowed for decision in decisions):
        for decision in decisions:
            if decision.reservation:decision.reservation.abandon_before_transport()
        return None
    digest='sha256:'+hashlib.sha256(' '.join(query.split()).encode()).hexdigest()
    return PublicWebAccess(search,tuple(decisions[1:]),root.owner_ref,None,search_ref,fetch_ref,digest)


class GitHubReadProvider:
    def __init__(self,*,registry,owner_ref,repository_ref,ref,upper_bound,paths=('README.md',),guard=None):
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}',repository_ref) or not ref or len(ref)>160:
            raise StorageError('exact public repository and requested ref required')
        if not 1<=len(paths)<=6 or any(not re.fullmatch(r'[A-Za-z0-9_./-]{1,200}',path) or '..' in path.split('/') for path in paths):
            raise StorageError('bounded repository path allowlist required')
        self.registry,self.owner_ref,self.repository_ref,self.ref,self.upper_bound=registry,owner_ref,repository_ref,ref,upper_bound
        self.paths,self.guard=tuple(paths),guard

    def read_repository_context(self,repository_ref):
        if repository_ref!=self.repository_ref:raise CapabilityDenied('repository selection differs')
        import uuid
        def read(path):
            decision=self.registry.authorize_and_reserve(AuthorizationRequest(owner_ref=self.owner_ref,connection_ref=None,
                capability='github.repository_context',resource_ref=repository_ref,operation='read',data_class='public',
                provider_ref='provider_github',purpose='project.context',operation_ref='github_'+uuid.uuid4().hex),upper_bound=self.upper_bound)
            if not decision.allowed:raise CapabilityDenied(decision.reason)
            def transport():
                if self.guard:self.guard()
                value=_https_get('https://api.github.com/repos/'+repository_ref+'/'+path,timeout_seconds=8,max_bytes=128000,
                    headers={'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2026-03-10'})
                if value['content_type']!='application/json':raise StorageError('GitHub JSON required')
                return json.loads(value['body'])
            return self.registry.execute_reserved((decision.reservation,),transport)
        commit=read('commits/'+quote(self.ref,safe=''))
        sha=commit.get('sha')
        if not isinstance(sha,str) or not re.fullmatch(r'[a-f0-9]{40}',sha):raise StorageError('observed commit SHA unavailable')
        items=[];gaps=[]
        for path in self.paths:
            try:
                document=read('contents/'+quote(path,safe='/')+'?'+urlencode({'ref':sha}))
                if (not isinstance(document,dict) or document.get('encoding')!='base64' or document.get('path')!=path
                    or type(document.get('size'))is not int or not 0<=document['size']<=128000
                    or not isinstance(document.get('sha'),str) or not re.fullmatch(r'[a-f0-9]{40}',document['sha'])):
                    raise StorageError('GitHub file scope or size differs')
                raw=base64.b64decode(document['content'],validate=False)
                if len(raw)>128000:raise StorageError('GitHub content exceeds bound')
                items.append({'path':path,'text':raw.decode('utf-8')[:12000],
                    'source_url':'https://github.com/'+repository_ref+'/blob/'+sha+'/'+path,'blob_sha':document.get('sha')})
            except (CapabilityDenied,StorageError):raise
            except Exception:gaps.append('unavailable:'+path)
        return {'repository_ref':repository_ref,'requested_ref':self.ref,'observed_ref':sha,'ref':sha,'items':items,'gaps':gaps,
                'status':'partial' if gaps else 'read','read_only':True}
