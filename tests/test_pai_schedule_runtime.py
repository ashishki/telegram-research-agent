"""Deferred Graph calendar/contacts real HTTP, conflicts and ambiguity."""
from datetime import timedelta
from tests.pai_runtime_fixtures import pai,graph,allow
from prm.runtime.schedule import GraphScheduleRuntime
from prm.schedule_connectors import CalendarScopeSelection


def test_actual_calendar_overlap_and_contact_names_are_not_guessed(pai):
    manager,transport,actor=graph(pai)
    for capability,purpose in (('assistant.calendar_read','calendar.read'),('assistant.contacts_read','contacts.read')):
        allow(pai,capability,'account_synthetic','private_connector_metadata',purpose,provider='provider_microsoft_graph',connection=transport.connection_ref,operation='read')
    runtime=GraphScheduleRuntime(transport)
    selected=CalendarScopeSelection('provider_microsoft_graph','account_synthetic',('calendar_fixture',),pai.now,pai.now+timedelta(days=2),'Europe/Berlin')
    result=runtime.read_calendar(selected)
    assert result['coverage_complete'] and len(result['events'])==2 and len(result['conflicts'])==1
    contacts=runtime.resolve_contact('Alex')
    assert contacts['resolution'].status=='ambiguous' and contacts['resolution'].contact_ref is None
