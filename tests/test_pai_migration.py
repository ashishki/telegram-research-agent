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
