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


def test_repeated_domain_import_keeps_target_tombstones_terminal_jobs_and_cleaned_files(pai):
    from copy import deepcopy
    from datetime import timedelta
    from hashlib import sha256
    from prm.runtime.migration import export_domain_delta,apply_domain_delta,state_manifest
    from prm.storage.postgres import PostgresStore
    from prm.storage.jobs import JobQueue
    from prm.runtime.composition import AssistantRuntime
    from prm.storage.policy import DurableCapabilityRegistry
    from prm.runtime.reader import PrivateReportRuntime
    from tests.test_pai_brief_runtime import stored_brief
    actor={'chat_id':'42','actor_id':'42','owner_chat_id':'42'};root=pai.root;memory=MemoryRuntime(root)
    preview=memory.preview(object_ref='memory_repeat_import',text='Synthetic derived content',source_refs=('source_fixture',),**actor)
    item=memory.confirm(preview,**actor)
    payload={'schema_version':1,'input_namespace':'memory','input_ref':item.object_id,'input_version':1,'input_digest':item.digest,
        'connection_ref':None,'resource_ref':'resource_local','purpose':'local.assistant','consent_revision':1}
    job=root.queue.enqueue(owner=root.owner_ref,idempotency_key='repeat_import_job',kind='compute.digest',payload=payload,deadline=pai.now+timedelta(minutes=10))
    root.queue.complete(root.queue.claim(owner=root.owner_ref,kinds=('compute.digest',)),{'text':'Synthetic result copy'})
    document,state=stored_brief(pai)
    memory.register_dependency(parent_namespace='memory',parent_ref=item.object_id,child_namespace='result',child_ref=root.briefs._document_ref(document.brief_id))
    root.reader=PrivateReportRuntime(root,artifact_root=pai.path/'source_artifacts')
    token=root.reader.issue_session(**actor);root.reader.artifact(token,brief_id=document.brief_id,version=document.version,format='html')
    pai.ops.kill_switch();OperationsRuntime(pai.pg.migrator,artifact_root=root.reader.path).backup(destination=pai.path/'repeat_baseline')
    delta=export_domain_delta(pai.pg.migrator);original=deepcopy(delta)
    target=pai.pg.empty_database('pa_test_repeat_import');directory=pai.path/'target_artifacts'
    restore_bundle(bundle=pai.path/'repeat_baseline',target=target,artifact_root=directory)
    app=pai.pg.target(target.database,'pa_test_app')
    registry=DurableCapabilityRegistry(app,budget_refs=root.registry.budget_refs,job_budget=True)
    restored=AssistantRuntime(target=app,settings=root.settings,registry=registry,owner_ref=root.owner_ref,owner_chat_id='42')
    restored.reader=PrivateReportRuntime(restored,artifact_root=directory);MemoryRuntime(restored).forget(item.object_id,**actor)
    assert not list(directory.iterdir()) and restored.queue.status(owner=root.owner_ref,job_id=job)['status']=='completed'
    expected=state_manifest(target)
    apply_domain_delta(target,delta,expected_target_manifest=expected)
    once=state_manifest(target)
    apply_domain_delta(target,delta,expected_target_manifest=once)
    assert state_manifest(target)==once and delta==original
    assert PostgresStore(app).get(root.owner_ref,'memory',item.object_id) is None
    assert restored.queue.status(owner=root.owner_ref,job_id=job)['status']=='completed'
    with PostgresStore(app).transaction() as tx:
        row=tx.conn.execute('SELECT deleted,cleanup_pending,root_digest FROM pa_artifacts.files WHERE owner=%s',(root.owner_ref,)).fetchone()
    assert row['deleted'] and not row['cleanup_pending']
    assert row['root_digest']==sha256(str(directory.resolve()).encode()).hexdigest()


def test_source_tombstone_conflicting_with_post_restore_target_write_blocks_atomic_import(pai):
    import pytest
    from prm.runtime.migration import export_domain_delta,apply_domain_delta,state_manifest
    from prm.storage.postgres import PostgresStore,StorageError
    actor={'chat_id':'42','actor_id':'42','owner_chat_id':'42'}
    source=pai.root.queue.store;ref='memory_divergent_restore'
    source.put(pai.root.owner_ref,'memory',ref,{'text':'baseline'},expected_version=0)
    pai.ops.kill_switch();OperationsRuntime(pai.pg.migrator).backup(destination=pai.path/'divergent_baseline')
    target=pai.pg.empty_database('pa_test_divergent_import')
    restore_bundle(bundle=pai.path/'divergent_baseline',target=target,artifact_root=pai.path/'divergent_artifacts')
    restored=PostgresStore(pai.pg.target(target.database,'pa_test_app'))
    restored.put(pai.root.owner_ref,'memory',ref,{'text':'new target version'},expected_version=1)
    MemoryRuntime(pai.root).forget(ref,**actor)
    delta=export_domain_delta(pai.pg.migrator);before=state_manifest(target)
    with pytest.raises(StorageError,match='incoming deletion conflicts'):
        apply_domain_delta(target,delta,expected_target_manifest=before)
    assert state_manifest(target)==before
    assert restored.get(pai.root.owner_ref,'memory',ref).payload['text']=='new target version'
