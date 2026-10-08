"""Selected Graph source binding for the shared Watch scheduler/collector."""
import hashlib
from urllib.parse import quote,urlencode
from prm.watch_jobs import WatchNotification
from prm.storage.postgres import StorageError
from .graph import GraphMailAdapter
from .scheduler import WatchScheduler,WatchCollectionWorker


def _watch_time(root):
    scheduler=root.watch_scheduler
    with scheduler.queue.store.transaction() as tx:return scheduler._now(tx.conn)


def wire_mail_watch(root,*,transport,selection):
    if len(selection.folders)!=1:raise StorageError('one exact watch folder required')
    source=selection.resource_ref
    def collect(source_ref,subscription):
        if source_ref!=source:raise StorageError('watch source substituted')
        path='/v1.0/me/mailFolders/'+quote(selection.folders[0],safe='')+'/messages?'+urlencode({'$select':','.join(GraphMailAdapter.FIELDS),'$top':min(selection.max_items,32)})
        value,receipt=transport.background_metadata_read(source_ref=source_ref,path=path)
        rows=value.get('value',[])
        if not isinstance(rows,list) or len(rows)>32:raise StorageError('Watch metadata batch exceeds bound')
        output=[]
        for row in rows:
            subject=row.get('subject','')
            if not subject.strip():continue
            sender=row.get('from',{}).get('emailAddress',{}).get('address','')
            if selection.sender_domains and sender.rsplit('@',1)[-1].casefold() not in selection.sender_domains:continue
            output.append(WatchNotification(subscription.subscription_id,root.owner_ref,'subject_'+hashlib.sha256(row['id'].encode()).hexdigest()[:24],
                hashlib.sha256((subject+row.get('receivedDateTime','')).encode()).hexdigest(),'change',subject[:240],subject[:800],
                'Новое сообщение в явно выбранной папке; необходимость ответа и сроки не подтверждены метаданными.',source_ref,_watch_time(root),
                source_url=row.get('webLink'),data_class='private_connector_metadata'))
        return output
    _wire(root,source=source,binding={'connection_ref':transport.connection_ref,'provider_ref':'provider_microsoft_graph'},collector=collect,upper_bound=transport.upper_bound)


def _wire(root,*,source,binding,collector,upper_bound):
    scheduler=getattr(root,'watch_scheduler',None) or WatchScheduler(root.queue)
    scheduler.source_bindings[source]=binding
    collectors=getattr(root,'watch_source_collectors',{})
    collectors[source]=collector;root.watch_source_collectors=collectors
    def collect_selected(source_ref,subscription):
        selected=collectors.get(source_ref)
        if selected is None:raise StorageError('selected Watch source unavailable')
        return selected(source_ref,subscription)
    root.watch_scheduler=scheduler;root.ingress.watch_scheduler=scheduler
    root.watch_collector=WatchCollectionWorker(scheduler,owner=root.owner_ref,registry=root.registry,collector=collect_selected,upper_bound=upper_bound)


def wire_archive_watch(root):
    from datetime import timedelta
    from prm.briefs import BriefWindow
    from .research import LocalArchiveReader
    source=root.archive_resource_ref
    def collect(source_ref,subscription):
        now=_watch_time(root)
        rows=LocalArchiveReader(root.settings.db_path).window_evidence(BriefWindow(subscription.timezone_name,now-timedelta(days=1),now,now))
        return [WatchNotification(subscription.subscription_id,root.owner_ref,
            'subject_'+hashlib.sha256(item['evidence_id'].encode()).hexdigest()[:24],item['source_version'],'change',item['title'][:240],item['support_span'][:800],
            'Новый материал в выбранном архиве.',source_ref,now,source_url=item['source_url'],data_class='private_archive') for item in rows]
    bound=getattr(getattr(root,'watch_collector',None),'upper_bound',0)
    _wire(root,source=source,binding={'connection_ref':None,'provider_ref':'provider_local','data_class':'private_archive'},collector=collect,upper_bound=bound)
