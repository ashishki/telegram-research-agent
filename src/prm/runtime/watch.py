"""Selected Graph source binding for the shared Watch scheduler/collector."""
from datetime import datetime,timezone
import hashlib
from urllib.parse import quote,urlencode
from prm.watch_jobs import WatchNotification
from prm.storage.postgres import StorageError
from .graph import GraphMailAdapter
from .scheduler import WatchScheduler,WatchCollectionWorker


def wire_mail_watch(root,*,transport,selection):
    if len(selection.folders)!=1:raise StorageError('one exact watch folder required')
    source=selection.resource_ref
    scheduler=WatchScheduler(root.queue,source_bindings={source:{'connection_ref':transport.connection_ref,'provider_ref':'provider_microsoft_graph'}})
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
                'Новое сообщение в явно выбранной папке; необходимость ответа и сроки не подтверждены метаданными.',source_ref,datetime.now(timezone.utc),
                source_url=row.get('webLink'),data_class='private_connector_metadata'))
        return output
    root.watch_scheduler=scheduler;root.watch_collector=WatchCollectionWorker(scheduler,owner=root.owner_ref,registry=root.registry,collector=collect,upper_bound=transport.upper_bound)
    root.ingress.watch_scheduler=scheduler
