"""Deferred actual private dump/restore and new default-off epoch."""
from tests.pai_runtime_fixtures import pai
from prm.runtime.operations import OperationsRuntime,restore_bundle


def test_actual_backup_restore_isolated_epoch_and_egress_off(pai):
    pai.ops.kill_switch()
    backup=OperationsRuntime(pai.pg.migrator).backup(destination=pai.path/'backup')
    target=pai.pg.empty_database('pa_test_restored_full')
    result=restore_bundle(bundle=pai.path/'backup',target=target,artifact_root=pai.path/'restored_artifacts')
    state=OperationsRuntime(pai.pg.target(target.database,'pa_test_app')).status()
    assert result['status']=='restored_egress_off' and not state['execution']['egress_enabled']
    assert state['execution']['epoch']!=backup['epoch'] and state['execution']['draining']
