"""Deferred inspect/edit/forget and actual tombstone enforcement."""
import pytest
from tests.pai_runtime_fixtures import pai
from prm.runtime.memory import MemoryRuntime
from prm.storage.postgres import StateConflict


def test_confirmed_memory_delete_and_restart_cannot_resurrect(pai):
    runtime=MemoryRuntime(pai.root);actor={'chat_id':'42','actor_id':'42','owner_chat_id':'42'}
    ref=runtime.preview(object_ref='memory_fixture',text='Explicit synthetic note',source_refs=('source_fixture',),**actor)
    assert runtime.inspect('memory_fixture',**actor) is None
    item=runtime.confirm(ref,**actor);assert item.payload['lifecycle']=='indexed'
    runtime.forget(item.object_id,**actor)
    assert MemoryRuntime(pai.root).inspect(item.object_id,**actor) is None
    with pytest.raises(StateConflict):pai.root.queue.store.put(pai.root.owner_ref,'memory',item.object_id,{'text':'resurrect'},expected_version=0)
    with pai.root.queue.store.transaction() as tx:
        assert tx.conn.execute('SELECT count(*) AS n FROM pa_runtime.object_versions WHERE owner=%s AND object_id=%s',(pai.root.owner_ref,item.object_id)).fetchone()['n']==0


def test_forget_removes_dependent_brief_documents_cache_and_actual_file(pai):
    from tests.test_pai_brief_runtime import stored_brief
    from prm.runtime.reader import PrivateReportRuntime
    runtime=MemoryRuntime(pai.root);actor={'chat_id':'42','actor_id':'42','owner_chat_id':'42'}
    preview=runtime.preview(object_ref='memory_report_source',text='Report source fact',source_refs=('explicit_owner',),**actor)
    source=runtime.confirm(preview,**actor);doc,state=stored_brief(pai)
    parent=pai.root.briefs._document_ref(doc.brief_id)
    runtime.register_dependency(parent_namespace='memory',parent_ref=source.object_id,child_namespace='result',child_ref=parent)
    pai.root.reader=PrivateReportRuntime(pai.root,artifact_root=pai.path/'deletion_artifacts')
    token=pai.root.reader.issue_session(**actor)
    assert pai.root.reader.artifact(token,brief_id=doc.brief_id,version=doc.version,format='html')
    assert list(pai.root.reader.path.glob('*.html'))
    result=runtime.forget(source.object_id,**actor)
    assert result['deletion_state']=='complete' and result['deleted_refs']>=3
    assert not list(pai.root.reader.path.glob('*.html'))
    assert pai.root.reader.artifact(token,brief_id=doc.brief_id,version=doc.version,format='html') is None
    with pai.root.queue.store.transaction() as tx:
        assert tx.conn.execute('SELECT count(*) AS n FROM pa_briefs.documents WHERE owner=%s AND id=%s',(pai.root.owner_ref,doc.brief_id)).fetchone()['n']==0


def test_forget_removes_memory_response_and_queued_result_copy(pai):
    from tests.pai_runtime_fixtures import request
    from prm.runtime.memory import MemoryRuntime
    root=pai.root;runtime=MemoryRuntime(root);root.attach_local_services(memory_runtime=runtime)
    actor={'chat_id':'42','actor_id':'42','owner_chat_id':'42'}
    preview=runtime.preview(object_ref='memory_copied_answer',text='Synthetic private note.',source_refs=('source_synthetic',),**actor)
    runtime.confirm(preview,**actor)
    _,result=request(pai,9300,'/memory memory_copied_answer')
    response_ref=result['payload']['conversation']['response_refs'][0]
    with root.queue.store.transaction() as tx:
        job=tx.conn.execute("SELECT result_ref FROM pa_jobs.jobs WHERE owner=%s AND payload->>'input_ref'=%s",(root.owner_ref,result['request_ref'])).fetchone()
    runtime.forget('memory_copied_answer',**actor)
    assert root.queue.store.get(root.owner_ref,'result',response_ref) is None
    assert root.queue.store.get(root.owner_ref,'result',job['result_ref']) is None
