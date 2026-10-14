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


def project_public_query(owner_text,proposed):
    """A model may project this question, never add remembered/private words."""
    from prm.public_web import _validate_public_query,_PRIVATE_QUERY_MARKERS
    if not isinstance(owner_text,str) or not isinstance(proposed,str):return None
    import unicodedata
    def normalize(value):return ' '.join(''.join(c for c in unicodedata.normalize('NFKC',value) if unicodedata.category(c)!='Cf').split())
    original=normalize(owner_text);query=normalize(proposed)
    # A standalone public formulation must carry no ownership/private-source
    # references. Reject whole questions conservatively, never try to redact
    # a secret substring that a model labelled public.
    possessive=r'\b(?:my|mine|our|ours|private|personal|мой|моя|моё|мое|мои|моего|моей|мою|моему|моем|моём|моим|моими|моих|наш|наша|наши|нашего|нашей|наших)\b'
    # Source-type wording itself may refer to private data even without an
    # explicit possessive ("the email I received"). Automatic projection is
    # deliberately unavailable for such questions; owner supplies a separate
    # standalone public formulation. This is not semantic declassification.
    private_source=r'\b(?:e[\s-]?mails?|mail(?:boxes|box|s)?|inbox(?:es)?|calendars?|diar(?:y|ies)|notes?|messages?|letters?|chats?|sms|dms|archives?|profiles?|projects?|почт\w*|пис(?:ьм|ем)\w*|календар\w*|дневник\w*|заметк\w*|сообщен\w*|переписк\w*|архив\w*|профил\w*|проект\w*)\b'
    reflexive=r'\b(?:сво(?:й|я|ё|е|и|его|ей|ю|ему|ем|ём|им|ими|их)|наш\w*)\b'
    personal_context=r'\b(?:i|we|me|us|я|мы|мне|меня|нам|нас|received|saved|forwarded|got|manage|получ\w*|отправлен\w*|сохран[её]н\w*|личн\w*)\b'
    source_reference=r'\b(?:from|in|inside|из|в|по)\s+(?:(?:the|an|a|этой|этом|этих)\s+)?(?:email|e-mail|inbox|mailbox|mail|calendar|notes?|messages?|archive|profile|почт\w*|письм\w*|календар\w*|заметк\w*|сообщени\w*|архив\w*|профил\w*)\b'
    if any(re.search(pattern,original,re.I) for pattern in (possessive,reflexive,private_source,source_reference,personal_context)):return None
    private=(*_PRIVATE_QUERY_MARKERS,'мой проект','моего проекта','для моего','my project','my mail','моя почта','мои письма','my calendar','мой календарь')
    if any(marker in original.casefold() for marker in private) or re.search(r'(?i)\b(?:token|password|секрет|пароль)\b|[\w.+-]+@[\w.-]+\.[a-z]{2,}',original):return None
    if not query or query not in original or _validate_public_query(query,original_query=original)!='accepted':return None
    return query


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
    def __init__(self,*,registry,owner_ref,repository_ref,ref,upper_bound,paths=('README.md',),guard=None,
                 issues=(),pulls=(),releases=(),credential=None,connection_ref=None,connection_revision=None,cache=None):
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}',repository_ref) or not ref or len(ref)>160:
            raise StorageError('exact public repository and requested ref required')
        if not 1<=len(paths)<=6 or any(not safe_repository_path(path) for path in paths) or len(set(paths))!=len(paths):
            raise StorageError('bounded repository path allowlist required')
        if any(not isinstance(ids,(tuple,list)) or len(ids)>3 or len(set(ids))!=len(ids) or any(type(i)is not int or not 1<=i<=1000000000 for i in ids) for ids in (issues,pulls,releases)) or len(paths)+len(issues)+len(pulls)+len(releases)>9:
            raise StorageError('bounded exact GitHub object selection required')
        if (credential is None)!=(connection_ref is None) or credential is not None and (type(connection_revision)is not int or connection_revision<1):
            raise StorageError('selected private connection revision required')
        self.registry,self.owner_ref,self.repository_ref,self.ref,self.upper_bound=registry,owner_ref,repository_ref,ref,upper_bound
        self.paths,self.guard=tuple(paths),guard
        self.issues,self.pulls,self.releases=tuple(issues),tuple(pulls),tuple(releases)
        self.credential,self.connection_ref,self.connection_revision,self.cache=credential,connection_ref,connection_revision,cache
        self.data_class='private_connector_content' if credential else 'public'

    @property
    def maximum_calls(self):return 1+len(self.paths)+len(self.issues)+len(self.pulls)+len(self.releases)

    @property
    def selection(self):
        return [self.repository_ref,self.ref,self.paths,self.issues,self.pulls,self.releases,self.connection_ref,self.connection_revision,self.data_class]

    def source_request(self):
        return AuthorizationRequest(owner_ref=self.owner_ref,connection_ref=self.connection_ref,capability='github.repository_context',
            resource_ref=self.repository_ref,operation='read',data_class=self.data_class,provider_ref='provider_github',purpose='project.context')

    def scope_digest(self,sha):
        return hashlib.sha256(json.dumps([sha,self.selection]).encode()).hexdigest()

    def read_repository_context(self,repository_ref,*,guard=None):
        if repository_ref!=self.repository_ref:raise CapabilityDenied('repository selection differs')
        import uuid
        def current():
            if self.guard:self.guard()
            if guard:guard()
            if self.credential:self.credential.current(owner=self.owner_ref,connection_ref=self.connection_ref,repository_ref=repository_ref,revision=self.connection_revision)
            if not self.registry.authorize(self.source_request()).allowed:raise CapabilityDenied('GitHub source scope denied')
        def read(path):
            from dataclasses import replace
            current()
            decision=self.registry.authorize_and_reserve(replace(self.source_request(),operation_ref='github_'+uuid.uuid4().hex),upper_bound=self.upper_bound)
            if not decision.allowed:raise CapabilityDenied(decision.reason)
            def transport():
                current()
                if self.credential:
                    row=self.credential.current(owner=self.owner_ref,connection_ref=self.connection_ref,repository_ref=repository_ref,revision=self.connection_revision)
                    permission='issues' if path.startswith('issues/') else 'pull_requests' if path.startswith('pulls/') else 'contents'
                    if row['scopes']['permissions'].get(permission)!='read':raise CapabilityDenied('GitHub object permission outside selected read scope')
                headers={'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2026-03-10'}
                if self.credential:headers['Authorization']='Bearer '+self.credential.credential(owner=self.owner_ref,connection_ref=self.connection_ref,repository_ref=repository_ref,revision=self.connection_revision)
                value=_https_get('https://api.github.com/repos/'+repository_ref+'/'+path,timeout_seconds=8,max_bytes=128000,
                    headers=headers)
                if value['content_type']!='application/json':raise StorageError('GitHub JSON required')
                return json.loads(value['body'])
            return self.registry.execute_reserved((decision.reservation,),transport)
        commit=read('commits/'+quote(self.ref,safe=''))
        sha=commit.get('sha')
        if not isinstance(sha,str) or not re.fullmatch(r'[a-f0-9]{40}',sha):raise StorageError('observed commit SHA unavailable')
        items=[];gaps=[]
        key=None;cached=None
        if self.cache:
            key=self.cache.key(kind='retrieval',parameters={'selection':self.selection,'sha':sha},dependencies=[],version='github-selected-v2')
            current();cached=self.cache.get(key=key,authorization_request=self.source_request())
        for path in self.paths:
            try:
                if cached is not None:
                    item=next((r for r in cached['items'] if r['path']==path),None)
                    if item is not None:items.append(item);continue
                document=read('contents/'+quote(path,safe='/')+'?'+urlencode({'ref':sha}))
                if (not isinstance(document,dict) or document.get('encoding')!='base64' or document.get('path')!=path
                    or type(document.get('size'))is not int or not 0<=document['size']<=128000
                    or not isinstance(document.get('sha'),str) or not re.fullmatch(r'[a-f0-9]{40}',document['sha'])):
                    raise StorageError('GitHub file scope or size differs')
                if document.get('type','file')!='file' or document.get('submodule_git_url') or document.get('target'):
                    raise StorageError('GitHub regular selected file required')
                raw=base64.b64decode(document['content'],validate=False)
                if len(raw)>128000:raise StorageError('GitHub content exceeds bound')
                text=raw.decode('utf-8')
                items.append({'path':path,'text':text[:4000],'content_truncated':len(text)>4000,'line_start':1,
                    'line_end':len(text[:4000].splitlines()),'object_kind':'file','observed_commit':sha,'source_version':document['sha'],
                    'source_url':'https://github.com/'+repository_ref+'/blob/'+sha+'/'+path,'blob_sha':document.get('sha')})
            except (CapabilityDenied,StorageError):raise
            except Exception:gaps.append('unavailable:'+path)
        if self.cache and key is not None and not gaps:
            self.cache.put(key=key,kind='retrieval',payload={'items':list(items)},dependencies=[],ttl_seconds=300)
        for kind,ids in (('issues',self.issues),('pulls',self.pulls),('releases',self.releases)):
            for number in ids:
                try:
                    value=read(kind+'/'+str(number))
                    url='https://github.com/'+repository_ref+'/'+('pull' if kind=='pulls' else kind)+'/'+str(number)
                    if not isinstance(value,dict) or value.get('number' if kind!='releases' else 'id')!=number or not isinstance(value.get('updated_at'),str):
                        raise StorageError('GitHub selected object identity/version differs')
                    if kind=='releases':
                        url=value.get('html_url')
                        if not isinstance(url,str) or not url.startswith('https://github.com/'+repository_ref+'/releases/tag/') or any(c.isspace() for c in url):raise StorageError('GitHub release identity differs')
                    elif value.get('html_url')!=url:raise StorageError('GitHub selected object repository differs')
                    title=value.get('title',value.get('name','')) or ''
                    body=value.get('body') or ''
                    if not isinstance(title,str) or not isinstance(body,str):raise StorageError('GitHub text required')
                    text=(title+'\n'+body).strip()
                    version=hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
                    items.append({'object_kind':kind,'object_number':number,'text':text[:4000],'content_truncated':len(text)>4000,
                        'source_url':url,'source_version':version,'updated_at':value['updated_at'],
                        'observed_commit':sha,'commit_binding':'mutable_object_not_commit_snapshot'})
                except (CapabilityDenied,StorageError):raise
                except Exception:gaps.append('unavailable:'+kind+':'+str(number))
        current()
        from datetime import datetime,timezone
        from prm.source_contracts import SourceResource,SourceBatch
        scope=self.scope_digest(sha)
        batch=SourceBatch.from_items(items,SourceResource(self.owner_ref,self.repository_ref,'github',self.data_class,connection_ref=self.connection_ref,scope_digest=scope),checked_at=datetime.now(timezone.utc),completeness='partial' if gaps else 'complete',omitted_count=len(gaps),reason='selected_objects_unavailable' if gaps else None)
        return {'source_batch':batch.metadata(),'repository_ref':repository_ref,'requested_ref':self.ref,'observed_ref':sha,'ref':sha,'items':items,'gaps':gaps,
                'status':'partial' if gaps else 'read','read_only':True}


def safe_repository_path(path):
    if not isinstance(path,str) or not re.fullmatch(r'[A-Za-z0-9_./-]{1,200}',path):return False
    parts=path.split('/')
    if any(p in {'','.','..'} or p.startswith('.') for p in parts):return False
    excluded={'node_modules','vendor','dist','build','coverage','__pycache__','generated','secrets','credentials'}
    if any(p.casefold() in excluded for p in parts):return False
    return not re.search(r'(?i)(?:^|/)(?:id_rsa|id_ed25519|credentials[^/]*|secrets?[^/]*|.*\.(?:pem|key|p12|pfx|env|sqlite|db|lock))$',path)
