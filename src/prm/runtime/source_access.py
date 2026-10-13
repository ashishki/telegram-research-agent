"""Fresh source permission checks shared by serving and delivery; no new grants."""
from dataclasses import replace
from prm.capabilities import AuthorizationRequest,CapabilityDenied
from prm.storage.postgres import StorageError


def source_current(tx,registry,owner,scopes):
    if len(scopes)>16:raise StorageError('bounded delivery source scopes required')
    requests=[AuthorizationRequest(**scope) for scope in scopes]
    chosen=[]
    for request in requests:
        if request.owner_ref!=owner:raise CapabilityDenied('delivery source owner differs')
        decision,_,_=registry._decision(tx.conn,request)
        if not decision.allowed:raise CapabilityDenied('delivery source was revoked')
        chosen.append(replace(request,grant_ref=decision.grant_ref,expected_grant_revision=decision.grant_revision))
    ids=sorted({request.grant_ref for request in chosen})
    if ids:tx.conn.execute('SELECT grant_id FROM pa_policy.grants WHERE owner=%s AND grant_id=ANY(%s) ORDER BY grant_id FOR SHARE',(owner,ids)).fetchall()
    for request in chosen:
        decision,_,_=registry._decision(tx.conn,request)
        if not decision.allowed:raise CapabilityDenied('delivery source scope changed')
    for connection in sorted({request.connection_ref for request in chosen if request.provider_ref=='provider_microsoft_graph' and request.connection_ref}):
        row=tx.conn.execute('SELECT status FROM pa_connections.accounts WHERE owner=%s AND id=%s FOR SHARE',(owner,connection)).fetchone()
        if not row or row['status']!='connected':raise CapabilityDenied('delivery source disconnected')
