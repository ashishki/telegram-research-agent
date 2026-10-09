"""Bounded result projections plus immutable owner-bound diagnostic chunks."""
from __future__ import annotations
import base64
import hashlib
import json
from prm.storage.postgres import StorageError, _canonical

MAX_PAYLOAD_BYTES = 524288
CHUNK_BYTES = 24000
PROJECTION_KEYS = frozenset({
    'conversation', 'response_ref', 'referenced_response_ref', 'request_id',
    'source_data_class', 'source_data_classes', 'source_scopes', 'source_memory_refs',
    'proposal_ref', 'version', 'content_digest', 'receipt_ref', 'job_id', 'job_ref',
    'model_call_attempted', 'model_reply_observed', 'provider_outcome',
    'accounting_status', 'write_performed', 'retrieval_performed',
    'telegram_parse_mode', 'telegram_navigation', 'delivery_completion',
})


def bounded_result_record(queue, lease, record):
    """Preserve full authorized payload without inlining it in every result."""
    encoded = json.dumps(record, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':'), allow_nan=False).encode()
    if len(encoded) <= 65536:
        _canonical(record)
        return record
    payload = record['payload']
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()
    if not 0 < len(data) <= MAX_PAYLOAD_BYTES:
        raise StorageError('diagnostic result payload exceeds its explicit bound')
    digest = hashlib.sha256(data).hexdigest()
    pieces = [data[i:i + CHUNK_BYTES] for i in range(0, len(data), CHUNK_BYTES)]
    prefix = 'resultpayload_' + hashlib.sha256((lease.owner + ':' + lease.job_id + ':' + digest).encode()).hexdigest()[:32]
    refs = [prefix + '_' + str(i) for i in range(len(pieces))]
    manifest = {'schema_version': 1, 'sha256': digest, 'bytes': len(data),
                'input_ref': lease.payload['input_ref'], 'chunk_refs': refs}
    compact = {key: payload[key] for key in PROJECTION_KEYS if key in payload}
    compact['payload_storage'] = manifest
    result = {**record, 'payload': compact}
    _canonical(result)  # Scope/confirmation projection must still meet64KiB.
    with queue.store.transaction() as tx:
        from .deletion import lineage_lock
        lineage_lock(tx.conn,lease.owner)
        queue._fenced(tx, lease)
        for index, (ref, piece) in enumerate(zip(refs, pieces)):
            value = {'schema_version': 1, 'index': index, 'sha256': digest,
                     'input_ref': manifest['input_ref'],
                     'data_base64': base64.b64encode(piece).decode('ascii')}
            prior = tx.get(lease.owner, 'result', ref, version=1)
            if prior is None:
                tx.put(lease.owner, 'result', ref, value, expected_version=0)
            elif prior.payload != value:
                raise StorageError('immutable result diagnostic chunk differs')
            if tx.conn.execute("SELECT to_regclass('pa_memory.dependencies') AS meta").fetchone()['meta'] is not None:
                tx.conn.execute('INSERT INTO pa_memory.dependencies VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                    (lease.owner, lease.payload['input_namespace'], lease.payload['input_ref'], 'result', ref))
    return result


def resolve_result_payload(store, *, owner, record):
    payload = record.get('payload', {})
    manifest = payload.get('payload_storage')
    if manifest is None:
        return payload
    if (not isinstance(manifest, dict) or manifest.get('schema_version') != 1
        or type(manifest.get('bytes')) is not int
        or not 0 < manifest['bytes'] <= MAX_PAYLOAD_BYTES
        or not isinstance(manifest.get('chunk_refs'), list)
        or not 1 <= len(manifest['chunk_refs']) <= 22):
        raise StorageError('invalid bounded diagnostic manifest')
    chunks = []
    for index, ref in enumerate(manifest['chunk_refs']):
        item = store.get(owner, 'result', ref, version=1)
        if (item is None or item.payload.get('index') != index
            or item.payload.get('sha256') != manifest['sha256']
            or item.payload.get('input_ref') != manifest['input_ref']):
            raise StorageError('diagnostic chunk owner or identity differs')
        try:
            piece = base64.b64decode(item.payload['data_base64'], validate=True)
        except (ValueError, KeyError):
            raise StorageError('invalid diagnostic chunk encoding') from None
        if len(piece) > CHUNK_BYTES:
            raise StorageError('diagnostic chunk exceeds bound')
        chunks.append(piece)
    data = b''.join(chunks)
    if len(data) != manifest['bytes'] or hashlib.sha256(data).hexdigest() != manifest['sha256']:
        raise StorageError('diagnostic payload digest differs')
    try:
        original = json.loads(data)
    except (ValueError, UnicodeError):
        raise StorageError('invalid diagnostic payload') from None
    if (not isinstance(original, dict)
        or any(original.get(key) != value for key, value in payload.items() if key in PROJECTION_KEYS)):
        raise StorageError('diagnostic scope projection differs')
    return original
