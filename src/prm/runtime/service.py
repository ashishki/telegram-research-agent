"""Explicit one-role process with stop/drain; no timer installation or live gate."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import signal
import threading
from prm.storage.postgres import SyntheticTarget,StorageError
from .composition import runtime_from_config
from .operations import OperationsRuntime


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--role',choices=('worker','research','scheduler','watch','delivery'),required=True)
    parser.add_argument('--target',required=True);parser.add_argument('--config',required=True);parser.add_argument('--db-path',required=True)
    args=parser.parse_args(argv)
    target_path,config_path=Path(args.target),Path(args.config)
    if target_path.stat().st_size>4096 or config_path.stat().st_size>8192:raise StorageError('bounded explicit configuration required')
    target=SyntheticTarget.from_mapping(json.loads(target_path.read_text()))
    root=runtime_from_config(json.loads(config_path.read_text()),target=target,settings=SimpleNamespace(db_path=args.db_path))
    stop=threading.Event()
    def shutdown(*args):stop.set()
    signal.signal(signal.SIGTERM,shutdown);signal.signal(signal.SIGINT,shutdown)
    if args.role=='worker':run=root.worker().run_once
    elif args.role=='research':
        from .research import DurableResearchWorker
        run=DurableResearchWorker(root).run_once
    elif args.role=='watch':
        if not hasattr(root,'watch_collector'):raise StorageError('selected Watch collector is not configured')
        run=root.watch_collector.run_once
    elif args.role=='delivery':
        if not hasattr(root,'delivery'):raise StorageError('explicit durable sender is not configured')
        def run():
            with root.queue.store.transaction() as tx:
                job=tx.conn.execute("SELECT j.id FROM pa_jobs.jobs j WHERE j.owner=%s AND j.status='completed' AND j.deadline>clock_timestamp() AND j.kind IN ('compute.assistant','compute.research') AND NOT EXISTS(SELECT 1 FROM pa_delivery.attempts a WHERE a.owner=j.owner AND a.id='answer_'||j.id) ORDER BY j.available_at,j.id LIMIT 1",(root.owner_ref,)).fetchone()
            if job:return root.delivery.deliver_result(owner=root.owner_ref,job_id=job['id'],destination_ref=root.ingress.destination_ref,upper_bound=root.ingress.delivery_upper_bound)
            if hasattr(root,'watch_collector'):
                for note in root.watch_collector.eligible_notifications():
                    if root.delivery.attempt(owner=root.owner_ref,delivery_id='watch_'+note['id']) is None:
                        return root.delivery.deliver_watch(owner=root.owner_ref,notification_id=note['id'],upper_bound=root.ingress.delivery_upper_bound)
            return None
    else:
        from .scheduler import WatchScheduler
        scheduler=getattr(root,'watch_scheduler',None) or WatchScheduler(root.queue);run=lambda:scheduler.tick(owner=root.owner_ref,registry=root.registry)
    while not stop.is_set():
        state=OperationsRuntime(target).status()
        if state.get('database')!='ready' or state.get('execution',{}).get('draining'):stop.wait(1);continue
        try:result=run()
        except Exception:stop.wait(1);continue
        if result is None:stop.wait(1)
    return 0


if __name__=='__main__':raise SystemExit(main())
