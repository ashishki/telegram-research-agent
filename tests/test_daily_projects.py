"""Durable exact owner confirmations, aliases, source/goal changes and applicability."""
from datetime import timedelta
import json,pytest
from tests.pai_runtime_fixtures import pai,request
from prm.runtime.memory import MemoryRuntime
from prm.storage.postgres import StorageError,StateConflict


def setup(pai):
    root=pai.root;root.attach_local_services(memory_runtime=MemoryRuntime(root))
    source=root.queue.store.put(root.owner_ref,'conversation','project_owner_source',{'query':'Synthetic explicit project description'},expected_version=0)
    return root,{'chat_id':'42','actor_id':'42','owner_chat_id':'42'},source


def context(pai,source,**changes):
    from tests.test_project_portfolio_context import _project
    d=_project('Aurora','active',confirmed='unknown');d.update(aliases=['Aurora','Аврора'])
    return {'descriptor':d,'reviewed_at':(pai.now-timedelta(minutes=1)).isoformat(),'expires_at':(pai.now+timedelta(days=30)).isoformat(),'source_bindings':[{'namespace':'conversation','ref':source.object_id,'version':source.version,'digest':source.digest}],'relationships':[],**changes}


def confirm(pai,root,actor,source,**changes):
    c=context(pai,source,**changes);preview=root.projects.preview(object_ref='project_aurora',context=c,**actor)
    return root.memory.confirm(preview,**actor)


def test_native_project_preview_confirmation_show_focus_and_exact_alias(pai):
    root,actor,source=setup(pai);c=context(pai,source)
    _,preview=request(pai,121000,'/projectpreview '+json.dumps({'object_ref':'project_aurora','context':c}))
    assert preview['status']=='preview' and root.queue.store.get(root.owner_ref,'memory','project_aurora') is None
    _,saved=request(pai,121001,'/projectconfirm '+preview['payload']['preview_ref'])
    assert saved['status']=='saved'
    _,shown=request(pai,121002,'/projectshow Аврора')
    assert 'prove one bounded workflow' in shown['text']
    _,wrong=request(pai,121003,'/projectshow Aur')
    assert wrong['status']=='not_found'
    request(pai,121004,'Объясни проект Аврора')
    with root.queue.store.transaction() as tx:
        focus=root.focus._current(tx).payload
        assert focus['project_ref']=='project_aurora' and focus['project_version']==1
    assert not pai.requests


def test_unknown_confirmation_and_foreign_owner_are_not_project_authority(pai):
    root,actor,source=setup(pai);c=context(pai,source)
    forged={**c,'descriptor':{**c['descriptor'],'owner_confirmation_status':'confirmed'}}
    with pytest.raises(StorageError):root.projects.preview(object_ref='project_bad',context=forged,**actor)
    root.queue.store.put(root.owner_ref,'memory','project_forged',{'kind':'project','project_context':forged},expected_version=0)
    with pytest.raises(StorageError):root.projects.get('project_forged',**actor)
    from prm.capabilities import CapabilityDenied
    with pytest.raises(CapabilityDenied):root.projects.preview(object_ref='project_bad',context=c,chat_id='44',actor_id='44',owner_chat_id='42')


def test_duplicate_alias_confirmation_is_atomic_and_replay_or_stale_cas_denied(pai):
    root,actor,source=setup(pai);item=confirm(pai,root,actor,source)
    other=context(pai,source);other['descriptor']['name']='Other'
    p=root.projects.preview(object_ref='project_other',context=other,**actor)
    with pytest.raises(StateConflict):root.memory.confirm(p,**actor)
    assert root.memory.inspect('project_other',**actor) is None
    changed=context(pai,source);changed['descriptor']['current_goal']='New goal'
    a=root.projects.preview(object_ref=item.object_id,context=changed,expected_version=1,**actor)
    b=root.projects.preview(object_ref=item.object_id,context=changed,expected_version=1,**actor)
    assert root.memory.confirm(a,**actor).version==2
    with pytest.raises(StateConflict):root.memory.confirm(a,**actor)
    with pytest.raises(StateConflict):root.memory.confirm(b,**actor)
    with pytest.raises(StorageError):root.projects.get(item.object_id,version=1,**actor)


def test_stale_or_changed_source_context_fails_closed(pai):
    root,actor,source=setup(pai)
    item=confirm(pai,root,actor,source,reviewed_at=(pai.now-timedelta(days=3)).isoformat(),expires_at=(pai.now-timedelta(days=1)).isoformat())
    with pytest.raises(StorageError):root.projects.get(item.object_id,**actor)
    assert root.projects.get(item.object_id,allow_stale=True,**actor)
    root.queue.store.put(root.owner_ref,'conversation',source.object_id,{'query':'Changed explicit source'},expected_version=1)
    with pytest.raises(StorageError):root.projects.get(item.object_id,allow_stale=True,**actor)


def test_keyword_only_link_paused_project_and_goal_change_never_recommend_action(pai):
    root,actor,source=setup(pai)
    evidence=root.queue.store.put(root.owner_ref,'result','project_evidence',{'text':'Synthetic Aurora experiment measures a bounded workflow.','data_classes':['user_provided']},expected_version=0)
    item=confirm(pai,root,actor,source)
    assert not root.projects.applicability(object_ref=item.object_id,version=1,evidence_ref=evidence.object_id,**actor)['action_recommendation']
    c=context(pai,source);c['relationships']=[{'evidence_ref':evidence.object_id,'evidence_version':1,'evidence_digest':evidence.digest,'quote':'experiment measures a bounded workflow','relation':'Supports the selected goal','experiment':'One synthetic fixture run','reject_if':'The fixture does not reproduce the measured behavior'}]
    p=root.projects.preview(object_ref=item.object_id,context=c,expected_version=1,**actor);item=root.memory.confirm(p,**actor)
    output=root.projects.applicability(object_ref=item.object_id,version=2,evidence_ref=evidence.object_id,**actor)
    assert output['action_recommendation'] and output['next_proof']=='one fixture test' and not output['execution_authority']
    c['descriptor']['status']='paused'
    p=root.projects.preview(object_ref=item.object_id,context=c,expected_version=2,**actor);root.memory.confirm(p,**actor)
    assert not root.projects.applicability(object_ref=item.object_id,version=3,evidence_ref=evidence.object_id,**actor)['action_recommendation']
    with pytest.raises(StorageError):root.projects.applicability(object_ref=item.object_id,version=2,evidence_ref=evidence.object_id,**actor)
    root.memory.forget(source.object_id,**actor)  # Different namespace must not delete conversation source.
    assert root.queue.store.get(root.owner_ref,'conversation',source.object_id)


def test_relationship_quote_or_evidence_revision_change_is_denied(pai):
    root,actor,source=setup(pai)
    evidence=root.queue.store.put(root.owner_ref,'result','project_evidence',{'text':'Synthetic source only.','data_classes':['user_provided']},expected_version=0)
    c=context(pai,source);c['relationships']=[{'evidence_ref':evidence.object_id,'evidence_version':1,'evidence_digest':evidence.digest,'quote':'Invented relationship quote','relation':'Link','experiment':'Test','reject_if':'Mismatch'}]
    p=root.projects.preview(object_ref='project_aurora',context=c,**actor)
    with pytest.raises(StorageError):root.memory.confirm(p,**actor)
    assert not root.memory.inspect('project_aurora',**actor)


def test_project_applicability_preserves_private_source_scopes_and_revocation(pai):
    from tests.pai_runtime_fixtures import allow
    from prm.capabilities import AuthorizationRequest,CapabilityDenied
    from dataclasses import asdict
    root,actor,source=setup(pai)
    grant=allow(pai,'archive.read',root.archive_resource_ref,'private_archive','research.archive',provider='provider_local',connection=None,operation='read')
    scope=asdict(AuthorizationRequest(owner_ref=root.owner_ref,connection_ref=None,capability='archive.read',resource_ref=root.archive_resource_ref,operation='read',data_class='private_archive',provider_ref='provider_local',purpose='research.archive'))
    evidence=root.queue.store.put(root.owner_ref,'result','project_private',{'text':'Synthetic private proof of the selected workflow.','data_classes':['private_archive'],'source_scopes':[scope]},expected_version=0)
    c=context(pai,source);c['relationships']=[{'evidence_ref':evidence.object_id,'evidence_version':1,'evidence_digest':evidence.digest,'quote':'proof of the selected workflow','relation':'Owner-selected goal connection','experiment':'One synthetic run','reject_if':'No measured proof'}]
    p=root.projects.preview(object_ref='project_aurora',context=c,**actor);root.memory.confirm(p,**actor)
    _,output=request(pai,121100,'/projectapply '+json.dumps({'object_ref':'project_aurora','version':1,'evidence_ref':evidence.object_id}))
    assert output['data_classes']==['private_archive'] and output['payload']['source_scopes']==[scope]
    root.registry.revoke_grant(grant.grant_id,owner_ref=root.owner_ref)
    with pytest.raises(CapabilityDenied):root.projects.applicability(object_ref='project_aurora',version=1,evidence_ref=evidence.object_id,**actor)


def test_forwarded_project_confirmation_cannot_use_memory_alias(pai):
    root,actor,source=setup(pai);preview=root.projects.preview(object_ref='project_aurora',context=context(pai,source),**actor)
    root.ingress.receive({'update_id':121200,'message':{'chat':{'id':42,'type':'private'},'from':{'id':42},'text':'/memoryconfirm '+preview,'forward_origin':{'type':'hidden_user','sender_user_name':'Synthetic source'},'message_id':121200}})
    ref=root.worker().run_once();output=root.queue.store.get(root.owner_ref,'result',ref).payload
    assert output['status']=='provider_egress_required' and root.memory.inspect('project_aurora',**actor) is None
    with root.queue.store.transaction() as tx:assert not tx.conn.execute('SELECT consumed FROM pa_memory.previews WHERE owner=%s AND id=%s',(root.owner_ref,preview)).fetchone()['consumed']
