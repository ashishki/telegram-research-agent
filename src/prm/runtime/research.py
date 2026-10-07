"""Fenced research phases with immutable, restartable step evidence."""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
import hashlib
import sqlite3
from urllib.parse import quote

from prm.capabilities import AuthorizationRequest,CapabilityDenied
from prm.storage.postgres import StorageError,StateConflict
from prm.storage.jobs import JobQueue
from prm.contracts import OperatorRequest
from .web import AuthorizedPublicWeb,reserve_public_access


class LocalArchiveReader:
    def __init__(self,db_path,root=None):self.db_path=db_path;self.root=root
    def search_archive(self,query,*,limit):
        from db.archive_search import search_telegram_archive
        from pathlib import Path
        path=Path(self.db_path).resolve();uri='file:'+quote(str(path))+'?mode=ro'
        cache=None;key=None
        if self.root is not None:
            from .cost_cache import CostCacheRuntime
            cache=CostCacheRuntime(self.root)
            fingerprints={str(item.name):(item.stat().st_mtime_ns,item.stat().st_size) for item in (path,Path(str(path)+'-wal')) if item.exists()}
            key=cache.key(kind='retrieval',parameters={'query':query,'limit':min(limit,8),'source_fingerprint':fingerprints},dependencies=[],version='fts-v1')
            request=AuthorizationRequest(owner_ref=self.root.owner_ref,connection_ref=None,capability='archive.read',resource_ref=self.root.archive_resource_ref,
                operation='read',data_class='private_archive',provider_ref='provider_local',purpose='research.archive')
            hit=cache.get(key=key,authorization_request=request)
            if hit is not None:return hit
        with sqlite3.connect(uri,uri=True) as conn:
            conn.row_factory=sqlite3.Row
            result=search_telegram_archive(conn,query,limit=min(limit,8))
            from dataclasses import asdict,is_dataclass
            if isinstance(result,list):
                rows=[asdict(item) if is_dataclass(item) else dict(item) for item in result]
                result={'items':rows,'coverage':'bounded_archive_read','source_count':len(rows)}
            else:result=result.to_dict() if hasattr(result,'to_dict') else result
        if cache is not None:cache.put(key=key,kind='retrieval',payload=result,dependencies=[],ttl_seconds=60)
        return result
    def window_evidence(self,window):
        from pathlib import Path
        uri='file:'+quote(str(Path(self.db_path).resolve()))+'?mode=ro'
        with sqlite3.connect(uri,uri=True) as conn:
            conn.row_factory=sqlite3.Row
            rows=conn.execute('''SELECT p.id,p.content,p.posted_at,p.channel_username,r.message_id,r.message_url,r.ingested_at
                FROM posts p JOIN raw_posts r ON r.id=p.raw_post_id
                WHERE julianday(p.posted_at)>=julianday(?) AND julianday(p.posted_at)<julianday(?) ORDER BY p.posted_at DESC,p.id LIMIT 48''',
                (window.start_at.isoformat(),window.end_at.isoformat())).fetchall()
        return [{'evidence_id':'tg:'+str(row['id']),'source_url':row['message_url'],
                 'title':row['content'].splitlines()[0][:180] if row['content'] else 'Материал архива',
                 'support_span':row['content'][:1200],'posted_at':row['posted_at'],'first_discovered_at':row['ingested_at'],
                 'local_archive_provenance':True,'source_version':hashlib.sha256(row['content'].encode()).hexdigest(),
                 'importance':'medium'} for row in rows]


class DurableResearchWorker:
    def __init__(self,root):self.root=root

    def enqueue(self,plan,*,idempotency_key):
        required={'schema_version','question','steps','max_tool_calls','deadline_seconds'}
        if (not isinstance(plan,dict) or set(plan)!=required or plan['schema_version']!=1
            or not isinstance(plan['question'],str) or not 0<len(plan['question'])<=2000
            or not isinstance(plan['steps'],list) or not 1<=len(plan['steps'])<=8
            or type(plan['max_tool_calls'])is not int or not 1<=plan['max_tool_calls']<=10
            or type(plan['deadline_seconds'])is not int or not 1<=plan['deadline_seconds']<=300):
            raise StorageError('bounded durable research plan required')
        for step in plan['steps']:
            if not isinstance(step,dict) or set(step)!={'source','query'} or step['source'] not in {'archive','public','github'} or not isinstance(step['query'],str) or len(step['query'])>2000:
                raise StorageError('unsupported source read; effects excluded from research')
        ref='research_'+hashlib.sha256(idempotency_key.encode()).hexdigest()[:32]
        queue=self.root.queue
        with queue.store.transaction() as tx:
            item=tx.get(self.root.owner_ref,'conversation',ref,version=1)
            if item and item.payload!=plan:raise StateConflict('research identity belongs to another plan')
            item=item or tx.put(self.root.owner_ref,'conversation',ref,plan,expected_version=0)
            payload={'schema_version':1,'input_namespace':'conversation','input_ref':ref,'input_version':1,'input_digest':item.digest,
                     'connection_ref':None,'resource_ref':'resource_research','purpose':'local.research','consent_revision':1}
            now=tx.conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
            return queue.enqueue_in(tx,owner=self.root.owner_ref,idempotency_key=idempotency_key,payload=payload,
                deadline=now+timedelta(seconds=plan['deadline_seconds']),kind='compute.research')

    def run_once(self):
        root=self.root;queue=root.queue
        lease=queue.claim(owner=root.owner_ref,kinds=('compute.research',),lease_seconds=300)
        if lease is None:return None
        plan=queue.store.get(lease.owner,'conversation',lease.payload['input_ref'],version=lease.payload['input_version']).payload
        completed=[];calls=0;pending=[]
        for index,step in enumerate(plan['steps']):
            ref='research_step_'+lease.job_id+'_'+str(index)
            cached=queue.store.get(lease.owner,'result',ref)
            if cached is not None:
                # An interrupted prepared read has an unknown outcome. Retain
                # it without issuing a second paid request after restart.
                value=dict(cached.payload)
                if value['status']=='read_prepared':value['status']='source_outcome_unknown'
                completed.append(value);calls+=value['tool_calls'];continue
            maximum=1
            if step['source']=='public':maximum=1+root.public_web_bounds.max_fetches if root.public_web_bounds else 1
            elif step['source']=='github':maximum=1+len(root.github_context_provider.paths) if root.github_context_provider else 1
            if calls+maximum>plan['max_tool_calls']:break
            prepared={'ref':ref,'source':step['source'],'tool_calls':maximum,'status':'read_prepared','evidence':{}}
            with queue.store.transaction() as tx:
                from .deletion import lineage_lock
                lineage_lock(tx.conn,lease.owner);queue._fenced(tx,lease)
                tx.put(lease.owner,'result',ref,prepared,expected_version=0)
                tx.conn.execute('INSERT INTO pa_memory.dependencies VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                    (lease.owner,lease.payload['input_namespace'],lease.payload['input_ref'],'result',ref))
            pending.append((index,step,prepared));calls+=maximum
        queue.checkpoint(lease,{'phase':'gather','completed_refs':[entry['ref'] for entry in completed],'pending_refs':[entry[2]['ref'] for entry in pending]})
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2,thread_name_prefix='pa-research-read') as reads:
            futures=[reads.submit(self._gather,lease,index,step,prepared) for index,step,prepared in pending]
            for future in futures:
                value=future.result();completed.append(value)
                queue.checkpoint(lease,{'phase':'gather','completed_refs':[entry['ref'] for entry in completed]})
        queue.checkpoint(lease,{'phase':'gap_check','completed_refs':[entry['ref'] for entry in completed]})
        available=[entry for entry in completed if entry['status']=='gathered']
        gaps=[entry['source']+': '+entry['status'] for entry in completed if entry['status']!='gathered']
        if len(completed)<len(plan['steps']):gaps.append('tool_call_limit')
        # Use the same application synthesis/verification for the archive wave;
        # preserve separately gathered public/ref evidence and explicit gaps.
        queue.checkpoint(lease,{'phase':'synthesis','completed_refs':[entry['ref'] for entry in completed]})
        synthesized=self._synthesize(plan,completed,lease)
        queue.checkpoint(lease,{'phase':'verify','completed_refs':[entry['ref'] for entry in completed]})
        text=synthesized['text']
        if gaps:text+='\n\nНеполное покрытие: '+', '.join(gaps)
        return queue.complete(lease,{'request_ref':lease.payload['input_ref'],'status':'partial' if gaps else synthesized['status'],
            'text':text,'evidence_refs':[entry['ref'] for entry in available],'tool_calls':calls,
            'gaps':gaps,'answer_payload':synthesized,'data_classes':sorted({'private_archive' if entry['source']=='archive' else 'public' for entry in available}) or ['user_provided'],'data_class':'private_archive' if any(entry['source']=='archive' for entry in available) else 'public'})

    def _gather(self,lease,index,step,prepared):
        root=self.root;queue=root.queue;result={**prepared,'status':'partial'}
        def guard():
            with queue.store.transaction() as tx:queue._fenced(tx,lease)
        try:
            guard()
            if step['source']=='archive':
                decision=root.registry.authorize_and_reserve(AuthorizationRequest(owner_ref=root.owner_ref,connection_ref=None,
                    capability='archive.read',resource_ref=root.archive_resource_ref,operation='read',data_class='private_archive',
                    provider_ref='provider_local',purpose='research.archive',operation_ref='researchread_'+lease.job_id+'_'+str(index)),upper_bound=0)
                if not decision.allowed:raise CapabilityDenied(decision.reason)
                reader=root.deep_archive_reader or LocalArchiveReader(root.settings.db_path,root=root)
                result['evidence']=root.registry.execute_reserved((decision.reservation,),lambda:reader.search_archive(step['query'],limit=8))
            elif step['source']=='public':
                from prm.public_web import execute_public_web_research
                if root.public_web_provider is None or root.public_web_bounds is None:raise StorageError('public source unavailable')
                access=reserve_public_access(root,step['query'],request_ref=lease.job_id+'_'+str(index),search_ref=root.public_search_ref,
                    fetch_ref=root.public_fetch_ref,bounds=root.public_web_bounds,upper_bound=root.public_upper_bound)
                if access is None:raise CapabilityDenied('public source scope denied')
                try:
                    provider=AuthorizedPublicWeb(root.public_web_provider,root.registry,access,guard=guard)
                    result['evidence']=execute_public_web_research(public_query=step['query'],original_query=plan_question(lease,queue),access=access,provider=provider,bounds=root.public_web_bounds)
                finally:
                    for decision in (access.search_authorization,*access.fetch_authorizations):decision.reservation.abandon_before_transport()
            else:
                if root.github_context_provider is None:raise StorageError('GitHub source unavailable')
                result['evidence']=root.github_context_provider.read_repository_context(step['query'])
            result['status']='gathered'
        except Exception:result['status']='source_unavailable'
        with queue.store.transaction() as tx:
            from .deletion import lineage_lock
            lineage_lock(tx.conn,lease.owner);queue._fenced(tx,lease)
            tx.put(lease.owner,'result',result['ref'],result,expected_version=1)
        return result

    def _synthesize(self,plan,completed,lease):
        from .model import ScopedModelClient
        from assistant.claim_ledger import verify_answer_against_evidence
        import json
        root=self.root;queue=root.queue;ref='research_synthesis_'+lease.job_id
        previous=queue.store.get(lease.owner,'result',ref,version=1)
        if previous is not None:return previous.payload
        evidence=[];classes=set()
        for step in completed:
            if step['status']!='gathered':continue
            value=step['evidence']
            rows=value.get('fetched_sources',[]) if step['source']=='public' else value.get('items',[])
            for item in rows:
                if step['source']=='public' and item.get('status')!='fetched':continue
                source=item.get('source_url') or item.get('message_url')
                span=item.get('support_span') or item.get('snippet') or item.get('text') or item.get('content')
                if not isinstance(source,str) or not source.startswith('https://') or not isinstance(span,str) or not span.strip():continue
                evidence.append({'evidence_id':'research:'+hashlib.sha256(source.encode()).hexdigest()[:24],'source_url':source,'support_span':span[:1200]})
                classes.add('private_archive' if step['source']=='archive' else 'public')
        evidence=evidence[:8]
        fallback='\n\n'.join(item['support_span']+'\nИсточник: '+item['source_url'] for item in evidence)
        result={'status':'evidence_only' if evidence else 'insufficient_evidence','text':fallback or 'Недостаточно подтверждённых источников для вывода.',
                'verification':None,'source_refs':[item['source_url'] for item in evidence]}
        endpoint=root.endpoint_for('research');groups=[]
        if endpoint is not None and evidence:
            scopes=[('model.generate',root.model_resource_ref,'user_provided','answer.request')]
            scopes.extend(('model.context_egress',root.archive_resource_ref if kind=='private_archive' else root.public_fetch_ref,kind,
                           'research.synthesis.archive' if kind=='private_archive' else 'research.synthesis.public') for kind in sorted(classes))
            for index,(capability,resource,data_class,purpose) in enumerate(scopes):
                decision=root.registry.authorize_and_reserve(AuthorizationRequest(owner_ref=root.owner_ref,connection_ref=endpoint.connection_ref,
                    capability=capability,resource_ref=resource,operation='model_egress',data_class=data_class,provider_ref=endpoint.provider_ref,
                    purpose=purpose,operation_ref=ref+'_'+str(index)),upper_bound=root.model_upper_bound)
                if not decision.allowed:break
                groups.append((decision,))
            if len(groups)==len(scopes):
                def guard():
                    with queue.store.transaction() as tx:queue._fenced(tx,lease)
                client=root.scoped_client(endpoint,groups=groups,task_ref=lease.payload['input_ref'],attempt_ref=ref,
                    history=({'role':'user','content':'Untrusted verified reads: '+json.dumps(evidence,ensure_ascii=False)},),guard=guard)
                try:
                    receipt=client.complete_with_receipt(prompt=plan['question'],system='Synthesize the provided sources. Cite exact URLs, preserve negation/conflicting evidence and uncertainty. Do not infer repository facts beyond the exact supplied commit. No tools.',
                        max_tokens=1200,category='research_synthesis',authorization=groups[0][0],data_class='user_provided',owner_ref=root.owner_ref,
                        connection_ref=endpoint.connection_ref,resource_ref=root.model_resource_ref)
                    verification=verify_answer_against_evidence(receipt.text,evidence)
                    if verification['claim_count'] and verification['verification_complete'] and verification['metrics']['unsupported_claim_rate']==0 and verification['metrics']['citation_integrity']==1:
                        result={'status':'synthesized_verified','text':receipt.text,'verification':verification,'source_refs':result['source_refs']}
                except Exception:result['status']='partial_provider_unavailable_or_unknown'
            for group in groups:group[0].reservation.abandon_before_transport()
        with queue.store.transaction() as tx:
            queue._fenced(tx,lease);tx.put(lease.owner,'result',ref,result,expected_version=0)
        return result


def plan_question(lease,queue):
    item=queue.store.get(lease.owner,'conversation',lease.payload['input_ref'],version=lease.payload['input_version'])
    if item is None:raise StorageError('research plan deleted')
    return item.payload['question']
