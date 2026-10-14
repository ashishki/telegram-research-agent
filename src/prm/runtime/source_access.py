"""Fresh source permission checks shared by serving and delivery; no new grants."""
from dataclasses import replace
from prm.capabilities import AuthorizationRequest,CapabilityDenied
from prm.storage.postgres import StorageError
import hashlib


PROTECTED=frozenset({'private_archive','private_connector_metadata','private_connector_content'})


def result_provenance(tx,owner,item):
    """Canonical response origins and both existing durable result layouts."""
    if item.object_id.startswith('response_'):
        ref='response_origin_'+hashlib.sha256(item.object_id.encode()).hexdigest()[:32]
        origin=tx.get(owner,'conversation',ref)
        if origin is None or origin.payload.get('response_ref')!=item.object_id:
            raise StorageError('response provenance unavailable')
        classes=origin.payload['data_classes'];scopes=origin.payload.get('source_scopes',[])
    else:
        details=item.payload.get('payload',{})
        classes=item.payload.get('data_classes',details.get('source_data_classes',[item.payload.get('data_class','private_archive')]))
        scopes=details.get('source_scopes',item.payload.get('source_scopes',[]))
    if not isinstance(classes,(list,tuple)) or not classes:raise StorageError('result data classes unavailable')
    if not isinstance(scopes,(list,tuple)) or len(scopes)>16:raise StorageError('bounded result source authority required')
    if not set(classes)<= {'model_generated','private_archive','private_connector_metadata','private_connector_content','user_provided','public'}:raise StorageError('unknown result data class')
    if not set(classes)&PROTECTED<={s.get('data_class') for s in scopes}:raise CapabilityDenied('protected result source authority unavailable')
    return tuple(classes),tuple(scopes)


def result_archive_snapshots(tx,owner,item):
    if item.object_id.startswith('response_'):
        origin=tx.get(owner,'conversation','response_origin_'+hashlib.sha256(item.object_id.encode()).hexdigest()[:32])
        return tuple(origin.payload.get('archive_snapshots',())) if origin else ()
    details=item.payload.get('payload',{})
    return tuple(details.get('archive_snapshots',item.payload.get('archive_snapshots',())))


def source_current(tx,registry,owner,scopes,*,archive_snapshots=(),require_snapshot=False):
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
    selected_guard=getattr(registry,'selected_source_guard',None)
    if selected_guard is not None:
        if require_snapshot:tx.hold_context(selected_guard(owner,tuple(requests),archive_snapshots=tuple(archive_snapshots)))
        else:tx.hold_context(selected_guard(owner,tuple(requests)))
    for connection in sorted({request.connection_ref for request in chosen if request.provider_ref=='provider_microsoft_graph' and request.connection_ref}):
        row=tx.conn.execute('SELECT status FROM pa_connections.accounts WHERE owner=%s AND id=%s FOR SHARE',(owner,connection)).fetchone()
        if not row or row['status']!='connected':raise CapabilityDenied('delivery source disconnected')
    for request in chosen:
        if request.provider_ref!='provider_github' or not request.connection_ref:continue
        row=tx.conn.execute('SELECT status,expires,scopes FROM pa_connections.accounts WHERE owner=%s AND id=%s FOR SHARE',(owner,request.connection_ref)).fetchone()
        now=tx.conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
        if (not row or row['status']!='connected' or row['expires'] is None or row['expires']<=now
            or not isinstance(row['scopes'],dict) or row['scopes'].get('provider')!='github'
            or row['scopes'].get('repositories')!=[request.resource_ref]):raise CapabilityDenied('GitHub source disconnected or expired')
