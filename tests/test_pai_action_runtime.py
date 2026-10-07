"""Deferred actual preview/edit/confirm -> Graph HTTP -> exact receipt."""
import pytest
from tests.pai_runtime_fixtures import pai,graph,allow
from prm.runtime.actions import ActionRuntime
from prm.capabilities import CapabilityDenied


def test_edited_preview_confirm_and_double_click_have_one_actual_write(pai):
    manager,transport,actor=graph(pai)
    allow(pai,'assistant.action_execute','resource_selected_mail','private_connector_content','action.execute',provider='provider_microsoft_graph',connection=transport.connection_ref,operation='write')
    runtime=ActionRuntime(pai.root,graph_transport=transport,upper_bound=0)
    preview=runtime.preview(action_code='mail.send',resource_ref='resource_selected_mail',content={'to':['recipient@example.test'],'subject':'Synthetic','body':'First body'},rationale_refs=('source_fixture',))
    edited=runtime.edit(preview,content={**preview.content,'body':'Edited body'})
    assert edited.digest!=preview.digest and edited.version==2
    first=runtime.confirm_and_execute(edited.proposal_ref,actor_ref=pai.root.owner_ref)
    second=runtime.confirm_and_execute(edited.proposal_ref,actor_ref=pai.root.owner_ref)
    assert first==second and first.status=='succeeded'
    writes=[row for row in pai.requests if row[0]=='write'];assert len(writes)==1
    assert writes[0][2]['message']['body']['content']=='Edited body'
    with pytest.raises(CapabilityDenied):runtime.confirm_and_execute(edited.proposal_ref,actor_ref='owner_foreign')
