"""Actual Watch wiring uses its injected or database clock for collector output."""
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from tests.pai_runtime_fixtures import pai
from prm.runtime.scheduler import WatchScheduler
from prm.runtime.watch import wire_archive_watch,wire_mail_watch


def test_archive_collector_uses_selected_scheduler_clock(pai,monkeypatch):
    from prm.runtime.research import LocalArchiveReader
    root=pai.root;frozen=pai.now-timedelta(hours=2)
    root.watch_scheduler=WatchScheduler(root.queue,clock=lambda:frozen)
    seen=[]
    def archive(self,window):
        seen.append(window)
        return [{'evidence_id':'synthetic_clock','source_version':'1','title':'Synthetic','support_span':'Synthetic archive material.','source_url':'https://source.example.test/one'}]
    monkeypatch.setattr(LocalArchiveReader,'window_evidence',archive)
    wire_archive_watch(root)
    note=root.watch_source_collectors[root.archive_resource_ref](root.archive_resource_ref,SimpleNamespace(subscription_id='watch_clock',timezone_name='UTC'))[0]
    assert note.due_at==frozen and seen[0].end_at==frozen and seen[0].start_at==frozen-timedelta(days=1)


def test_mail_collector_supports_injected_and_default_database_clock(pai):
    from prm.mail_connector import MailScopeSelection
    root=pai.root;frozen=pai.now-timedelta(hours=1)
    root.watch_scheduler=WatchScheduler(root.queue,clock=lambda:frozen)
    def read(**kwargs):return {'value':[{'id':'synthetic_clock_mail','subject':'Synthetic','receivedDateTime':pai.now.isoformat(),'from':{'emailAddress':{'address':'sender@example.test'}}}]},{}
    transport=SimpleNamespace(connection_ref='connection_clock',upper_bound=0,background_metadata_read=read)
    selection=MailScopeSelection('provider_microsoft_graph','resource_mail_clock',folders=('inbox',))
    wire_mail_watch(root,transport=transport,selection=selection)
    collect=root.watch_source_collectors[selection.resource_ref]
    subscription=SimpleNamespace(subscription_id='watch_mail_clock')
    assert collect(selection.resource_ref,subscription)[0].due_at==frozen
    root.watch_scheduler.clock=None
    before=datetime.now(timezone.utc)
    assert collect(selection.resource_ref,subscription)[0].due_at>=before
