#!/usr/bin/env python3
"""Matched pre-frozen synthetic facts; lexical precision is not provider quality."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from prm.research_blocks import fact_proof
from prm.runtime.research_answer import accepted_answer

def evaluate():
    path=ROOT/'evals/synthesis/daily-20261013.json';value=json.loads(path.read_text());rows=[]
    for case in value['cases']:
        evidence=[{'source_url':'https://example.test/alpha','support_span':case['quote']}]
        raw=json.dumps({'findings':[{k:case[k] for k in ('text','source_url','quote')}]},ensure_ascii=False)
        rows.append({'id':case['id'],'expected_supported':case['expected_supported'],
            'legacy_all_or_none_admitted':accepted_answer(raw,evidence) is not None,
            'block_admitted':fact_proof(case['text'],case['quote'],case['source_url'],evidence) is not None})
    metrics={}
    for mode in ('legacy_all_or_none_admitted','block_admitted'):
        tp=sum(r[mode] and r['expected_supported'] for r in rows);fp=sum(r[mode] and not r['expected_supported'] for r in rows);fn=sum(not r[mode] and r['expected_supported'] for r in rows)
        metrics[mode]={'groundedness_precision':tp/(tp+fp) if tp+fp else None,'required_fact_recall':tp/(tp+fn) if tp+fn else None,
            'false_reject_count':fn,'false_accept_count':fp}
    return {'schema_version':'assistant.daily_synthesis_eval.v1','fixture_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'authority':value['authority'],'rows':rows,'metrics':metrics,'semantic_translation':'only fixed bounded vocabulary; other paraphrases remain unverified'}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();value=evaluate()
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');print(json.dumps(value['metrics']))
