"""Versioned role/privacy policy and observed paired promotion; never authority."""
from dataclasses import dataclass,asdict
from datetime import datetime,timezone,timedelta
import hashlib,json
from prm.storage.postgres import StorageError,StateConflict
from prm.source_contracts import CLASSES

ROLES=frozenset({'chat','planner','research','brief_editorial','extraction','vision','speech','media','judge'})
QUALITIES=frozenset({'economical','balanced','maximum'})


def aware(value):
    if isinstance(value,str):value=datetime.fromisoformat(value)
    if not isinstance(value,datetime) or value.tzinfo is None:raise StorageError('aware policy timestamp required')
    return value


def endpoint_identity(endpoint):
    return {'provider':endpoint.provider_ref,'connection':endpoint.connection_ref,'endpoint':endpoint.endpoint,'model':endpoint.model}


def identity_digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


@dataclass(frozen=True)
class RolePolicy:
    version: str
    checked_at: datetime
    expires_at: datetime
    allowed_data_classes: tuple[str,...]
    fallback_qualities: tuple[str,...] = ()
    max_candidates: int = 1
    cooldown_seconds: int = 60

    def __post_init__(self):
        if not isinstance(self.version,str) or not 0<len(self.version)<=128:raise StorageError('explicit role policy version required')
        if aware(self.checked_at)>=aware(self.expires_at):raise StorageError('bounded policy review validity required')
        if not isinstance(self.allowed_data_classes,tuple) or not self.allowed_data_classes or not set(self.allowed_data_classes)<=CLASSES:raise StorageError('explicit allowed role data classes required')
        if not isinstance(self.fallback_qualities,tuple) or len(set(self.fallback_qualities))!=len(self.fallback_qualities) or not set(self.fallback_qualities)<=QUALITIES:raise StorageError('explicit fallback allowlist required')
        if type(self.max_candidates)is not int or not 1<=self.max_candidates<=3 or type(self.cooldown_seconds)is not int or not 1<=self.cooldown_seconds<=3600:raise StorageError('bounded preflight attempts/cooldown required')

    @classmethod
    def from_mapping(cls,value):
        value=dict(value)
        for key in ('checked_at','expires_at'):value[key]=aware(value[key])
        for key in ('allowed_data_classes','fallback_qualities'):
            if key in value:value[key]=tuple(value[key])
        return cls(**value)
    def current(self,now,classes):return self.checked_at<=now<self.expires_at and set(classes)<=set(self.allowed_data_classes)
    def digest(self):
        value=asdict(self);value.update(checked_at=self.checked_at.isoformat(),expires_at=self.expires_at.isoformat())
        return identity_digest(value)


class ModelProfiles:
    def __init__(self,profiles,*,baseline='balanced',comparison_receipts=None,policies=None,root=None):
        if baseline not in QUALITIES or baseline not in profiles:raise StorageError('explicit baseline profile required')
        if set(profiles)-QUALITIES or any(set(value)-ROLES for value in profiles.values()):raise StorageError('unsupported explicit model profile or role')
        self.profiles={q:dict(v) for q,v in profiles.items()};self.baseline=baseline;self.comparisons=dict(comparison_receipts or {});self.root=root
        self.policies=None if policies is None else {q:{r:RolePolicy.from_mapping(v) if isinstance(v,dict) else v for r,v in roles.items()} for q,roles in policies.items()}
        if self.policies is not None and (set(self.policies)!=set(self.profiles) or any(set(self.policies[q])!=set(self.profiles[q]) for q in self.profiles)):raise StorageError('every configured endpoint requires its exact role policy')
        self.cooldowns={}
    def binding(self,quality,role):
        endpoint=self.profiles[quality][role];policy=self.policies[quality][role] if self.policies is not None else None
        return {'quality':quality,'role':role,'endpoint':endpoint_identity(endpoint),'policy_digest':policy.digest() if policy else 'legacy_unversioned'}
    def _promoted(self,role):
        reference=self.comparisons.get(role)
        if self.root is None or not isinstance(reference,str):return False
        try:
            with self.root.queue.store.transaction() as tx:
                item=tx.get(self.root.owner_ref,'result',reference)
                if not item:return False
                value=item.payload;now=tx.conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
                if aware(value['expires_at'])<=now or value['baseline_binding']!=self.binding(self.baseline,role) or value['candidate_binding']!=self.binding('economical',role):return False
                _validate_observations(tx,self.root,value['baseline'],value['candidate'],(value['baseline_binding'],value['candidate_binding']))
                from .evaluation import compare_task_observations
                score=compare_task_observations(value['baseline'],value['candidate'])
                return score['quality_non_regressed'] and score['thresholds_met'] and score['savings_microdollars'] is not None and score['savings_microdollars']>0
        except (StorageError,ValueError,KeyError,TypeError):return False
    def _cooldown(self,key,now):
        if self.root is None:return self.cooldowns.get(key,now)<=now
        item=self.root.queue.store.get(self.root.owner_ref,'conversation','profile_cooldown_'+key)
        return not item or aware(item.payload['until'])<=now
    def select(self,*,role,quality='balanced',manual_model=None,data_classes=('user_provided',),now=None):
        if role not in ROLES or quality not in QUALITIES:raise StorageError('explicit supported workload role and quality required')
        now=aware(now or datetime.now(timezone.utc));chosen=self.baseline if quality=='economical' and not self._promoted(role) else quality
        candidates=[chosen]
        if manual_model is not None:
            candidates=[q for q in self.profiles if role in self.profiles[q] and self.profiles[q][role].model==manual_model]
            if len(candidates)!=1:raise StorageError('manual selection requires one configured endpoint')
        elif self.policies is not None and role in self.policies.get(chosen,{}):
            policy=self.policies[chosen][role]
            if not policy.checked_at<=now<policy.expires_at:raise StorageError('expired role policy cannot authorize automatic alternatives')
            candidates+=list(policy.fallback_qualities);candidates=candidates[:policy.max_candidates]
        for q in dict.fromkeys(candidates):
            endpoint=self.profiles.get(q,{}).get(role)
            if endpoint is None:continue
            if self.policies is not None:
                policy=self.policies[q][role]
                if not policy.current(now,data_classes):continue
            if self._cooldown(identity_digest(self.binding(q,role)),now):return endpoint
        raise StorageError('configured role/policy unavailable; no implicit provider fallback')
    def check(self,endpoint,*,role,data_classes,now=None):
        now=aware(now or datetime.now(timezone.utc))
        if self.policies is None:return
        matches=[q for q in self.profiles if self.profiles[q].get(role)==endpoint]
        if not matches or any(not self.policies[q][role].current(now,data_classes) for q in matches):raise StorageError('selected model role/privacy policy unavailable')
    def unavailable(self,*,role,quality,outcome):
        if outcome not in {'not_attempted','rejected'}:raise StorageError('unknown transport never authorizes a fallback or retry')
        if self.policies is None:raise StorageError('versioned cooldown policy required')
        now=datetime.now(timezone.utc);key=identity_digest(self.binding(quality,role));until=now+timedelta(seconds=self.policies[quality][role].cooldown_seconds)
        if self.root is None:self.cooldowns[key]=until;return
        ref='profile_cooldown_'+key
        with self.root.queue.store.transaction() as tx:
            old=tx.get(self.root.owner_ref,'conversation',ref)
            tx.put(self.root.owner_ref,'conversation',ref,{'until':until.isoformat(),'outcome':outcome},expected_version=old.version if old else 0)
    def record_comparison(self,*,role,baseline,candidate,expires_at):
        if self.root is None:raise StorageError('durable observed comparison backend required')
        expires_at=aware(expires_at)
        if expires_at<=datetime.now(timezone.utc):raise StorageError('future comparison expiry required')
        root=self.root
        with root.queue.store.transaction() as tx:
            from .deletion import lineage_lock
            lineage_lock(tx.conn,root.owner_ref)
            _validate_observations(tx,root,baseline,candidate,(self.binding(self.baseline,role),self.binding('economical',role)))
            from .evaluation import compare_task_observations
            score=compare_task_observations(baseline,candidate)
            value={'baseline':baseline,'candidate':candidate,'baseline_binding':self.binding(self.baseline,role),'candidate_binding':self.binding('economical',role),'expires_at':expires_at.isoformat(),'score':score}
            for rows,binding in ((baseline,value['baseline_binding']),(candidate,value['candidate_binding'])):
                if any(r['observed_model']!=binding['endpoint']['model'] for r in rows):raise StorageError('comparison endpoint model differs')
            reference='profile_comparison_'+identity_digest(value)
            old=tx.get(root.owner_ref,'result',reference)
            if old is None:tx.put(root.owner_ref,'result',reference,value,expected_version=0)
            for row in baseline+candidate:
                tx.conn.execute('INSERT INTO pa_memory.dependencies VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(root.owner_ref,'conversation',row['attempt_ref'],'result',reference))
        return reference


def _validate_observations(tx,root,baseline,candidate,bindings):
    if not isinstance(baseline,list) or not isinstance(candidate,list):raise StorageError('paired observed rows required')
    seen=set()
    for row in baseline+candidate:
        expected=bindings[0 if row in baseline else 1]['endpoint']
        ref=row.get('attempt_ref');observation=tx.get(root.owner_ref,'conversation',ref) if isinstance(ref,str) else None
        if ref in seen or not observation:raise StorageError('unique actual observation receipt required')
        seen.add(ref);value=observation.payload;actual=value.get('observation',{})
        if row['source_snapshot']!=value.get('context_digest') or not value.get('context_digest'):raise StorageError('actual paired context/source packet differs')
        task=tx.get(root.owner_ref,'conversation',value['task_ref'])
        if not task or task.digest!=row['input_digest'] or actual.get('provider_outcome')!='accepted' or actual.get('observed_model')!=row['observed_model'] or actual.get('requested_model')!=row['requested_model'] or value.get('input_digest')!=row.get('model_input_digest'):raise StorageError('paired receipt observation differs')
        usage_ref=row.get('usage_ref')
        if usage_ref not in value['operation_refs']:raise StorageError('usage must bind the actual operation')
        member=tx.conn.execute('SELECT request FROM pa_policy.members WHERE owner=%s AND operation_ref=%s',(root.owner_ref,usage_ref)).fetchone()
        if not member or (member['request']['provider_ref'],member['request']['connection_ref'])!=(expected['provider'],expected['connection']):raise StorageError('actual provider/connection differs from compared endpoint')
        members=tx.conn.execute('SELECT request FROM pa_policy.members WHERE owner=%s AND operation_ref=ANY(%s)',(root.owner_ref,value['operation_refs'])).fetchall()
        if row['scope_digest']!=observed_scope_digest(m['request'] for m in members):raise StorageError('actual paired privacy/resource scopes differ')
        usage=tx.conn.execute('SELECT cost_microdollars,task_ref,outcome,model FROM pa_cache.usage WHERE owner=%s AND attempt_ref=%s',(root.owner_ref,usage_ref)).fetchone()
        if not usage or usage['task_ref']!=value['task_ref'] or usage['outcome']!='accepted' or usage['model']!=row['observed_model'] or usage['cost_microdollars']!=row['cost_microdollars']:raise StorageError('observed task cost unavailable/different')
    for left,right in zip(baseline,candidate):
        if any(left[k]!=right[k] for k in ('prompt_version','tool_version')):raise StorageError('paired prompt/tool versions changed')


def observed_scope_digest(requests):
    fields=('capability','resource_ref','operation','data_class','purpose')
    return identity_digest(sorted({tuple(r[f] for f in fields) for r in requests}))
