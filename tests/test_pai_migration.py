"""Deferred monotone confirmations/tombstones after isolated state transfer."""
from tests.pai_runtime_fixtures import pai
from prm.runtime.operations import OperationsRuntime,restore_bundle
from prm.runtime.migration import export_receipt_delta,apply_receipt_delta
from prm.runtime.memory import MemoryRuntime


def test_new_deletion_delta_after_snapshot_survives_rollback_rehearsal(pai):
    actor={'chat_id':'42','actor_id':'42','owner_chat_id':'42'};memory=MemoryRuntime(pai.root)
    preview=memory.preview(object_ref='memory_delta',text='Synthetic old content',source_refs=('source_fixture',),**actor);memory.confirm(preview,**actor)
    pai.ops.kill_switch();OperationsRuntime(pai.pg.migrator).backup(destination=pai.path/'baseline')
    memory.forget('memory_delta',**actor);delta=export_receipt_delta(pai.pg.migrator)
    target=pai.pg.empty_database('pa_test_rollback_delta')
    restore_bundle(bundle=pai.path/'baseline',target=target,artifact_root=pai.path/'rollback_artifacts')
    assert apply_receipt_delta(target,delta)['status']=='delta_applied_egress_off'
    from prm.storage.postgres import PostgresStore
    restored=PostgresStore(pai.pg.target(target.database,'pa_test_app'))
    assert restored.get(pai.root.owner_ref,'memory','memory_delta') is None


def test_full_domain_delta_preserves_new_memory_conversation_and_budget_state(pai):
    from prm.runtime.migration import export_domain_delta,apply_domain_delta,state_manifest
    from prm.storage.postgres import PostgresStore
    pai.ops.kill_switch();OperationsRuntime(pai.pg.migrator).backup(destination=pai.path/'domain_baseline')
    target=pai.pg.empty_database('pa_test_domain_delta')
    restore_bundle(bundle=pai.path/'domain_baseline',target=target,artifact_root=pai.path/'domain_artifacts')
    expected=state_manifest(target)
    pai.root.queue.store.put(pai.root.owner_ref,'memory','memory_after_snapshot',{'text':'new owned state'},expected_version=0)
    state=pai.root.conversations.record_response('42',text='New visible result after snapshot')
    delta=export_domain_delta(pai.pg.migrator)
    assert apply_domain_delta(target,delta,expected_target_manifest=expected)['tables']>20
    restored=PostgresStore(pai.pg.target(target.database,'pa_test_app'))
    assert restored.get(pai.root.owner_ref,'memory','memory_after_snapshot').payload['text']=='new owned state'
    assert restored.get(pai.root.owner_ref,'result',state.object_refs[0].response_ref).payload['display_text']=='New visible result after snapshot'


def test_corrupted_domain_object_blocks_atomic_transfer(pai):
    from prm.runtime.migration import export_domain_delta,apply_domain_delta,state_manifest
    import hashlib,json,pytest
    from prm.storage.postgres import StorageError
    pai.root.queue.store.put(pai.root.owner_ref,'memory','memory_domain_integrity',{'text':'original'},expected_version=0)
    pai.ops.kill_switch();OperationsRuntime(pai.pg.migrator).backup(destination=pai.path/'integrity_baseline')
    target=pai.pg.empty_database('pa_test_domain_integrity')
    restore_bundle(bundle=pai.path/'integrity_baseline',target=target,artifact_root=pai.path/'integrity_artifacts')
    expected=state_manifest(target);delta=export_domain_delta(pai.pg.migrator)
    data=delta['tables']['pa_runtime.object_versions'];data['rows'][0]['payload']={'text':'tampered'}
    data['sha256']=hashlib.sha256(json.dumps(data['rows'],sort_keys=True).encode()).hexdigest()
    with pytest.raises(StorageError):apply_domain_delta(target,delta,expected_target_manifest=expected)
    assert state_manifest(target)==expected
