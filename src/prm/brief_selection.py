"""Separate editorial signals and exact confirmed project relationships."""
import re
from prm.brief_editorial import BriefEditorial, BriefStory, StoryAnchor

VERSION = 'brief-attention-v1'


def brief_ref(record):
    from prm.briefs import _slug,_EVIDENCE_REF
    identity=record.payload.get('evidence_id') or record.external_ref
    return identity if _EVIDENCE_REF.fullmatch(identity) else 'evidence_'+_slug(identity,fallback=record.payload.get('source_url',''))


def safe_anchor(text):
    parts=re.split(r'https?://\S+|<[^>]*>',text)
    for part in sorted(parts,key=len,reverse=True):
        part=part.strip()
        if len(part)>=16:return part[:1200]
    # An anchor is a literal pointer, not a factual shortening. Neutral UI
    # wording below is used when no supported factual excerpt is available.
    for start in range(max(0,len(text)-15)):
        part=text[start:start+16]
        if not re.search(r'https?://|<[^>]+>',part):return part
    return None


def project_match(record, projects):
    value = record.payload
    dependency = value.get('dependency_ref')
    if not isinstance(dependency, dict) or dependency.get('namespace') != 'result':
        return None
    span = value.get('support_span') or value.get('summary') or ''
    for item in projects:
        context = item.payload['project_context']
        descriptor = context['descriptor']
        from assistant.project_portfolio_context import project_action_recommendation_allowed
        if not project_action_recommendation_allowed(descriptor, direct_evidence=True):
            continue
        for relation in context['relationships']:
            if (relation['evidence_ref'] == dependency.get('object_ref')
                and relation['evidence_version'] == dependency.get('version')
                and relation['evidence_digest'] == dependency.get('digest')
                and relation['quote'] in span):
                return {'project_ref': item.object_id, 'version': item.version, 'digest': item.digest,
                        'name': descriptor['name'], 'goal': descriptor['current_goal'],
                        'blocker': descriptor['current_blocker'], 'relationship': relation}
    return None


def event_signals(event, *, projects=(),rules=()):
    matches = [(r, project_match(r, projects)) for r in event.records]
    applicable = next(((r, m) for r, m in matches if m), None)
    representative = applicable[0] if applicable else min(event.records, key=lambda r: (
        {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}.get(r.payload.get('importance'), 4), r.evidence_ref))
    p = representative.payload
    text = p.get('support_span') or p.get('summary') or ''
    from prm.feedback import preference_signal
    feedback=preference_signal(representative,rules)
    return representative, {'importance': p.get('importance', 'unknown'),'feedback':feedback,
        'importance_basis': 'source_annotation_or_local_heuristic_not_verified_fact',
        'novelty': event.novelty, 'reliability': 'conflicting' if event.conflict else 'single_or_unverified_independence',
        'project_applicability': 'confirmed_relationship' if applicable else 'unknown',
        'project': applicable[1] if applicable else None,
        'reading_cost_words': len(str(text).split()),'selection_reading_cost_words':len(str(text).split())*(2 if 'reading_cost' in feedback['features'] else 1),
        'verification_requested':'reliability' in feedback['features'],'mechanism': VERSION}


def select_events(events, *, projects=(),rules=(), maximum=20):
    rows = [(e, *event_signals(e, projects=projects,rules=rules)) for e in events]
    def rank(row):
        e, r, s = row
        return ({'critical': 0, 'high': 1}.get(s['importance'], 2),
                0 if e.conflict else 1, 0 if s['project'] else 1,
                s['feedback']['adjustment'],{'changed': 0, 'new': 1, 'uncertain':2, 'repeated': 3}[e.novelty],
                s['selection_reading_cost_words'], r.evidence_ref)
    mandatory=sorted((r for r in rows if r[0].conflict or r[2]['importance']=='critical'),key=rank)
    selected=mandatory[:maximum]
    groups={}
    for row in sorted(rows,key=rank):
        if row in mandatory:continue
        record=row[1]
        key=(record.resource.resource_ref,record.payload.get('source_group_id') or record.resource.kind)
        groups.setdefault(key,[]).append(row)
    ordered=sorted(groups.values(),key=lambda g:rank(g[0]))
    index=0
    while len(selected)<maximum and any(index<len(g) for g in ordered):
        for group in ordered:
            if index<len(group) and len(selected)<maximum:selected.append(group[index])
        index+=1
    return tuple(selected)


def build_attention_editorial(document, decisions):
    # This local fallback uses verbatim facts. No model can manufacture project
    # context or turn a suggested experiment into an obligation.
    sources = document.evidence_by_ref()
    stories = []
    used = set()
    continuations = 0
    for event, record, signal in decisions:
        if len(stories) >= 5:
            break
        ref=brief_ref(record)
        source = sources.get(ref)
        if source is None or len(source.summary) < 16:
            continue
        if event.novelty == 'repeated' and not event.conflict and signal['importance'] not in {'critical', 'high'}:
            continue
        project = signal['project']
        why = ('Редакционный приоритет: отмечено существенное изменение; оценка важности требует проверки.'
               if signal['importance'] in {'critical', 'high'} else
               'Изменение относительно предыдущего обзора.' if event.novelty == 'changed' else
               'Материал в проверенной выборке; новизна не подтверждена.' if event.novelty=='uncertain' else
               'Новый материал в проверенной выборке.')
        next_step = ''
        caveat = 'Независимое подтверждение не установлено.'
        if event.conflict:
            caveat = 'Источники расходятся; проверьте исходные значения до решения.'
        if project:
            why = 'Подтверждённая связь с проектом «' + project['name'][:80] + '»: ' + project['relationship']['relation'][:160]
            if continuations < 3:
                next_step = 'Возможный эксперимент: ' + project['relationship']['experiment'][:180]
                continuations += 1
            caveat = 'Условие отказа: ' + project['relationship']['reject_if'][:240]
            if event.conflict:caveat='Источники расходятся; проверьте исходные значения. '+caveat
        elif continuations < 3:
            next_step = 'Изучить исходный материал, если тема сейчас полезна.'
            continuations += 1
        if signal.get('feedback',{}).get('rule_bindings'):
            why+=' Учтено подтверждённое правило для этой темы.'
        if signal.get('verification_requested') and not project:
            next_step='Проверить исходное утверждение перед применением.'
        if source.time_kind == 'discovered':
            caveat = 'Впервые обнаружено в этом периоде; время события не подтверждено. ' + caveat
        # Keep validator text limits/URL rules; source text with URLs remains in
        # document evidence, and that uncertain story falls back to its source.
        quote=safe_anchor(source.summary)
        if quote is None:continue
        from prm.research_blocks import fact_proof
        known=[{'source_url':source.source_ref,'support_span':source.summary}]
        fact=source.summary[:280]
        neutral='Краткая формулировка не подтверждена. Откройте исходный материал.'
        if not fact_proof(fact,source.summary,source.source_ref,known) or re.search(r'https?://|<[^>]+>',fact):
            fact=neutral
            caveat='Для проверки утверждений нужен полный исходный фрагмент. '+caveat
        title = source.title[:140]
        if not fact_proof(title,source.summary,source.source_ref,known) or re.search(r'https?://|<[^>]+>',title):title='Материал источника'
        if title.startswith('@') or any(s.title.casefold()==title.casefold() for s in stories):
            # A unique neutral label introduces no numeric/source claim.
            title='Материал источника '+'•'*len(stories)
        stories.append(BriefStory(title, fact, fact, fact, why[:300], next_step[:300], caveat[:300], (StoryAnchor(ref, quote),)))
        used.add(ref)
    candidate = BriefEditorial(tuple(stories), tuple(sources.keys() - used))
    try:
        return BriefEditorial.from_dict(candidate.to_dict(), document.evidence)
    except ValueError:
        # Do not accept unsupported numeric headlines or unsafe source strings.
        safe = []
        for story in stories:
            try:
                BriefEditorial.from_dict({'stories': [story.to_dict()], 'omitted_refs': [r for r in sources if r not in {a.evidence_ref for a in story.anchors}]}, document.evidence)
            except ValueError:
                continue
            safe.append(story)
        used = {a.evidence_ref for s in safe for a in s.anchors}
        return BriefEditorial(tuple(safe), tuple(r for r in sources if r not in used))


def admit_editorial_wording(local, proposed, evidence):
    """D14 fact admission applies to model prose; selection/next steps stay bound.

    Exact quotes alone do not verify a story. A model cannot overwrite a
    current confirmed relationship, erase a required event or invent a duty.
    """
    if type(proposed) is not BriefEditorial:return local
    from dataclasses import replace
    from prm.research_blocks import fact_proof
    sources={e.evidence_ref:e for e in evidence}
    rows=[]
    for story in local.stories:
        refs={a.evidence_ref for a in story.anchors}
        offers=[s for s in proposed.stories if {a.evidence_ref for a in s.anchors}==refs]
        if len(offers)!=1:rows.append(story);continue
        offer=offers[0]
        known=[{'source_url':sources[a.evidence_ref].source_ref,'support_span':sources[a.evidence_ref].summary} for a in story.anchors]
        def proof(text):
            return any(fact_proof(text,a.quote,sources[a.evidence_ref].source_ref,known) for a in story.anchors)
        if not all(proof(s) for s in (offer.summary,offer.explanation,offer.plain_explanation)) or not proof(offer.title):
            rows.append(story);continue
        rows.append(replace(story,title=offer.title,summary=offer.summary,explanation=offer.explanation,plain_explanation=offer.plain_explanation))
    try:return BriefEditorial.from_dict(BriefEditorial(tuple(rows),local.omitted_refs).to_dict(),evidence)
    except ValueError:return local
