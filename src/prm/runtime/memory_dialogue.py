"""Natural explicit memory controls retain existing preview/confirmation semantics."""
import hashlib,json,re,uuid
from prm.contracts import AssistantResult
from prm.capabilities import CapabilityDenied
from prm.storage.postgres import StorageError,StateConflict
from .memory_context import binding_provenance,memory_current,SAVE_UNDO_POLICY


class MemoryDialogueRuntime:
    def __init__(self,root):self.root=root
    @property
    def actor(self):return dict(chat_id=self.root.owner_chat_id,actor_id=self.root.owner_chat_id,owner_chat_id=self.root.owner_chat_id)

    def _pending_ref(self):return 'memory_pending_'+hashlib.sha256(self.root.focus.scope().encode()).hexdigest()[:32]

    def preview(self,request_ref,lease,*,text,object_ref=None,expected_version=0,kind='note',lifecycle='indexed',source_bindings=None,preference_rule=None):
        root=self.root
        with root.queue.store.transaction() as tx:
            source=tx.get(root.owner_ref,'conversation',request_ref,version=1)
            if source is None:raise StorageError('explicit memory input unavailable')
            root.ingress.bindings.request_current_in(tx,source)
            if source.payload.get('telegram_envelope',{}).get('source_trust')=='untrusted_source':raise CapabilityDenied('memory needs explicit owner input')
            bindings=source_bindings or [{'namespace':'conversation','ref':source.object_id,'version':source.version,'digest':source.digest}]
            classes,scopes,snapshots=binding_provenance(root,tx,bindings)
        ref=root.memory.preview(object_ref=object_ref or 'memory_'+uuid.uuid4().hex,text=text,source_refs=tuple(b['ref'] for b in bindings),
            source_bindings=bindings,kind=kind,lifecycle=lifecycle,expected_version=expected_version,preference_rule=preference_rule,**self.actor)
        with root.queue.store.transaction() as tx:
            from .deletion import lineage_lock
            lineage_lock(tx.conn,root.owner_ref)
            if lease:root.queue._fenced(tx,lease)
            old=tx.get(root.owner_ref,'conversation',self._pending_ref())
            value={'schema_version':'assistant.memory_preview_binding.v1','preview_ref':ref,'request_ref':request_ref,
                'result_ref':'result_'+lease.job_id if lease else None,'kind':kind}
            tx.put(root.owner_ref,'conversation',self._pending_ref(),value,expected_version=old.version if old else 0)
            tx.conn.execute('INSERT INTO pa_memory.dependencies VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(root.owner_ref,'conversation',request_ref,'conversation',self._pending_ref()))
        return AssistantResult(request_ref,'preview','chat','Предпросмотр сохранения:\n'+text+'\n\nПодтвердить: «подтверди сохранение».',payload={'preview_ref':ref,'preview_kind':kind,
            'source_data_classes':classes,'source_data_class':classes[0],'source_scopes':scopes,'archive_snapshots':snapshots,'save_undo_policy':SAVE_UNDO_POLICY})

    def _view(self,request_ref,items,*,status='found',prefix=''):
        root=self.root;classes={'user_provided'};scopes={};snapshots=set();bindings=[]
        with root.queue.store.transaction() as tx:
            from .deletion import lineage_lock
            lineage_lock(tx.conn,root.owner_ref)
            for item in items:
                b={'memory_ref':item.object_id,'version':item.version,'digest':item.digest}
                current=memory_current(tx,root.owner_ref,b)
                if current.payload.get('kind')=='project':c,s,a=root.projects.provenance_in(tx,current)
                else:c,s,a=binding_provenance(root,tx,current.payload.get('source_bindings',[]))
                classes.update(c);snapshots.update(a);bindings.append(b)
                for scope in s:scopes[json.dumps(scope,sort_keys=True)]=scope
        text=prefix+'\n'.join(item.object_id+' (v'+str(item.version)+'): '+item.payload['text'] for item in items)
        if not items:text=prefix+'Записи не найдены или их источники сейчас недоступны.'
        from .source_access import source_current
        try:
            state=root.conversations.record_model_response(root.owner_chat_id,text=text,query='',topic='Память',data_classes=classes,
                source_scopes=list(scopes.values()),archive_snapshots=snapshots,memory_bindings=bindings,
                provenance_guard=lambda tx:source_current(tx,root.registry,root.owner_ref,list(scopes.values()),archive_snapshots=snapshots,require_snapshot=True))
        except (CapabilityDenied,StorageError):
            return AssistantResult(request_ref,'source_unavailable','chat','Запись изменена или удалена. Покажите актуальную память заново.',payload={'source_data_class':'user_provided'})
        return AssistantResult(request_ref,status if items else 'not_found','chat',text,payload={'conversation':{'response_refs':[state.object_refs[0].response_ref]},
            'memory_bindings':bindings,'source_data_classes':sorted(classes),'source_data_class':sorted(classes)[0],'source_scopes':list(scopes.values()),'archive_snapshots':sorted(snapshots)})

    def try_answer(self,request,*,request_ref,lease,guard):
        root=self.root
        if not hasattr(root,'memory'):return None
        text=request.query.strip();low=text.casefold().rstrip('?.!')
        if lease:
            with root.queue.store.transaction() as tx:body=root.queue._input(tx,root.owner_ref,lease.payload).payload
            if body.get('telegram_envelope',{}).get('source_trust')=='untrusted_source':return None
        save=re.fullmatch(r'(?is)(?:запомни|сохрани в память)\s*[: ]\s*(.{1,12000})',text)
        if save:return self.preview(request_ref,lease,text=save[1].strip())
        if low in {'подтверди сохранение','подтвердить сохранение','сохрани эту запись'}:
            ticket=root.focus.ticket(request_ref) if lease else None
            pending=root.queue.store.get(root.owner_ref,'conversation',self._pending_ref())
            if (not pending or not ticket or not ticket.get('target') or ticket['target']['result_ref']!=pending.payload['result_ref']):
                return AssistantResult(request_ref,'clarify','chat','Для сохранения нужен текущий точный предпросмотр. Покажите его заново.',payload={'source_data_class':'user_provided'})
            item=root.memory.confirm(pending.payload['preview_ref'],**self.actor)
            return self._view(request_ref,[item],status='saved',prefix='Сохранено. Отменить: «забудь '+item.object_id+'».\n')
        correct=re.fullmatch(r'(?is)(?:исправь память|исправь запись)\s+(memory_[a-f0-9]+)\s*:\s*(.{1,12000})',text)
        if correct:
            current=root.memory.inspect(correct[1],**self.actor)
            if current is None:return self._view(request_ref,[])
            return self.preview(request_ref,lease,text=correct[2],object_ref=current.object_id,expected_version=current.version,kind=current.payload['kind'],lifecycle=current.payload['lifecycle'],preference_rule=current.payload.get('preference_rule'))
        forget=re.fullmatch(r'(?i)(?:забудь|удали из памяти|отмени правило)\s+((?:memory_|feedback_rule_)[a-f0-9]+)',text)
        if forget:
            value=root.memory.forget(forget[1],**self.actor);guard()
            return AssistantResult(request_ref,value['deletion_state'],'chat','Запись удалена. '+value['backup_limitation'],payload={'source_data_class':'user_provided','deletion':value})
        if low in {'покажи память','что сохранено в памяти','экспортируй память','экспорт памяти'}:
            items=root.memory.export_objects(**self.actor)
            if low.startswith('экспорт'):return self._view(request_ref,items,status='export',prefix='Экспорт подтверждённых записей:\n')
            return self._view(request_ref,items)
        search=re.fullmatch(r'(?is)(?:найди в памяти|покажи память о|что я сохранил о)\s+(.{1,500})',text)
        if search:return self._view(request_ref,root.memory.search(search[1],**self.actor))
        inspect=re.fullmatch(r'(?i)(?:покажи запись|покажи правило)\s+((?:memory_|feedback_rule_)[a-f0-9]+)',text)
        if inspect:
            item=root.memory.inspect(inspect[1],**self.actor)
            return self._view(request_ref,[item] if item else [])
        return None
