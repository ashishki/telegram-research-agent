"""Frozen deterministic event labels, revisions and honest independence."""
from pathlib import Path
import json
from datetime import datetime,timezone
from prm.source_contracts import SourceResource,SourceBatch
from prm.event_clusters import cluster_events


def records(texts,urls=None,**extra):
    urls=urls or ['https://primary.example.test/event']
    return SourceBatch.from_items([{'evidence_id':'row_'+str(i),'canonical_url':urls[i%len(urls)],
        'source_url':'https://t.me/synthetic/'+str(i),'support_span':text,'source_version':'v'+str(i),**extra}
        for i,text in enumerate(texts)],SourceResource('owner_fixture','resource_fixture','archive','private_archive'),
        checked_at=datetime.now(timezone.utc),completeness='complete',omitted_count=0).items


def test_frozen_reposts_gold_event_recall_and_duplicate_rate():
    cases=json.loads((Path(__file__).parent/'fixtures/daily07_events.json').read_text())['cases']
    expected=found=0
    for c in cases:
        events=cluster_events(records(c['texts'],c['urls']))
        assert len(events)==c['expected_events']
        expected+=c['expected_events'];found+=len(events)
        assert all(e.metadata()['independent_confirmation_count'] is None for e in events)
    assert expected==found==7
    from tools.daily_event_eval import evaluate
    result=evaluate()
    assert result['gold_event_recall']==1.0 and result['duplicate_output_rate']==0.0
    assert all(c['exact_gold_groups']==c['observed_groups'] or sorted(c['exact_gold_groups'])==sorted(c['observed_groups']) for c in result['cases'])


def test_previous_brief_suppresses_recurrence_but_not_changed_deadline():
    first=cluster_events(records(['Deadline is 2026-10-20.']))[0]
    history=[{**first.metadata(),'brief_ref':'brief_prior:1'}]
    repeated=cluster_events(records(['Deadline is 2026-10-20.'],first_discovered_at='2026-10-14T09:00:00Z'),history=history)[0]
    changed=cluster_events(records(['Correction: deadline is 2026-10-22.']),history=history)[0]
    assert repeated.novelty=='repeated' and changed.novelty=='changed'
    assert repeated.metadata()['last_surfaced_at'] is None


def test_title_change_is_metadata_and_explicit_revision_is_not_deduplicated():
    a=records(['The protocol supports retrieval cache.'],title='Old title')[0]
    b=records(['The protocol supports retrieval cache.'],title='New title')[0]
    assert len(cluster_events((a,b)))==1
    revision=records(['The protocol supports retrieval cache.'],event_revision='correction-v2')[0]
    assert len(cluster_events((a,revision)))==2


def test_conflicts_and_truncated_candidates_stay_visible():
    a=records(['Submission closes on 2026-10-20.'],conflict_group='deadline',conflict_value='20')[0]
    b=records(['Submission closes on 2026-10-22.'],conflict_group='deadline',conflict_value='22')[0]
    assert len(cluster_events((a,b)))==2 and all(e.conflict for e in cluster_events((a,b)))
    a=records(['Long identical partial source excerpt.'],content_truncated=True)[0]
    b=records(['Long identical partial source excerpt.'],content_truncated=True,title='Other uncertain source')[0]
    assert len(cluster_events((a,b)))==2


def test_distinct_explicit_events_do_not_merge_identical_announcements():
    text='Applications are now open for this programme.'
    events=cluster_events(records([text,text],['https://primary.example.test/alpha','https://primary.example.test/beta']))
    assert len(events)==2 and events[0].event_ref!=events[1].event_ref
