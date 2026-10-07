"""Paired observed-task quality/cost comparison; never a release authority."""
from decimal import Decimal
from prm.storage.postgres import StorageError


def compare_task_observations(baseline,candidate,*,minimum_tasks=20):
    def index(rows):
        if not isinstance(rows,list) or len(rows)<minimum_tasks:raise StorageError('fixed user-task holdout is incomplete')
        result={}
        for row in rows:
            required={'case_id','input_digest','source_snapshot','scope_digest','language','prompt_version','tool_version',
                      'requested_model','observed_model','task_kind','succeeded','supported_claims','total_claims','cost_microdollars','duration_ms'}
            if not isinstance(row,dict) or not required<=set(row) or row['case_id'] in result:raise StorageError('complete unique observed task receipt required')
            if row['requested_model']!=row['observed_model']:raise StorageError('observed model differs from the fixed comparison')
            if type(row['succeeded'])is not bool or row['task_kind'] not in {'simple','complex'}:raise StorageError('actual task outcome required')
            if not 0<=row['supported_claims']<=row['total_claims'] or row['duration_ms']<0:raise StorageError('invalid observed task metrics')
            if row['cost_microdollars'] is not None and (type(row['cost_microdollars'])is not int or row['cost_microdollars']<0):raise StorageError('known nonnegative task cost or explicit unknown required')
            result[row['case_id']]=row
        return result
    left,right=index(baseline),index(candidate)
    if set(left)!=set(right):raise StorageError('paired holdout cases changed')
    for key in left:
        for field in ('input_digest','source_snapshot','scope_digest','language','task_kind'):
            if left[key][field]!=right[key][field]:raise StorageError('paired input/source/permission/language mismatch')
    def score(rows):
        kinds={kind:[row for row in rows if row['task_kind']==kind] for kind in ('simple','complex')}
        total=sum(row['total_claims'] for row in rows);supported=sum(row['supported_claims'] for row in rows)
        return {'tasks':len(rows),'simple_success_rate':sum(row['succeeded'] for row in kinds['simple'])/len(kinds['simple']) if kinds['simple'] else None,
                'complex_success_rate':sum(row['succeeded'] for row in kinds['complex'])/len(kinds['complex']) if kinds['complex'] else None,
                'claim_support_rate':supported/total if total else None,
                'known_cost_microdollars':sum(row['cost_microdollars'] or 0 for row in rows),
                'unknown_cost_tasks':sum(row['cost_microdollars'] is None for row in rows),
                'latency_ms':sorted(row['duration_ms'] for row in rows)[max(0,int(len(rows)*.95)-1)]}
    before,after=score(list(left.values())),score(list(right.values()))
    comparable=all(before[key] is not None and after[key] is not None and after[key]>=before[key] for key in ('simple_success_rate','complex_success_rate','claim_support_rate'))
    costs_known=not before['unknown_cost_tasks'] and not after['unknown_cost_tasks']
    savings=before['known_cost_microdollars']-after['known_cost_microdollars'] if comparable and costs_known else None
    return {'baseline':before,'candidate':after,'quality_non_regressed':comparable,'savings_microdollars':savings,
            'thresholds_met':after['simple_success_rate'] is not None and after['complex_success_rate'] is not None and after['claim_support_rate'] is not None
                and after['simple_success_rate']>=.95 and after['complex_success_rate']>=.90 and after['claim_support_rate']>=.98,
            'evidence_layer':'observed_dataset_only','human_acceptance':False,'release_authority':False}
