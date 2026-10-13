"""Role policy expiry/privacy, actual paired receipts, explicit cost units."""
from datetime import datetime,timedelta,timezone
from dataclasses import replace
import pytest
from tests.pai_runtime_fixtures import pai,allow,request
from prm.runtime.profiles import ModelProfiles,RolePolicy
from prm.storage.postgres import StorageError


def policy(now,**changes):
    return RolePolicy(version='fixture_policy_v1',checked_at=now-timedelta(minutes=1),expires_at=now+timedelta(days=1),allowed_data_classes=('user_provided',),**changes)


def test_role_selection_privacy_expiry_and_missing_boolean_receipt(pai):
    base=pai.root.model_endpoint;cheap=replace(base,connection_ref='connection_candidate')
    profiles=ModelProfiles({'balanced':{'chat':base,'planner':base},'economical':{'chat':cheap}},policies={'balanced':{'chat':policy(pai.now),'planner':policy(pai.now)},'economical':{'chat':policy(pai.now)}},comparison_receipts={'chat':{'quality_non_regressed':True}},root=pai.root)
    assert profiles.select(role='chat',quality='economical')==base
    assert profiles.select(role='planner')==base
    with pytest.raises(StorageError):profiles.select(role='judge')
    with pytest.raises(StorageError):profiles.select(role='chat',data_classes=('private_archive',))
    with pytest.raises(StorageError):profiles.select(role='chat',now=pai.now+timedelta(days=2))
    assert not pai.requests


def test_preflight_fallback_is_allowlisted_cooldown_survives_restart_and_unknown_never_retries(pai):
    base=pai.root.model_endpoint;strong=replace(base,connection_ref='connection_strong')
    profiles={'balanced':{'chat':base},'maximum':{'chat':strong}}
    policies={'balanced':{'chat':policy(pai.now,fallback_qualities=('maximum',),max_candidates=2)},'maximum':{'chat':policy(pai.now)}}
    registry=ModelProfiles(profiles,policies=policies,root=pai.root)
    registry.unavailable(role='chat',quality='balanced',outcome='not_attempted')
    assert ModelProfiles(profiles,policies=policies,root=pai.root).select(role='chat')==strong
    with pytest.raises(StorageError):registry.unavailable(role='chat',quality='maximum',outcome='unknown')
    assert not pai.requests


def test_native_chat_final_guard_rejects_private_history_under_user_only_policy(pai):
    root=pai.root;root.model_profile_registry=ModelProfiles({'balanced':{'chat':root.model_endpoint}},policies={'balanced':{'chat':policy(pai.now)}},root=root);root.quality_profile='balanced'
    allow(pai,'model.generate',root.model_resource_ref,'user_provided','answer.request')
    allow(pai,'model.context_egress',root.model_resource_ref,'model_generated','dialogue.history')
    assert request(pai,120010,'/chat Synthetic first')[1]['status']=='ok'
    request(pai,120011,'/chat Synthetic second')
    assert len(pai.requests)==1


def test_currency_peak_offpeak_subscription_unknown_and_expiry_replay(pai):
    from prm.runtime.cost_cache import CostCacheRuntime
    cache=CostCacheRuntime(pai.root)
    for version,currency,mode in [('usd','USD','meter'),('eur','EUR','meter'),('sub','USD','subscription')]:
        cache.register_tariff(provider='provider_openai',model='fixture_model',version=version,input_per_million=2,cached_input_per_million=1,output_per_million=4,source_ref='https://example.test/tariff',checked_at=pai.now-timedelta(days=1),valid_until=pai.now+timedelta(days=1),currency=currency,billing_mode=mode,subscription_amount=10 if mode=='subscription' else None,offpeak={'start_hour_utc':22,'end_hour_utc':6,'input':1,'cache_read':.5,'output':2})
    usage={'input':100,'cached_input':20,'output':40,'reasoning':None,'cache_write':None,'semantics':'openai_chat_output_includes_reasoning'}
    params=dict(task_ref='fixture_cost',provider='provider_openai',model='fixture_model',usage=usage,latency_ms=1,outcome='accepted')
    assert cache.record(**params,attempt_ref='peak',tariff_version='usd',observed_at=pai.now.replace(hour=12))==340
    assert cache.record(**params,attempt_ref='off',tariff_version='usd',observed_at=pai.now.replace(hour=23))==170
    assert cache.record(**params,attempt_ref='peak',tariff_version='usd',observed_at=pai.now+timedelta(days=3))==340
    assert cache.record(**params,attempt_ref='eur',tariff_version='eur') is None
    assert cache.record(**params,attempt_ref='sub',tariff_version='sub') is None
    assert cache.record(**params,attempt_ref='unknown',tariff_version=None) is None
    view=cache.billing_view()
    assert view['usage']['unknown_attempts']==3 and view['subscription_paid'] is None and view['overage_billed'] is None and not view['invoice_verified']


def test_promotion_requires_actual_paired_attempts_and_costs_bound_to_endpoint(pai):
    from prm.runtime.cost_cache import CostCacheRuntime
    from prm.runtime.profiles import identity_digest,observed_scope_digest
    from dataclasses import asdict
    root=pai.root;base=root.model_endpoint;cheap=replace(base,connection_ref='connection_candidate');root.quality_profile='balanced'
    profiles=ModelProfiles({'balanced':{'chat':base},'economical':{'chat':cheap}},policies={'balanced':{'chat':policy(pai.now)},'economical':{'chat':policy(pai.now)}},root=root)
    root.model_profile_registry=profiles
    allow(pai,'model.generate',root.model_resource_ref,'user_provided','answer.request')
    allow(pai,'model.generate',root.model_resource_ref,'user_provided','answer.request',connection=cheap.connection_ref)
    cache=CostCacheRuntime(root)
    for version,rate in [('base',2),('cheap',1)]:cache.register_tariff(provider=base.provider_ref,model=base.model,version=version,input_per_million=rate,cached_input_per_million=rate,output_per_million=rate,source_ref='https://example.test/synthetic-pair',valid_until=pai.now+timedelta(days=1))
    pairs=[]
    for side,endpoint in [('base',base),('cheap',cheap)]:
        root.tariff_version=side;rows=[]
        for i in range(20):
            task=root.queue.store.put(root.owner_ref,'conversation',f'paired_{side}_{i}',{'query':'Synthetic paired question '+str(i)},expected_version=0)
            decision=allow_decision(pai,endpoint,'paired_op_'+side+'_'+str(i))
            client=root.scoped_client(endpoint,groups=((decision,),),task_ref=task.object_id,attempt_ref=decision.operation_ref)
            try:receipt=client.complete_with_receipt(prompt=task.payload['query'],system='Synthetic fixture',max_tokens=30,category='chat',authorization=decision,data_class='user_provided',owner_ref=root.owner_ref,connection_ref=endpoint.connection_ref,resource_ref=root.model_resource_ref)
            finally:decision.reservation.abandon_before_transport()
            assert receipt.text=='Синтетический ответ на текущий вопрос.'
            rows.append({'case_id':str(i),'input_digest':task.digest,'model_input_digest':client.input_digest,'attempt_ref':client.attempt_ref,'usage_ref':decision.operation_ref,'source_snapshot':root.queue.store.get(root.owner_ref,'conversation',client.attempt_ref).payload['context_digest'],'scope_digest':observed_scope_digest([asdict(decision.reservation._request)]),'language':'ru','prompt_version':'v1','tool_version':'v1','requested_model':base.model,'observed_model':base.model,'task_kind':'simple' if i<10 else 'complex','succeeded':True,'supported_claims':1,'total_claims':1,'cost_microdollars':int(cache.task_cost(task.object_id)['known_microdollars']),'duration_ms':receipt.duration_ms})
        pairs.append(rows)
    assert len(pai.requests)==40
    reference=profiles.record_comparison(role='chat',baseline=pairs[0],candidate=pairs[1],expires_at=pai.now+timedelta(days=1))
    profiles.comparisons['chat']=reference
    assert profiles.select(role='chat',quality='economical')==cheap
    tampered=[dict(r) for r in pairs[1]];tampered[0]['usage_ref']='other'
    with pytest.raises(StorageError):profiles.record_comparison(role='chat',baseline=pairs[0],candidate=tampered,expires_at=pai.now+timedelta(days=1))
    from prm.runtime.deletion import delete_derived_in
    with root.queue.store.transaction() as tx:delete_derived_in(tx,owner=root.owner_ref,namespace='conversation',object_ref=pairs[0][0]['attempt_ref'])
    assert profiles.select(role='chat',quality='economical')==base


def allow_decision(pai,endpoint,reference):
    from prm.capabilities import AuthorizationRequest
    return pai.root.registry.authorize_and_reserve(AuthorizationRequest(owner_ref=pai.root.owner_ref,connection_ref=endpoint.connection_ref,capability='model.generate',resource_ref=pai.root.model_resource_ref,operation='model_egress',data_class='user_provided',provider_ref=endpoint.provider_ref,purpose='answer.request',operation_ref=reference),upper_bound=500)


def test_expired_primary_policy_cannot_open_fresh_fallback_or_vague_promotion(pai):
    base=pai.root.model_endpoint;strong=replace(base,connection_ref='connection_strong')
    expired=RolePolicy('old',pai.now-timedelta(days=3),pai.now-timedelta(days=1),('user_provided',),('maximum',),2)
    registry=ModelProfiles({'balanced':{'chat':base},'maximum':{'chat':strong}},policies={'balanced':{'chat':expired},'maximum':{'chat':policy(pai.now)}})
    with pytest.raises(StorageError):registry.select(role='chat')
    assert not pai.requests


def test_runtime_profile_policy_config_is_offline_and_complete(pai):
    from prm.runtime.config import validate_runtime_config
    from prm.runtime.composition import runtime_from_config
    from dataclasses import asdict
    endpoint=asdict(pai.root.model_endpoint);endpoint.pop('token');endpoint.pop('capabilities')
    value={'version':'v1','checked_at':(pai.now-timedelta(minutes=1)).isoformat(),'expires_at':(pai.now+timedelta(days=1)).isoformat(),'allowed_data_classes':['user_provided']}
    config={'owner_ref':pai.root.owner_ref,'owner_chat_id':'42','budget_refs':['request_full','job_full','day_full','month_full'],'job_budget':True,'local_services':True,'model_profiles':{'balanced':{'chat':endpoint,'planner':endpoint}},'profile_policies':{'balanced':{'chat':value,'planner':value}}}
    validate_runtime_config(config)
    root=runtime_from_config(config,target=pai.pg.app,settings=pai.root.settings)
    assert root.endpoint_for('planner')==root.endpoint_for('chat') and root.endpoint_for('research') is None
    assert {'projects','archive','budget'}<=set(root.services) and not pai.requests
    bad={**config,'profile_policies':{'balanced':{'chat':value}}}
    with pytest.raises(StorageError):validate_runtime_config(bad)


def test_media_cannot_inherit_chat_profile_or_bypass_role_expiry(pai):
    from prm.runtime.media import MediaRuntime
    from prm.runtime.vision import VisionAdapter
    from prm.runtime.speech import SpeechTranscriber
    root=pai.root;root.model_profile_registry=ModelProfiles({'balanced':{'chat':root.model_endpoint}},policies={'balanced':{'chat':policy(pai.now)}},root=root);root.quality_profile='balanced'
    media=MediaRuntime(root,temporary_root=pai.path/'role-media')
    image=media.ingest(content=b'\x89PNG\r\n\x1a\nsynthetic',kind='image',mime_type='image/png')
    voice=media.ingest(content=b'OggSsynthetic',kind='voice',mime_type='audio/ogg')
    with pytest.raises(StorageError):VisionAdapter(root,endpoint=root.model_endpoint,upper_bound=0)(image,'Synthetic',media.path/image.media_ref)
    with pytest.raises(StorageError):SpeechTranscriber(root,endpoint=root.model_endpoint,upper_bound=0)(voice,media.path/voice.media_ref)
    assert not pai.requests
