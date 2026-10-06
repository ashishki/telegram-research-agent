"""Real durable action flow and crash/restart, with only provider I/O faked."""
from dataclasses import replace,asdict
from datetime import datetime,timedelta,timezone
import multiprocessing
import os
from pathlib import Path
import uuid
import pytest
from prm.confirmed_actions import ActionProposal,ActionExecuteRequest,ExecutionOutcome,execute_action
from prm.capabilities import CapabilityGrant,ProviderPolicy,AuthorizationRequest,CapabilityDenied
from prm.storage.postgres import migrate,SyntheticTarget,StateConflict
from prm.storage.testing import PostgresSandbox
from prm.storage.policy import install_policy,DurableCapabilityRegistry
from prm.storage.actions import install_actions,DurableActionStore


@pytest.fixture(scope='module')
def sandbox():
    with PostgresSandbox() as value:
        migrate(value.migrator,expected_version=0);install_policy(value.migrator);install_actions(value.migrator)
        yield value


def setup(sandbox,name):
    now=datetime.now(timezone.utc);owner='owner_action_'+name;conn='connection_action_'+name;resource='resource_action_'+name
    refs=tuple(kind+'_'+name for kind in ('request','day','month'))
    reg=DurableCapabilityRegistry(sandbox.app,budget_refs=refs)
    for kind,ref in zip(('request','day','month'),refs):reg.configure_window(owner=owner,ref=ref,kind=kind,capacity=20,starts=now-timedelta(hours=1),ends=now+timedelta(days=1))
    grant=CapabilityGrant('grant_action_'+name,owner,conn,'assistant.action_execute',(resource,),('write',),('private_connector_content',),
        'action.execute',ProviderPolicy(('provider_microsoft_graph',),maximum_request_count=20),now-timedelta(minutes=1),now+timedelta(hours=1),1)
    reg.register_grant(grant)
    proposal=ActionProposal('proposal_'+name,owner,conn,'provider_microsoft_graph','mail.send',resource,1,
        {'to':['synthetic@example.test'],'subject':'Synthetic','body':'No real send'},('evidence_synthetic',),now,now+timedelta(minutes=10))
    store=DurableActionStore(sandbox.app,owner_ref=owner);store.register(proposal)
    action=store.confirm(proposal.proposal_ref,actor_ref=owner)
    return reg,grant,store,action


def request(reg,grant,operation):
    auth=reg.authorize_and_reserve(AuthorizationRequest(grant.owner_ref,grant.capability,grant.resource_refs[0],'write',
        'private_connector_content','provider_microsoft_graph','action.execute',connection_ref=grant.connection_ref,operation_ref=operation),upper_bound=1)
    return ActionExecuteRequest(auth,grant.owner_ref,grant.connection_ref,grant.resource_refs[0],'provider_microsoft_graph')


class FakeExecutor:
    def __init__(self,path,crash=False):self.path=path;self.crash=crash
    def execute(self,action):
        with open(self.path,'a') as output:output.write('synthetic effect\n');output.flush();os.fsync(output.fileno())
        if self.crash:os._exit(0)
        return ExecutionOutcome('succeeded',provider_operation_ref='synthetic_provider_1')


def _execute_worker(config,refs,grant,action,barrier,path,crash,results):
    target=SyntheticTarget.from_mapping(config);reg=DurableCapabilityRegistry(target,budget_refs=refs)
    req=request(reg,grant,'operation_'+uuid.uuid4().hex)
    if barrier:barrier.wait(timeout=15)
    store=DurableActionStore(target,owner_ref=grant.owner_ref)
    receipt=execute_action(action,request=req,executor=FakeExecutor(path,crash),store=store,now=datetime.now(timezone.utc))
    if results:results.put(receipt.status)


def test_real_application_action_entrypoint_double_click_and_restart(sandbox,tmp_path):
    reg,grant,store,action=setup(sandbox,'double')
    ctx=multiprocessing.get_context('spawn');barrier=ctx.Barrier(2);results=ctx.Queue();path=tmp_path/'effect.txt'
    workers=[ctx.Process(target=_execute_worker,args=(asdict(sandbox.app),reg.budget_refs,grant,action,barrier,str(path),False,results)) for _ in range(2)]
    for worker in workers:worker.start()
    statuses=[results.get(timeout=30) for _ in workers]
    for worker in workers:worker.join(timeout=20);assert worker.exitcode==0
    assert path.read_text().splitlines()==['synthetic effect']
    restarted=DurableActionStore(sandbox.app,owner_ref=grant.owner_ref)
    receipt=execute_action(action,request=request(reg,grant,'operation_restart'),executor=FakeExecutor(path),store=restarted,now=datetime.now(timezone.utc))
    assert receipt.status=='succeeded'
    assert len(path.read_text().splitlines())==1


def test_process_death_after_effect_before_receipt_never_repeats(sandbox,tmp_path):
    reg,grant,store,action=setup(sandbox,'crash');path=tmp_path/'effect.txt'
    ctx=multiprocessing.get_context('spawn');worker=ctx.Process(target=_execute_worker,args=(asdict(sandbox.app),reg.budget_refs,grant,action,None,str(path),True,None))
    worker.start();worker.join(timeout=25);assert worker.exitcode==0
    restarted=DurableActionStore(sandbox.app,owner_ref=grant.owner_ref)
    receipt=execute_action(action,request=request(reg,grant,'operation_after_crash'),executor=FakeExecutor(path),store=restarted,now=datetime.now(timezone.utc))
    assert receipt.status=='unknown' and receipt.error_code=='prepared'
    assert path.read_text().splitlines()==['synthetic effect']
    with pytest.raises(StateConflict):restarted.register(replace(action.proposal,version=2),expected_version=1)


def test_wrong_owner_stale_version_revoked_grant_and_cancel_deny(sandbox,tmp_path):
    reg,grant,store,action=setup(sandbox,'denials');path=tmp_path/'effect.txt'
    req=request(reg,grant,'operation_stale')
    forged=replace(action,confirmation=replace(action.confirmation,actor_ref='owner_foreign'))
    with pytest.raises(CapabilityDenied):execute_action(forged,request=req,executor=FakeExecutor(path),store=store,now=datetime.now(timezone.utc))
    store.register(replace(action.proposal,version=2,content={**action.proposal.content,'body':'Edited'}),expected_version=1)
    with pytest.raises(CapabilityDenied):execute_action(action,request=req,executor=FakeExecutor(path),store=store,now=datetime.now(timezone.utc))
    current=store.confirm(action.proposal.proposal_ref,actor_ref=grant.owner_ref)
    store.cancel(current.proposal.proposal_ref)
    with pytest.raises(CapabilityDenied):execute_action(current,request=req,executor=FakeExecutor(path),store=store,now=datetime.now(timezone.utc))
    assert not path.exists()
    reg2,g2,s2,a2=setup(sandbox,'revoked')
    req2=request(reg2,g2,'operation_revoked');reg2.revoke_grant(g2.grant_id,owner_ref=g2.owner_ref)
    with pytest.raises(CapabilityDenied):execute_action(a2,request=req2,executor=FakeExecutor(path),store=s2,now=datetime.now(timezone.utc))
    assert not path.exists()


def test_confirmation_cannot_be_moved_to_another_account_or_proposal(sandbox,tmp_path):
    reg,grant,store,action=setup(sandbox,'binding');path=tmp_path/'effect.txt';req=request(reg,grant,'operation_binding')
    changed=replace(action,proposal=replace(action.proposal,connection_ref='connection_other'))
    with pytest.raises(CapabilityDenied):execute_action(changed,request=req,executor=FakeExecutor(path),store=store,now=datetime.now(timezone.utc))
    other=replace(action.proposal,proposal_ref='proposal_other_binding');store.register(other)
    forged=replace(action,proposal=other)
    with pytest.raises(CapabilityDenied):execute_action(forged,request=req,executor=FakeExecutor(path),store=store,now=datetime.now(timezone.utc))
    assert not path.exists()


def test_expired_confirmation_proposal_never_calls_provider(sandbox,tmp_path):
    import time
    reg,grant,store,action=setup(sandbox,'expiry')
    soon=replace(action.proposal,version=2,expires_at=datetime.now(timezone.utc)+timedelta(seconds=1))
    store.register(soon,expected_version=1)
    action=store.confirm(soon.proposal_ref,actor_ref=grant.owner_ref)
    time.sleep(1.1)
    path=tmp_path/'effect.txt'
    with pytest.raises(CapabilityDenied):execute_action(action,request=request(reg,grant,'operation_expired'),executor=FakeExecutor(path),store=store,now=datetime.now(timezone.utc))
    assert not path.exists()
