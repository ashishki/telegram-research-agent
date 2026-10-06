"""Bounded compute worker; effect jobs need the separate confirmed executor."""
from __future__ import annotations
from prm.storage.jobs import JobQueue


class ComputeWorker:
    def __init__(self,queue:JobQueue,*,owner):self.queue=queue;self.owner=owner
    def run_once(self):
        lease=self.queue.claim(owner=self.owner,modes=('compute',),kinds=('compute.digest',))
        if lease is None:return None
        if lease.kind != 'compute.digest':
            self.queue.retry_compute(lease,error_code='compute_unavailable')
            return None
        # Checkpoint is metadata only. A resumed lease reuses its verified input
        # refs; no grant snapshot, callable, network client or secret is loaded.
        self.queue.checkpoint(lease,{'stage':'input_verified','input_ref':lease.payload['input_ref']})
        result={'input_ref':lease.payload['input_ref'],'input_version':lease.payload['input_version'],'input_digest':lease.payload['input_digest']}
        return self.queue.complete(lease,result)
