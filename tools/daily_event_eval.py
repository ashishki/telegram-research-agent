#!/usr/bin/env python3
"""Frozen public/synthetic deterministic event baseline; no provider I/O."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json
from prm.source_contracts import SourceResource,SourceBatch
from prm.event_clusters import cluster_events,VERSION


def evaluate():
    path=Path(__file__).resolve().parents[1]/'tests/fixtures/daily07_events.json'
    raw=path.read_bytes();fixture=json.loads(raw);observations=[]
    for case in fixture['cases']:
        rows=[{'evidence_id':case['id']+'_'+str(i),'canonical_url':case['urls'][i%len(case['urls'])],
               'source_url':'https://t.me/synthetic/'+str(i),'support_span':text,'source_version':'v'+str(i)} for i,text in enumerate(case['texts'])]
        batch=SourceBatch.from_items(rows,SourceResource('owner_fixture','resource_fixture','archive','private_archive'),
            checked_at=datetime(2026,10,14,tzinfo=timezone.utc),completeness='complete',omitted_count=0)
        events=cluster_events(batch.items)
        identities=[r.external_ref for r in batch.items]
        # Frozen cases declare either one syndicated group or all distinct
        # events. Compare exact member sets, not merely equal output counts.
        gold_groups=[frozenset(identities)] if case['expected_events']==1 else [frozenset((i,)) for i in identities]
        predicted=[frozenset(r.external_ref for r in e.records) for e in events]
        observations.append({'case_id':case['id'],'input_records':len(rows),'gold_events':case['expected_events'],
            'observed_events':len(events),'preserved_events':sum(g in predicted for g in gold_groups),
            'exact_gold_groups':[sorted(g) for g in gold_groups],
            'observed_groups':[sorted(g) for g in predicted],
            'duplicate_outputs':max(0,len(events)-case['expected_events']),
            'independent_confirmation_count':None,'event_revisions':[e.revision for e in events]})
    gold=sum(o['gold_events'] for o in observations);outputs=sum(o['observed_events'] for o in observations)
    return {'schema_version':'assistant.daily_event_eval.v1','fixture_sha256':hashlib.sha256(raw).hexdigest(),
        'dataset_role':fixture['dataset_role'],'mechanism':VERSION,'cases':observations,
        'gold_event_recall':sum(o['preserved_events'] for o in observations)/gold,
        'duplicate_output_rate':sum(o['duplicate_outputs'] for o in observations)/outputs,
        'gold_events':gold,'output_events':outputs,'semantic_clustering':False,
        'human_usefulness':None,'provider_integration':False,'holdout_acceptance':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    result=evaluate();Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('gold_events','output_events','gold_event_recall','duplicate_output_rate','fixture_sha256')}))
