"""Deferred expected/2x workload and named recovery scenarios; no claimed SLO."""
from tests.pai_runtime_fixtures import pai,allow,request
from tests.test_pai_end_to_end import (
    test_object_followups_confirmation_cancel_restart,
    test_watch_pause_dst_revoke_and_unknown_send,
    test_action_edit_confirm_double_click_owner_expiry_version,
    test_source_injection_secret_query_and_fallback_denials,
    test_restore_migration_revoke_delete_and_cache,
)


def test_expected_and_twice_peak_intake_records_queue_and_latency(pai):
    import time
    allow(pai,'model.generate','resource_dialogue','user_provided','answer.request')
    elapsed=[]
    for count in (10,20):
        started=time.monotonic();jobs=[]
        for index in range(count):
            ack=pai.root.ingress.receive({'update_id':1000+count*100+index,'message':{'chat':{'id':42,'type':'private'},'from':{'id':42},'text':'/chat synthetic load question'}})
            jobs.append(ack.job_id)
        assert len(set(jobs))==count
        for job in jobs:assert pai.root.worker().run_once()
        assert all(pai.root.queue.status(owner=pai.root.owner_ref,job_id=job)['status']=='completed' for job in jobs)
        elapsed.append(time.monotonic()-started)
    assert len([entry for entry in pai.requests if entry[0]=='model'])==30
    assert all(value>0 for value in elapsed)
