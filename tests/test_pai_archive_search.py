"""Deferred paired HTTP archive synthesis and provenance acceptance."""
from tests.pai_runtime_fixtures import pai,allow
from tests.test_prm_synthesis import _archive_payload,_archive_evidence
from prm.runtime.archive import RuntimeArchiveTransport
from prm.synthesis import synthesize_archive_response


def test_canonical_spans_reach_real_runtime_http_and_verify(pai):
    allow(pai,'model.generate','resource_dialogue','user_provided','answer.request')
    allow(pai,'model.context_egress','resource_archive','private_archive','answer.context')
    transport=RuntimeArchiveTransport(pai.root,request_ref='request_archive',guard=lambda:None,context_resource_ref='resource_archive')
    result=synthesize_archive_response(_archive_payload(),question='agent evals',evidence_items=_archive_evidence(),access=None,transport=transport)
    assert result.status=='generated_verified'
    assert 'https://t.me/example/1' in result.text
    sent=[row[2] for row in pai.requests if row[0]=='model']
    assert len(sent)==1 and 'Agent evals use task success and groundedness.' in str(sent[0])


def test_fabricated_provenance_and_revoked_archive_never_egress(pai):
    allow(pai,'model.generate','resource_dialogue','user_provided','answer.request')
    grant=allow(pai,'model.context_egress','resource_archive','private_archive','answer.context')
    pai.root.registry.revoke_grant(grant.grant_id,owner_ref=pai.root.owner_ref)
    transport=RuntimeArchiveTransport(pai.root,request_ref='request_revoked_archive',guard=lambda:None,context_resource_ref='resource_archive')
    result=synthesize_archive_response(_archive_payload(),question='agent evals',evidence_items=_archive_evidence(),access=None,transport=transport)
    assert result.text is None and not pai.requests


def test_compatible_model_provider_uses_separate_archive_scope_groups(pai):
    from dataclasses import replace
    pai.root.model_endpoint=replace(pai.root.model_endpoint,provider_ref='provider_mimo')
    allow(pai,'model.generate','resource_dialogue','user_provided','answer.request',provider='provider_mimo')
    allow(pai,'model.context_egress','resource_archive','private_archive','answer.context',provider='provider_mimo')
    transport=RuntimeArchiveTransport(pai.root,request_ref='request_compatible_archive',guard=lambda:None,context_resource_ref='resource_archive')
    result=synthesize_archive_response(_archive_payload(),question='agent evals',evidence_items=_archive_evidence(),access=None,transport=transport)
    assert result.status=='generated_verified'
    assert len([row for row in pai.requests if row[0]=='model'])==1
