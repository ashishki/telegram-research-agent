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

# Daily evidence is separate from the historical model comparison above.
import hashlib
import json
import re
from pathlib import Path

DAILY_GROUPS={'chat':40,'search':30,'brief':16,'dialogue':20,'lifecycle':14}
TRACE_METRICS=frozenset({'model_calls','write_calls','turn_count','binding_count','source_count','unknown_cost_attempts',
    'focus_preserved','history_present','source_verified','replay_blocked','paused','old_job_cancelled','new_job_queued','partial'})
SAFE_STATUSES=frozenset({'ok','provider_egress_required','confirmation_unavailable','generated_verified','denied','invalid',
    'partial','restored','cancelled','ambiguous','paused','unknown','succeeded','accepted','not_attempted'})


def daily_digest(value):
    try:raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    except (TypeError,ValueError,RecursionError):raise StorageError('invalid bounded daily evidence') from None
    if len(raw)>1048576:raise StorageError('daily evidence exceeds bound')
    return hashlib.sha256(raw).hexdigest()


def _daily_json(path):
    path=Path(path)
    with path.open('rb') as stream:raw=stream.read(1048577)
    if len(raw)>1048576:raise StorageError('daily evidence exceeds bound')
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError('duplicate')
            result[key]=value
        return result
    try:return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('constant')))
    except (ValueError,RecursionError):raise StorageError('invalid daily evidence JSON') from None


def _public_strings(value):
    """Reject credential/PII canaries even in explicitly synthetic packets."""
    if isinstance(value,dict):
        for key,item in value.items():
            if key.lower() in {'token','api_key','authorization','headers','password','owner_ref','account_ref','chat_id','raw_response'}:
                raise StorageError('private field forbidden in public daily evidence')
            _public_strings(item)
    elif isinstance(value,list):
        for item in value:_public_strings(item)
    elif isinstance(value,str):
        if len(value.encode())>48000 or re.search(r'(?i)bearer\s|sk-[a-z0-9_-]{12,}|private_canary|secret_canary|\b\d{8,}:[A-Za-z0-9_-]{20,}',value):
            raise StorageError('secret canary forbidden in public daily evidence')


def validate_daily_manifest(value):
    required={'schema_version','dataset_id','target_units','target_counts','independent_holdout_ready','public_visible_texts','cases'}
    if not isinstance(value,dict) or set(value)!=required or value['schema_version']!='assistant.daily_manifest.v1':
        raise StorageError('complete daily manifest required')
    if value['dataset_id']!='daily_synthetic_v1' or value['target_units']!=120 or value['target_counts']!=DAILY_GROUPS or value['independent_holdout_ready'] is not False:
        raise StorageError('full target and honest holdout state required')
    if not isinstance(value['public_visible_texts'],list) or len(value['public_visible_texts'])>100 or any(not isinstance(x,str) for x in value['public_visible_texts']):
        raise StorageError('bounded declared public texts required')
    cases=value['cases']
    if not isinstance(cases,list) or not 20<=len(cases)<=120:raise StorageError('first twenty native tasks required')
    ids=set();families={};sources={};groups={key:0 for key in DAILY_GROUPS}
    for case in cases:
        fields={'case_id','group','language','split','scenario_family','driver','turns','sources','expected','must_not_effects','binding_contract','receipt_contract'}
        if not isinstance(case,dict) or set(case)!=fields:raise StorageError('complete frozen daily case required')
        ref=case['case_id']
        if not isinstance(ref,str) or not re.fullmatch(r'DAILY-[0-9]{3}',ref) or ref in ids:raise StorageError('unique daily case identity required')
        ids.add(ref)
        if case['group'] not in groups or case['language'] not in {'ru','en'} or case['split'] not in {'train','dev','holdout'}:
            raise StorageError('typed daily group/language/split required')
        contract=case['receipt_contract']
        contract_fields={'required_tool','object_version','requested_model','observed_model','model_input_digests','turn_input_digests','view_kind'}
        if not isinstance(contract,dict) or set(contract)!=contract_fields or contract['object_version']!=1 or type(contract['object_version'])is not int or contract['requested_model']!='fixture_model' or contract['observed_model']!='fixture_model' or contract['view_kind'] not in {'assistant_turns','subsystem_events'}:
            raise StorageError('frozen native receipt contract required')
        for key in ('model_input_digests','turn_input_digests'):
            if not isinstance(contract[key],list) or len(contract[key])>20 or any(not isinstance(x,str) or not re.fullmatch('[a-f0-9]{64}',x) for x in contract[key]):raise StorageError('frozen input fingerprints required')
        if contract['turn_input_digests']!=[hashlib.sha256(t.encode()).hexdigest() for t in case['turns']]:raise StorageError('frozen turn input changed')
        driver=case['driver']
        tool='model.generate' if driver.startswith(('chat_','dialogue_')) else 'archive.synthesize' if driver.startswith('archive_') else 'brief.build' if driver.startswith('brief_') else 'control.resolve' if driver.startswith('control_') else 'watch.lifecycle' if driver=='watch_pause' else 'action.dispatch' if driver=='action_unknown_repeat' else None
        if contract['required_tool']!=tool or tool is None:raise StorageError('required driver tool contract changed')
        groups[case['group']]+=1
        if not isinstance(case['scenario_family'],str) or not case['scenario_family'] or not isinstance(case['driver'],str):raise StorageError('scenario and driver required')
        family=case['scenario_family']
        if family in families and families[family]!=case['split']:raise StorageError('scenario family leaked across dataset splits')
        families[family]=case['split']
        turns=case['turns']
        if not isinstance(turns,list) or not 1<=len(turns)<=20 or any(not isinstance(t,str) or not t.strip() for t in turns):raise StorageError('complete visible task turns required')
        if case['group']=='dialogue' and not 10<=len(turns)<=20:raise StorageError('whole ten-to-twenty-turn dialogue required')
        if not isinstance(case['sources'],list) or not 1<=len(case['sources'])<=16:raise StorageError('frozen source snapshot required')
        for source in case['sources']:
            if not isinstance(source,dict) or set(source)!={'source_id','text','sha256'} or not isinstance(source['source_id'],str) or not isinstance(source['text'],str):raise StorageError('complete source snapshot required')
            digest=hashlib.sha256(source['text'].encode()).hexdigest()
            if source['sha256']!=digest:raise StorageError('source snapshot digest changed')
            for key in (source['source_id'],digest):
                if key in sources and sources[key]!=case['split']:raise StorageError('source leaked across dataset splits')
                sources[key]=case['split']
        expected=case['expected']
        if not isinstance(expected,dict) or set(expected)!={'status','metrics'} or expected['status'] not in SAFE_STATUSES or not isinstance(expected['metrics'],dict) or set(expected['metrics'])-TRACE_METRICS:
            raise StorageError('typed expected task constraints required')
        for metric,number in expected['metrics'].items():
            if type(number) not in {int,bool} or type(number)is int and not 0<=number<=1000:raise StorageError('bounded metric constraint required')
        if case['must_not_effects']!=['unauthorized_write','provider_retry','private_export'] or case['binding_contract'] not in {'immutable_result','source_snapshot','durable_control','exact_action_receipt'}:
            raise StorageError('object binding and forbidden effects required')
    if set(f'DAILY-{i:03}' for i in range(1,21))-ids or any(n==0 or n>DAILY_GROUPS[g] for g,n in groups.items()):
        raise StorageError('required daily cases/groups missing')
    _public_strings(value);daily_digest(value)
    return value


def load_daily_manifest(path):return validate_daily_manifest(_daily_json(path))


def make_daily_trace(manifest,case,*,turns,objects,status,metrics,effects,duration_ms,cost_microdollars=None,errors=(),tool_results=(),model_observations=(),turn_bindings=()):
    """Projection only: publish declared synthetic text, never arbitrary payloads."""
    if case not in manifest['cases']:raise StorageError('case is not bound to manifest')
    allowed=set(manifest['public_visible_texts'])|set(case['turns'])|{s['text'] for s in case['sources']}
    visible=[]
    for turn in turns:
        if not isinstance(turn,dict) or set(turn)!={'role','text'} or turn['role'] not in {'user','assistant'} or not isinstance(turn['text'],str):raise StorageError('typed visible turn required')
        text=turn['text']
        _public_strings(text)
        if turn['role']=='user' and text not in case['turns']:raise StorageError('undeclared input cannot be exported')
        visible.append({'role':turn['role'],'text':text if text in allowed else None,'text_sha256':hashlib.sha256(text.encode()).hexdigest()})
    value={'schema_version':'assistant.daily_trace.v1','evidence_layer':'local_synthetic','provider_execution':False,
        'human_acceptance':False,'case_id':case['case_id'],'manifest_digest':daily_digest(manifest),'case_digest':daily_digest(case),
        'source_snapshots':[{k:s[k] for k in ('source_id','sha256')} for s in case['sources']],
        'visible_turns':visible,'objects':[dict(o) for o in objects],'outcome':{'status':status,'metrics':metrics},'effects':effects,
        'duration_ms':duration_ms,'cost_microdollars':cost_microdollars,'errors':list(errors),
        'tool_results':list(tool_results),'model_observations':list(model_observations),
        'turn_bindings':[dict(b) for b in turn_bindings],'view_kind':case['receipt_contract']['view_kind']}
    verify_daily_trace(manifest,value)
    return value


def verify_daily_trace(manifest,trace):
    validate_daily_manifest(manifest)
    fields={'schema_version','evidence_layer','provider_execution','human_acceptance','case_id','manifest_digest','case_digest',
        'source_snapshots','visible_turns','objects','outcome','effects','duration_ms','cost_microdollars','errors','tool_results','model_observations','turn_bindings','view_kind'}
    if not isinstance(trace,dict) or set(trace)!=fields or trace['schema_version']!='assistant.daily_trace.v1' or trace['evidence_layer']!='local_synthetic' or trace['provider_execution'] is not False or trace['human_acceptance'] is not False:
        raise StorageError('complete local synthetic trace required')
    case=next((c for c in manifest['cases'] if c['case_id']==trace['case_id']),None)
    if not case or trace['view_kind']!=case['receipt_contract']['view_kind'] or trace['manifest_digest']!=daily_digest(manifest) or trace['case_digest']!=daily_digest(case):raise StorageError('trace manifest/case binding changed')
    if trace['source_snapshots']!=[{k:s[k] for k in ('source_id','sha256')} for s in case['sources']]:raise StorageError('trace source evidence missing or changed')
    turns=trace['visible_turns'];users=[];allowed=set(manifest['public_visible_texts'])|set(case['turns'])|{s['text'] for s in case['sources']}
    if not isinstance(turns,list) or not 2<=len(turns)<=40:raise StorageError('visible trace turns missing')
    for index,turn in enumerate(turns):
        if not isinstance(turn,dict) or turn.get('role')!=('user' if index%2==0 else 'assistant'):raise StorageError('whole dialogue order changed')
        if not isinstance(turn,dict) or set(turn)!={'role','text','text_sha256'} or turn['role'] not in {'user','assistant'} or not isinstance(turn['text_sha256'],str) or not re.fullmatch('[a-f0-9]{64}',turn['text_sha256']):raise StorageError('complete typed visible turn required')
        if turn['text'] is not None:
            if not isinstance(turn['text'],str) or turn['text'] not in allowed or hashlib.sha256(turn['text'].encode()).hexdigest()!=turn['text_sha256']:raise StorageError('undeclared or changed visible text')
        if turn['role']=='user':users.append(turn['text'])
    if users!=case['turns'] or sum(t['role']=='assistant' for t in turns)!=len(users):raise StorageError('required whole dialogue turns missing')
    objects=trace['objects']
    if not isinstance(objects,list) or not 1<=len(objects)<=64:raise StorageError('typed object evidence missing')
    for item in objects:
        if (not isinstance(item,dict) or set(item)!={'kind','ref_digest','version','digest','turn_index','input_sha256','status'} or item['kind'] not in {'result','source','job','brief','action_receipt','action_proposal','subscription'}
            or type(item['version'])is not int or item['version']!=case['receipt_contract']['object_version']
            or type(item['turn_index'])is not int or not 1<=item['turn_index']<=len(case['turns'])
            or item['input_sha256']!=case['receipt_contract']['turn_input_digests'][item['turn_index']-1]
            or not isinstance(item['status'],str) or not re.fullmatch('[a-z_]{1,80}',item['status'])
            or any(not isinstance(item[k],str) or not re.fullmatch('[a-f0-9]{64}',item[k]) for k in ('ref_digest','digest'))):raise StorageError('invalid object/version evidence')
    required_kind={'immutable_result':'result','source_snapshot':'source','durable_control':'job','exact_action_receipt':'action_receipt'}[case['binding_contract']]
    if case['driver']=='watch_pause':required_kind='subscription'
    if not any(o['kind']==required_kind for o in objects):raise StorageError('intended object binding missing')
    outcome=trace['outcome']
    if not isinstance(outcome,dict) or set(outcome)!={'status','metrics'} or outcome['status'] not in SAFE_STATUSES or not isinstance(outcome['metrics'],dict) or set(outcome['metrics'])-TRACE_METRICS:raise StorageError('typed actual task outcome required')
    for number in outcome['metrics'].values():
        if type(number) not in {int,bool} or type(number)is int and not 0<=number<=1000:raise StorageError('invalid observed metric')
    effects=trace['effects']
    if not isinstance(effects,dict) or set(effects)!=set(case['must_not_effects']) or any(type(n)is not int or n<0 for n in effects.values()):raise StorageError('explicit forbidden-effect counts required')
    if type(trace['duration_ms'])is not int or trace['duration_ms']<0 or trace['cost_microdollars'] is not None and (type(trace['cost_microdollars'])is not int or trace['cost_microdollars']<0):raise StorageError('actual latency/known or unknown cost required')
    if not isinstance(trace['errors'],list) or len(trace['errors'])>20 or any(e not in {'provider_rejected','invalid_provider_response','unknown_outcome','scope_denied','source_outage','cancelled'} for e in trace['errors']):raise StorageError('bounded typed errors required')
    tools=trace['tool_results'];models=trace['model_observations']
    if not isinstance(tools,list) or not 1<=len(tools)<=32:raise StorageError('typed tool results missing')
    if len(tools)!=1 or not isinstance(tools[0],dict):raise StorageError('typed required tool receipt missing')
    if tools[0].get('tool')!=case['receipt_contract']['required_tool'] or tools[0].get('status')!=outcome['status']:
        raise StorageError('required tool/outcome relationship changed')
    expected_calls=outcome['metrics'].get('model_calls',0) if tools[0]['tool']=='model.generate' else outcome['metrics'].get('write_calls',0) if tools[0]['tool']=='action.dispatch' else 1
    if tools[0].get('calls')!=expected_calls:raise StorageError('tool call evidence conflicts with observed effects')
    for tool in tools:
        if not isinstance(tool,dict) or set(tool)!={'tool','status','calls'} or tool['tool'] not in {'model.generate','archive.synthesize','brief.build','control.resolve','watch.lifecycle','action.dispatch'} or tool['status'] not in SAFE_STATUSES or type(tool['calls'])is not int or not 0<=tool['calls']<=1000:raise StorageError('typed bounded tool result required')
    if not isinstance(models,list) or len(models)!=outcome['metrics'].get('model_calls',0):raise StorageError('actual model observations missing')
    if any(not isinstance(m,dict) for m in models):raise StorageError('typed model observation required')
    if sorted(m.get('input_digest','') for m in models)!=case['receipt_contract']['model_input_digests']:raise StorageError('observed model input is not the frozen task')
    for model in models:
        if not isinstance(model,dict) or set(model)!={'requested_model','observed_model','finish_reason','protocol','usage','input_digest','duration_ms','provider_outcome'} or model['provider_outcome']!='accepted' or model['protocol']!='chat_completions' or model['finish_reason']!='stop':raise StorageError('complete observed model identity/stop/usage required')
        if model['requested_model']!=case['receipt_contract']['requested_model'] or model['observed_model']!=case['receipt_contract']['observed_model']:raise StorageError('observed model identity changed')
        for key in ('requested_model','observed_model'):
            if not isinstance(model[key],str) or not re.fullmatch('[A-Za-z0-9_.:/-]{1,128}',model[key]):raise StorageError('actual requested/observed model required')
        if not isinstance(model['input_digest'],str) or not re.fullmatch('[a-f0-9]{64}',model['input_digest']) or type(model['duration_ms'])is not int or model['duration_ms']<0:raise StorageError('bounded model digest/latency required')
        usage=model['usage']
        if not isinstance(usage,dict) or set(usage)!={'input','output','cached_input','cache_write','reasoning','semantics'} or usage['semantics'] not in {'openai_chat_output_includes_reasoning','unknown_compatible_provider'}:raise StorageError('normalized observed usage required')
        for number in (usage[k] for k in ('input','output','cached_input','cache_write','reasoning')):
            if number is not None and (type(number)is not int or not 0<=number<=1000000):raise StorageError('invalid observed model usage')
        if usage['input'] is None or usage['output'] is None or usage['cached_input'] is not None and usage['cached_input']>usage['input'] or usage['reasoning'] is not None and usage['reasoning']>usage['output']:
            raise StorageError('accepted usage subsets inconsistent')
    bindings=trace['turn_bindings']
    if not isinstance(bindings,list) or len(bindings)!=len(case['turns']):raise StorageError('per-turn input/result bindings missing')
    if len(objects)!=len(bindings):raise StorageError('unrelated extra object evidence')
    for index,binding in enumerate(bindings,1):
        required={'turn_index','input_sha256','kind','ref_digest','version','digest','status'}
        if not isinstance(binding,dict) or set(binding)!=required or binding['turn_index']!=index or type(binding['turn_index'])is not int or binding['input_sha256']!=case['receipt_contract']['turn_input_digests'][index-1] or binding not in objects:
            raise StorageError('input/result/turn relationship changed')
        expected_kind='action_proposal' if case['driver']=='action_unknown_repeat' and index==1 else required_kind
        if binding['kind']!=expected_kind:raise StorageError('intended per-turn result kind changed')
    if bindings[-1]['status']!=outcome['status']:raise StorageError('final bound result/status differs')
    if required_kind=='source':
        source_objects=[o for o in objects if o['kind']=='source']
        for source in case['sources']:
            if not any(o['ref_digest']==hashlib.sha256(source['source_id'].encode()).hexdigest() and o['digest']==source['sha256'] for o in source_objects):raise StorageError('intended source ref/digest/version not bound')
    _public_strings(trace);daily_digest(trace)
    expected=case['expected']
    passed=outcome['status']==expected['status'] and all(type(outcome['metrics'].get(k))is type(v) and outcome['metrics'].get(k)==v for k,v in expected['metrics'].items()) and not any(effects.values())
    return {'mechanics_met':passed,'evidence_layer':'local_synthetic','quality_score':None,'provider_execution':False,'human_acceptance':False}


def verify_daily_trace_suite(manifest,traces):
    validate_daily_manifest(manifest)
    if not isinstance(traces,list) or len(traces)!=len(manifest['cases']):raise StorageError('required trace cases missing')
    if {t.get('case_id') for t in traces if isinstance(t,dict)}!={c['case_id'] for c in manifest['cases']}:raise StorageError('duplicate or omitted daily trace case')
    results=[verify_daily_trace(manifest,t) for t in traces]
    return {'cases':len(results),'mechanics_met':all(r['mechanics_met'] for r in results),'evidence_layer':'local_synthetic',
        'independent_holdout':False,'quality_score':None,'provider_execution':False,'human_acceptance':False}
