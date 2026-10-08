"""Durable logical-task fences across client reconstruction and provider changes."""
import hashlib
import re
from prm.storage.postgres import StorageError
from .deletion import lineage_lock


class ModelAttemptAlreadyRecorded(StorageError):
    def __init__(self,reference,operation_refs,*,recorded_digest=None,requested_digest=None):
        super().__init__('model task already attempted; automatic retry is forbidden')
        self.attempt_ref=reference;self.operation_refs=tuple(operation_refs);self.retry_allowed=False
        self.recorded_digest=recorded_digest;self.requested_digest=requested_digest
        self.input_changed=recorded_digest is not None and requested_digest is not None and recorded_digest!=requested_digest


def prepare_model_attempt(store,*,owner,task_ref,purpose,operation_refs,input_digest):
    if not isinstance(task_ref,str) or not 0<len(task_ref)<=512:raise StorageError('bounded logical model task required')
    if not isinstance(input_digest,str) or not re.fullmatch(r'[a-f0-9]{64}',input_digest):raise StorageError('model input digest required')
    reference='model_attempt_'+hashlib.sha256((task_ref+'\x1f'+purpose).encode()).hexdigest()[:32]
    with store.transaction() as tx:
        lineage_lock(tx.conn,owner)
        old=tx.get(owner,'conversation',reference)
        if old is not None:raise ModelAttemptAlreadyRecorded(reference,old.payload['operation_refs'],
            recorded_digest=old.payload['input_digest'],requested_digest=input_digest)
        tx.put(owner,'conversation',reference,{'task_ref':task_ref,'purpose':purpose,'operation_refs':list(operation_refs),
            'input_digest':input_digest,'retry_allowed':False},expected_version=0)
        if tx.get(owner,'conversation',task_ref) is not None and tx.conn.execute("SELECT to_regclass('pa_memory.dependencies') AS meta").fetchone()['meta'] is not None:
            tx.conn.execute('INSERT INTO pa_memory.dependencies VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                (owner,'conversation',task_ref,'conversation',reference))
    return reference
