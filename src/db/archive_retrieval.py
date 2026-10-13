"""Bounded canonical retrieval; variants and sidecars never widen source scope."""
from __future__ import annotations
from dataclasses import dataclass,replace
import hashlib,json,re,unicodedata
from db.archive_search import (ArchiveSearchError,ArchiveSearchResult,_coerce_filters,
    _append_in_filter,_append_reaction_filter,_append_tag_filter,_append_project_filter,
    _reaction_count_sql,_tag_count_sql,_project_names_sql,_result_from_row)
from db.archive_documents import archive_documents_for_row

VERSION='canonical-retrieval-v1'
# Fixed vocabulary predates synthetic measurements. This is lexical expansion,
# not learned semantics or an unrestricted translation service.
GROUPS=(
    ('agent','агентов',('agents','агент','агенты','агентов','агентами')),
    ('evaluation','оценка',('eval','evals','evaluations','оценка','оценки','оценку','оценивание')),
    ('regression','регрессионные',('regressions','регрессионные','регрессионных','регрессия')),
    ('tests','тесты',('test','checks','тесты','тестов','проверки','проверок')),
    ('task','задач',('tasks','задача','задачи','задач')),
    ('success','успешность',('successful','успех','успешность','успешности')),
    ('retrieval','поиск',('search','поиск','поиска','поиску')),
    ('vector','векторный',('vectors','векторный','векторного','векторный','векторная','вектор')),
    ('context','контекст',('contexts','контекст','контекста','контекстный')),
    ('grounded','проверенные',('grounding','проверенные','подтверждённые','подтвержденные')),
    ('source','источники',('sources','источник','источники','источников')),
    ('service','сервис',('services','сервиса','сервис','сервисы')),
    ('latency','задержку',('delay','задержка','задержку','задержки')),
)
STOP=frozenset({'найди','покажи','материалы','материал','про','о','об','в','и','на','the','a','an','about','find','show','in','and','for'})
TOKEN=re.compile(r'[0-9a-zа-яё][0-9a-zа-яё_+-]*',re.I)


def query_variants(query):
    if not isinstance(query,str) or not 0<len(query.encode())<=2000:raise ArchiveSearchError('bounded retrieval query required')
    terms=[t for t in TOKEN.findall(unicodedata.normalize('NFKC',query).casefold()) if t not in STOP][:16]
    if not terms:raise ArchiveSearchError('query must contain searchable terms')
    aliases={a:(en,ru) for en,ru,forms in GROUPS for a in (en,ru,*forms)}
    candidates=[' '.join(terms)]
    candidates.extend(' '.join(aliases.get(t,(t,t))[index] for t in terms) for index in (0,1))
    return tuple(dict.fromkeys(candidates))[:3]


@dataclass(frozen=True)
class RetrievalResult:
    items: tuple[ArchiveSearchResult,...]
    variant_count: int
    candidate_count: int
    rejected_sidecar_count: int
    vector_status: str

    def metadata(self):
        return {'version':VERSION,'variant_count':self.variant_count,'candidate_count':self.candidate_count,
            'selected_count':len(self.items),'rejected_sidecar_count':self.rejected_sidecar_count,
            'vector_status':self.vector_status,'coverage':'bounded_query_candidates','learned_status':'not_run_D46_gate'}


def retrieve_archive(connection,query,*,filters=None,limit=10,vector_index_path=None,expand=True,snippet_tokens=32,chunk_max_chars=3200):
    from db.archive_search import search_telegram_archive_fts
    if type(limit)is not int or not 1<=limit<=80:raise ArchiveSearchError('retrieval limit must be 1..80')
    normalized=_coerce_filters(filters)
    exact=re.fullmatch(r'tg:(-?\d{1,19}):([1-9]\d{0,18})',query) if isinstance(query,str) else None
    url=re.fullmatch(r'https://t\.me/[A-Za-z0-9_]{1,64}/[1-9]\d{0,18}',query) if isinstance(query,str) else None
    if exact or url:
        values=(int(exact[1]),int(exact[2])) if exact else (query,)
        if any(isinstance(v,int) and not -2**63<v<2**63 for v in values):raise ArchiveSearchError('canonical identity exceeds bound')
        predicate='r.channel_id=? AND r.message_id=?' if exact else 'r.message_url=?'
        rows=connection.execute('SELECT p.id FROM posts p JOIN raw_posts r ON r.id=p.raw_post_id WHERE '+predicate+' LIMIT 80',values).fetchall()
        canonical=_canonical_rows(connection,tuple(r[0] for r in rows),normalized)
        items=[]
        for row in canonical.values():
            documents,excluded=archive_documents_for_row(row,chunk_max_chars=chunk_max_chars)
            if documents:
                item=_result_from_row({**dict(row),'rank':0,'snippet':documents[0].content[:320]},document=documents[0])
                items.append(replace(item,retrieval_mode='canonical_exact_lookup'))
        return RetrievalResult(tuple(items[:limit]),1,len(items),0,'not_selected')
    variants=query_variants(query) if expand else (query,)
    entries={};rejected=0;vector_status='not_selected'
    def add(item,rank,weight,mode):
        # Post-level dedup also prevents long chunks occupying every top slot.
        key=item.post_archive_document_id
        entry=entries.setdefault(key,{'item':item,'score':0.0,'modes':set(),'fts_rank':None,'vector_rank':None})
        entry['score']+=weight/(60+rank);entry['modes'].add(mode)
        field='fts_rank' if mode=='fts' else 'vector_rank'
        entry[field]=min(entry[field],rank) if entry[field] is not None else rank
    for index,variant in enumerate(variants):
        rows=search_telegram_archive_fts(connection,variant,filters=normalized,limit=min(80,max(20,limit*3)),
            snippet_tokens=snippet_tokens,chunk_max_chars=chunk_max_chars)
        canonical=_canonical_rows(connection,tuple({i.post_id for i in rows}),normalized)
        terms=set(TOKEN.findall(variant.casefold()))
        for rank,item in enumerate(rows,1):
            row=canonical.get(item.post_id)
            if row and terms & set(TOKEN.findall(row['content'].casefold())):
                documents,excluded=archive_documents_for_row(row,chunk_max_chars=chunk_max_chars)
                match=next((doc for doc in documents if doc.archive_document_id==item.archive_document_id and doc.content_hash==item.content_hash),None)
                if match:add(_result_from_row({**dict(row),'rank':item.rank,'snippet':item.snippet},document=match),rank,3 if index==0 else 1,'fts')
    if vector_index_path is not None:
        from db.archive_vector import search_archive_vector_index,ArchiveVectorIndexError
        try:
            candidates=search_archive_vector_index(index_path=vector_index_path,query=variants[0],filters=normalized,limit=80)
            canonical=_canonical_rows(connection,tuple({i.post_id for i in candidates}),normalized)
            for rank,item in enumerate(candidates,1):
                row=canonical.get(item.post_id)
                documents,excluded=archive_documents_for_row(row,chunk_max_chars=chunk_max_chars) if row else ((),None)
                match=next((doc for doc in documents if doc.archive_document_id==item.archive_document_id and doc.content_hash==item.content_hash),None)
                if match is None:rejected+=1;continue
                fresh=_result_from_row({**dict(row),'rank':item.rank,'snippet':match.content[:320]},document=match)
                add(fresh,rank,1,'hashed_vector')
            vector_status='canonical_revalidated'
        except ArchiveVectorIndexError:vector_status='unavailable_no_index_build'
    families={}
    for entry in entries.values():
        key=entry['item'].content_hash
        prior=families.get(key)
        if prior is None:families[key]=dict(entry,modes=set(entry['modes']))
        else:
            prior['score']=max(prior['score'],entry['score']);prior['modes'].update(entry['modes'])
            for field in ('fts_rank','vector_rank'):
                values=[n for n in (prior[field],entry[field]) if n is not None];prior[field]=min(values) if values else None
            if entry['item'].post_archive_document_id<prior['item'].post_archive_document_id:prior['item']=entry['item']
    ranked=sorted(families.values(),key=lambda e:(-e['score'],e['item'].post_archive_document_id))
    selected=[];seen_hashes=set();counts={};deferred=[]
    for entry in ranked:
        item=entry['item']
        if item.content_hash in seen_hashes:continue
        seen_hashes.add(item.content_hash)
        if counts.get(item.channel_id,0)>=max(1,(limit+1)//2):deferred.append(entry);continue
        selected.append(entry);counts[item.channel_id]=counts.get(item.channel_id,0)+1
    selected=(selected+deferred)[:limit]
    items=tuple(replace(e['item'],retrieval_mode='canonical_expanded_fts' if 'hashed_vector' not in e['modes'] else 'canonical_fts_hashed_fusion',
        fusion_score=round(e['score'],8),fts_rank=e['fts_rank'],vector_rank=e['vector_rank']) for e in selected)
    return RetrievalResult(items,len(variants),len(entries),rejected,vector_status)


def _canonical_rows(connection,ids,filters):
    if not ids:return {}
    if len(ids)>80 or any(type(i)is not int or i<=0 for i in ids):raise ArchiveSearchError('bounded canonical candidates required')
    where=['p.id IN ('+','.join('?' for _ in ids)+')',"typeof(p.content)='text'","trim(p.content)<>''"]
    params=list(ids)
    _append_in_filter(where,params,'p.channel_username',filters.channel_usernames)
    if filters.channel_identities:
        where.append('('+' OR '.join('(r.channel_id=? AND p.channel_username=?)' for _ in filters.channel_identities)+')')
        params.extend(v for pair in filters.channel_identities for v in pair)
    _append_in_filter(where,params,'p.language_detected',filters.languages)
    for value,operator in ((filters.date_from,'>='),(filters.date_to,'<')):
        if value:where.append('p.posted_at '+operator+' ?');params.append(value)
    _append_reaction_filter(connection,where,params,filters);_append_tag_filter(connection,where,params,filters);_append_project_filter(connection,where,params,filters)
    sql='SELECT p.id AS post_id,p.raw_post_id,p.channel_username,p.posted_at,p.content,p.language_detected,r.channel_id,r.message_id,r.message_url,r.forward_from,'+_reaction_count_sql(connection)+' AS reaction_count,'+_tag_count_sql(connection)+' AS tag_count,'+_project_names_sql(connection)+' AS project_names FROM posts p JOIN raw_posts r ON r.id=p.raw_post_id WHERE '+' AND '.join(where)
    rows=connection.execute(sql,params).fetchall()
    return {row['post_id']:row for row in rows}
