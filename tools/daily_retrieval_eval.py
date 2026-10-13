#!/usr/bin/env python3
"""Offline frozen synthetic comparison; never opens the operator archive."""
import argparse,hashlib,json,math,sqlite3,tempfile,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT))

def evaluate():
    from tests.test_daily_retrieval import corpus,FIXTURE
    from db.archive_search import search_telegram_archive_fts
    from db.archive_retrieval import retrieve_archive
    from db.archive_vector import build_archive_vector_index
    import db.archive_vector as legacy_vector
    conn,value=corpus();output={}
    try:
        with tempfile.TemporaryDirectory(prefix='daily-retrieval-') as temp:
            index=Path(temp)/'derived.sqlite';build_archive_vector_index(conn,index_path=index)
            for mode in ('fts_baseline','current_hashed_fusion','expanded_fts','expanded_hashed_fusion'):
                rows=[]
                for case in value['cases']:
                    if mode=='fts_baseline':items=search_telegram_archive_fts(conn,case['query'],filters=case['filters'],limit=20)
                    elif mode=='current_hashed_fusion':
                        # Preserve the current hashed algorithm with its original
                        # FTS baseline, only in this isolated synthetic process.
                        original=legacy_vector.search_telegram_archive;legacy_vector.search_telegram_archive=search_telegram_archive_fts
                        try:items=legacy_vector._search_telegram_archive_hybrid_baseline(conn,case['query'],vector_index_path=index,filters=case['filters'],limit=20,vector_policy='always')
                        finally:legacy_vector.search_telegram_archive=original
                    else:items=retrieve_archive(conn,case['query'],filters=case['filters'],limit=20,vector_index_path=index if mode.endswith('fusion') else None).items
                    ids=[str(i.post_id) for i in items];gold=case['relevance'];relevant=set(gold)
                    recall=len(set(ids[:20])&relevant)/len(relevant) if relevant else None
                    rank=next((k for k,i in enumerate(ids,1) if i in gold),None)
                    dcg=sum((2**gold.get(i,0)-1)/math.log2(k+2) for k,i in enumerate(ids[:10]))
                    ideal=sum((2**v-1)/math.log2(k+2) for k,v in enumerate(sorted(gold.values(),reverse=True)[:10]))
                    rows.append({'id':case['id'],'language':case['language'],'category':case['category'],'result_ids':ids,
                        'recall_at_20':recall,'ndcg_at_10':dcg/ideal if ideal else None,'mrr':(1/rank if rank else 0) if relevant else None,
                        'no_answer_false_positive':bool(ids) if not relevant else None})
                metrics={}
                for language in ('all','ru','en'):
                    subset=[r for r in rows if language=='all' or r['language']==language]
                    metrics[language]={key:sum(vals)/len(vals) if vals else None for key in ('recall_at_20','ndcg_at_10','mrr','no_answer_false_positive') if (vals:=[r[key] for r in subset if r[key] is not None])}
                output[mode]={'metrics':metrics,'rows':rows}
        return {'schema_version':'assistant.daily_retrieval_eval.v1','fixture_sha256':hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
            'authority':value['authority'],'modes':output,'learned_candidate':value['learned_candidate'],
            'adoption':'expanded FTS local mechanics; hashed fusion not enabled automatically due no-answer false positives; synthetic labels are not human gold/independent holdout',
            'metric_scope':'MRR/recall/nDCG answerable cases only; no-answer false positives separate; physical duplicate gold refs may be collapsed by candidate dedup'}
    finally:conn.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=evaluate();args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({mode:data['metrics'] for mode,data in result['modes'].items()},ensure_ascii=False))
