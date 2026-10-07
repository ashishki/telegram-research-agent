"""Deferred unique actual usage, unknown tariff and revoked cache evidence."""
from datetime import timedelta
from tests.pai_runtime_fixtures import pai,allow
from prm.runtime.cost_cache import CostCacheRuntime
from prm.capabilities import AuthorizationRequest


def test_usage_subsets_are_not_double_counted_and_unknown_is_not_zero(pai):
    costs=CostCacheRuntime(pai.root)
    costs.register_tariff(provider='provider_openai',model='fixture_model',version='fixture_v1',input_per_million=2,cached_input_per_million=.5,
        output_per_million=10,source_ref='https://example.test/synthetic_tariff',valid_until=pai.now+timedelta(days=1))
    usage={'input':100,'cached_input':20,'cache_write':0,'output':40,'reasoning':15,'semantics':'openai_chat_output_includes_reasoning'}
    values=dict(task_ref='task_fixture',attempt_ref='attempt_fixture',provider='provider_openai',model='fixture_model',usage=usage,latency_ms=15,outcome='accepted',tariff_version='fixture_v1')
    assert costs.record(**values)==570 and costs.record(**values)==570
    assert costs.task_cost('task_fixture')['attempts']==1
    assert costs.record(**dict(values,attempt_ref='attempt_unknown_tariff',tariff_version=None)) is None


def test_cache_hit_rechecks_version_and_live_grant(pai):
    cache=CostCacheRuntime(pai.root)
    grant=allow(pai,'archive.read','resource_archive','private_archive','research.archive',provider='provider_local',connection=None,operation='read')
    item=pai.root.queue.store.put(pai.root.owner_ref,'memory','memory_cache',{'text':'synthetic'},expected_version=0)
    dependency={'namespace':'memory','object_ref':item.object_id,'version':item.version,'digest':item.digest}
    key=cache.key(kind='retrieval',parameters={'query_digest':'fixture'},dependencies=[dependency])
    cache.put(key=key,kind='retrieval',payload={'answer':'synthetic'},dependencies=[dependency],ttl_seconds=60)
    access=AuthorizationRequest(owner_ref=pai.root.owner_ref,connection_ref=None,capability='archive.read',resource_ref='resource_archive',operation='read',
        data_class='private_archive',provider_ref='provider_local',purpose='research.archive')
    assert cache.get(key=key,authorization_request=access)
    pai.root.registry.revoke_grant(grant.grant_id,owner_ref=pai.root.owner_ref)
    assert cache.get(key=key,authorization_request=access) is None
