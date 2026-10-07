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
