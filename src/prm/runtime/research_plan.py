"""Bounded two-wave local research plans; no model-selected source expansion."""
import json
import re
from prm.storage.postgres import StorageError


def validate_research_plan(plan, root):
    legacy = {'schema_version','question','steps','max_tool_calls','deadline_seconds'}
    additional = {'gap_steps','coverage_terms'}
    if not isinstance(plan,dict) or type(plan.get('schema_version')) is not int or plan['schema_version'] not in {1,2}:
        raise StorageError('bounded durable research plan required')
    fields = legacy if plan['schema_version']==1 else legacy|additional
    if (set(plan)!=fields or not isinstance(plan['question'],str) or not 0<len(plan['question'])<=2000
        or not isinstance(plan['steps'],list) or not 1<=len(plan['steps'])<=8
        or type(plan['max_tool_calls']) is not int or not 1<=plan['max_tool_calls']<=10
        or type(plan['deadline_seconds']) is not int or not 1<=plan['deadline_seconds']<=300):
        raise StorageError('bounded durable research plan required')
    gaps=plan.get('gap_steps',[])
    terms=plan.get('coverage_terms',[])
    if (not isinstance(gaps,list) or len(gaps)>3 or len(plan['steps'])+len(gaps)>8
        or not isinstance(terms,list) or len(terms)>8 or len(set(terms))!=len(terms)
        or any(not isinstance(t,str) or not 2<=len(t)<=80 or t.casefold() not in plan['question'].casefold() for t in terms)):
        raise StorageError('bounded owner-question coverage terms and gap steps required')
    selected={s.get('source') for s in plan['steps'] if isinstance(s,dict)}
    for step in plan['steps']+gaps:
        if (not isinstance(step,dict) or set(step)!={'source','query'} or step['source'] not in {'archive','public','github'}
            or not isinstance(step['query'],str) or not 0<len(step['query'])<=2000):
            raise StorageError('unsupported source read; effects excluded from research')
        if step['source'] not in selected:raise StorageError('gap wave cannot expand selected sources')
        if step['source']=='public':
            from .web import project_public_query
            if project_public_query(plan['question'],step['query']) is None:raise StorageError('standalone public formulation required')
        if step['source']=='github' and plan['schema_version']==2:
            provider=root.github_context_provider
            if provider is None or step['query']!=provider.repository_ref:raise StorageError('exact selected GitHub repository required')
    identities=[(s['source'],s['query']) for s in plan['steps']+gaps]
    if plan['schema_version']==2 and len(set(identities))!=len(identities):raise StorageError('duplicate research reads excluded')
    if plan['schema_version']==2 and not terms:raise StorageError('explicit coverage terms required')
    return json.loads(json.dumps(plan))


def selected_catalogue(root,plan):
    sources={s['source'] for s in plan['steps']}
    return {'archive_resource':root.archive_resource_ref if 'archive' in sources else None,
            'archive_selection':root.archive_selection.digest if 'archive' in sources and root.archive_selection else None,
            'public_resources':[root.public_search_ref,root.public_fetch_ref] if 'public' in sources else None,
            'public_hosts':list(root.public_web_bounds.trusted_source_hosts) if 'public' in sources and root.public_web_bounds else None,
            'github_selection':json.loads(json.dumps(root.github_context_provider.selection)) if 'github' in sources and root.github_context_provider else None}


def assess_coverage(plan,completed,eligible_rows):
    terms=plan.get('coverage_terms',[])
    texts=[' '.join(str(r.get('support_span') or r.get('text') or r.get('content') or r.get('snippet') or '').split()).casefold() for r in eligible_rows]
    covered=[t for t in terms if any(t.casefold() in text for text in texts)]
    missing=[t for t in terms if t not in covered]
    conflicts=any(e['evidence'].get('conflicts') for e in completed if e['status']=='gathered')
    groups={}
    for row in eligible_rows:
        if row.get('conflict_group') and row.get('conflict_value'):
            groups.setdefault(row['conflict_group'],set()).add(row['conflict_value'])
    conflicts=conflicts or any(len(v)>1 for v in groups.values())
    unknown=any(e['status']=='source_outcome_unknown' for e in completed)
    unavailable=any(e['status']=='source_unavailable' for e in completed)
    unattempted=max(0,len(plan['steps'])-sum(e.get('wave',0)==0 for e in completed))
    return {'schema_version':'assistant.research_coverage.v1','mechanism':'exact_lexical_terms_not_semantic_answer_acceptance',
            'covered_terms':covered,'missing_terms':missing,'eligible_read_count':len(eligible_rows),'conflicts':bool(conflicts),
            'unattempted_primary_count':unattempted,
            'sufficient':bool(terms and not missing and eligible_rows and not conflicts and not unknown and not unavailable and not unattempted),
            'stop_extra_wave':unknown or unavailable,'unknown_outcome':unknown}


def coverage_terms(question):
    stops={'deep','research','investigate','please','исследуй','исследование','глубоко','подробно','пожалуйста','сравни','про','для','что','как','моего','мой','моим','проект','проектом'}
    terms=list(dict.fromkeys(t for t in re.findall(r'[\w-]{3,}',question.casefold()) if t not in stops))[:8]
    return terms or [question[:80]]
