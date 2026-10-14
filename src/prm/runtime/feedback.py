"""Native owner feedback and explicit scoped rules in the existing version store."""
from dataclasses import replace
import hashlib,json,re
from prm.feedback import FeedbackEvent,LABELS,validate_preference_rule
from prm.contracts import AssistantResult
from prm.capabilities import CapabilityDenied
from prm.storage.postgres import StorageError,StateConflict


class FeedbackRuntime:
    def __init__(self,root):self.root=root;self.weekly_prompt=False

    def rules(self):
        from .memory_context import memory_current,binding_provenance
        result=[]
        with self.root.queue.store.transaction() as tx:
            rows=tx.conn.execute("SELECT h.object_id FROM pa_runtime.object_heads h JOIN pa_runtime.object_versions v USING(owner,namespace,object_id,version) WHERE h.owner=%s AND h.namespace='memory' AND v.payload ? 'preference_rule' ORDER BY h.object_id LIMIT 32",(self.root.owner_ref,)).fetchall()
            for row in rows:
                item=tx.get(self.root.owner_ref,'memory',row['object_id'])
                try:
                    memory_current(tx,self.root.owner_ref,{'memory_ref':item.object_id,'version':item.version,'digest':item.digest},require_typed=True)
                    binding_provenance(self.root,tx,item.payload.get('source_bindings',[]));validate_preference_rule(item.payload['preference_rule'])
                except (StorageError,CapabilityDenied,KeyError,TypeError,ValueError):continue
                result.append(item)
        return tuple(result)

    def record(self,document,manifest,*,kind,request_ref,idempotency_key,story_number=None,emoji=(),origin='explicit_owner'):
        root=self.root
        with root.queue.store.transaction() as tx:
            from .deletion import lineage_lock
            from .source_access import source_current,project_bindings_current,memory_bindings_current
            lineage_lock(tx.conn,root.owner_ref)
            current=tx.get(root.owner_ref,'result',manifest.object_id,version=manifest.version)
            if current is None or current.digest!=manifest.digest:raise CapabilityDenied('feedback document changed or deleted')
            project_bindings_current(tx,root.owner_ref,current.payload.get('project_bindings',[]));memory_bindings_current(tx,root.owner_ref,current.payload.get('memory_bindings',[]))
            source_current(tx,root.registry,root.owner_ref,current.payload.get('source_scopes',[]),archive_snapshots=current.payload.get('archive_snapshots',[]),require_snapshot=True)
            count=len(document.editorial.stories) if document.editorial else len(document.items)
            if story_number is not None and not 1<=story_number<=count:raise StorageError('feedback story unavailable')
            now=tx.conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
            ref='feedback_'+hashlib.sha256((root.owner_ref+':'+idempotency_key).encode()).hexdigest()[:32]
            old=tx.get(root.owner_ref,'result',ref)
            if old:
                value=old.payload['event']
                if (value['brief_id'],value['brief_version'],value['content_digest'],value['kind'],value['story_number'],value['emoji'])!=(document.brief_id,document.version,document.content_digest,kind,story_number,list(emoji)):raise StateConflict('feedback identity already bound')
                return old
            event=FeedbackEvent(root.owner_ref,document.brief_id,document.version,document.content_digest,kind,now.isoformat(),story_number,tuple(emoji),origin)
            item=tx.put(root.owner_ref,'result',ref,{'kind':'feedback_event','event':event.to_dict(),'source_data_classes':current.payload['source_data_classes'],
                'data_classes':current.payload['source_data_classes'],'data_class':current.payload['source_data_classes'][0],
                'source_scopes':current.payload.get('source_scopes',[]),'archive_snapshots':current.payload.get('archive_snapshots',[])},expected_version=0)
            tx.conn.execute('INSERT INTO pa_memory.dependencies VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(root.owner_ref,'result',current.object_id,'result',ref))
            if request_ref:
                if tx.get(root.owner_ref,'conversation',request_ref) is None:raise StorageError('feedback input unavailable')
                tx.conn.execute('INSERT INTO pa_memory.dependencies VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(root.owner_ref,'conversation',request_ref,'result',ref))
            return item

    def preview_rule(self,request_ref,lease,*,topic,signal):
        rule=validate_preference_rule({'topic':topic,'signal':signal})
        from .memory_dialogue import MemoryDialogueRuntime
        description='Правило только для темы «'+rule['topic']+'»: '+{'useful':'выше интерес','not_topic':'ниже применимость темы','known':'ниже новизна','too_long':'предпочитать короткое представление','incorrect':'проверять надёжность'}[signal]+'. Критические события и противоречия сохраняются.'
        existing=next((item for item in self.rules() if item.payload['preference_rule']['topic']==rule['topic']),None)
        return MemoryDialogueRuntime(self.root).preview(request_ref,lease,text=description,kind='preference',
            object_ref=existing.object_id if existing else 'feedback_rule_'+hashlib.sha256((request_ref+topic).encode()).hexdigest()[:32],
            expected_version=existing.version if existing else 0,preference_rule=rule)

    def try_answer(self,request,*,request_ref,lease,guard):
        text=request.query.strip();low=text.casefold().rstrip('?.!')
        if text.startswith('/feedbackrule '):
            value=json.loads(text.partition(' ')[2]);rule=validate_preference_rule(value)
            return self.preview_rule(request_ref,lease,topic=rule['topic'],signal=rule['signal'])
        rule=re.fullmatch(r'(?is)(?:не показывай тему|меньше темы)\s+(.{1,120})',text)
        if rule and hasattr(self.root,'memory'):return self.preview_rule(request_ref,lease,topic=rule[1],signal='not_topic')
        rule=re.fullmatch(r'(?is)(?:больше темы|чаще тему)\s+(.{1,120})',text)
        if rule and hasattr(self.root,'memory'):return self.preview_rule(request_ref,lease,topic=rule[1],signal='useful')
        if low in {'почему это показано','почему показано','почему выбран этот материал'}:
            return self.root.documents.view_current(request,request_ref=request_ref,lease=lease,guard=guard,why_signals=True)
        kind=LABELS.get(low)
        match=re.fullmatch(r'(?i)(полезно|не тема|уже знал|длинно|неверно|применил)\s+(?:пункт\s*)?(\d{1,2})',text)
        story=int(match[2]) if match else None
        if match:kind=LABELS[match[1].casefold()]
        if kind is None:return None
        resolved=self.root.documents.resolve_current(request,request_ref=request_ref,lease=lease,guard=guard)
        if resolved is None:return AssistantResult(request_ref,'clarify','chat','Выбери обзор и пункт для этой обратной связи.',payload={'source_data_class':'user_provided'})
        doc,manifest,active=resolved;story=story or active
        item=self.record(doc,manifest,kind=kind,request_ref=request_ref,idempotency_key=request_ref,story_number=story)
        text='Записано для этой версии обзора: '+kind+'.'
        if kind=='applied':text+=' Применение отмечено с твоих слов; измеренный эффект неизвестен.'
        text+=' Постоянное правило не изменено.'
        return self.root.documents.remember_view(request_ref,doc,manifest,text,view='feedback',active_item=story,extra={'feedback_ref':item.object_id,'feedback_event':item.payload['event']})

    def optional_prompt(self):return 'Если полезно, отметь один пункт: «полезно», «не тема», «уже знал», «длинно», «неверно» или «применил».' if self.weekly_prompt else ''

    def receive_reaction(self,update,envelope):
        binding=self.root.ingress.bindings.for_message(envelope.destination,envelope.message_id)
        if binding is None or binding.origin_kind!='bot' or not binding.response_ref:return None
        item=self.root.queue.store.get(self.root.owner_ref,'result',binding.response_ref,version=binding.response_version)
        if item is None:return None
        value=item.payload.get('payload',{});pointer=value.get('document_binding') or value.get('brief_document')
        if pointer is None:return None
        try:document,manifest=self.root.documents.load(pointer['brief_id'],pointer['version'])
        except (StorageError,CapabilityDenied):return None
        ref='feedback_input_'+hashlib.sha256((envelope.destination.bot_ref+':'+str(update['update_id'])).encode()).hexdigest()[:32]
        raw={'schema_version':'assistant.feedback_reaction_input.v1','input_digest':envelope.input_digest,'update_id':update['update_id']}
        with self.root.queue.store.transaction() as tx:
            self.root.ingress.bindings._lineage_lock(tx);self.root.ingress.bindings.update_identity_in(tx,update)
            old=tx.get(self.root.owner_ref,'conversation',ref)
            if old and old.payload!=raw:raise StateConflict('reaction update changed')
            if old is None:tx.put(self.root.owner_ref,'conversation',ref,raw,expected_version=0)
        emojis=tuple(v.get('emoji') or ('custom:'+v['custom_emoji_id'] if v.get('custom_emoji_id') else 'paid') for v in update['message_reaction']['new_reaction'])
        return self.record(document,manifest,kind='reaction_interest' if emojis else 'unknown',request_ref=ref,idempotency_key=ref,
            emoji=emojis,origin='personal_reaction')

    def import_legacy(self,row,*,brief_id,version,content_digest,legacy_ref,idempotency_key,chat_id,actor_id,owner_chat_id,personal_reaction=False,confirmed_owner=False):
        """Explicit authenticated adapter seam, with no private database discovery."""
        from prm.briefs import brief_owner_ref_from_authenticated_private_tuple
        from prm.feedback import from_legacy_feedback
        if brief_owner_ref_from_authenticated_private_tuple(chat_id,actor_id,owner_chat_id)!=self.root.owner_ref:raise CapabilityDenied('legacy feedback owner differs')
        if confirmed_owner is not True or row.get('confirmation_state','confirmed')!='confirmed':raise CapabilityDenied('legacy feedback needs explicit confirmed owner import')
        if not isinstance(legacy_ref,str) or not 1<=len(legacy_ref)<=128:raise StorageError('explicit legacy source reference required')
        doc,manifest=self.root.documents.load(brief_id,version)
        if doc.content_digest!=content_digest:raise StateConflict('legacy feedback exact version differs')
        from datetime import datetime,timezone
        event=from_legacy_feedback(row,owner_ref=self.root.owner_ref,brief_id=brief_id,brief_version=version,content_digest=content_digest,
            observed_at=datetime.now(timezone.utc).isoformat(),personal_reaction=personal_reaction)
        marker='feedback_input_'+hashlib.sha256((legacy_ref+':'+idempotency_key).encode()).hexdigest()[:32]
        metadata={'schema_version':'assistant.legacy_feedback_binding.v1','legacy_ref':legacy_ref,'brief_id':brief_id,'version':version,
            'content_digest':content_digest,'kind':event.kind,'origin':event.origin}
        with self.root.queue.store.transaction() as tx:
            old=tx.get(self.root.owner_ref,'conversation',marker)
            if old and old.payload!=metadata:raise StateConflict('legacy feedback import identity differs')
            if old is None:tx.put(self.root.owner_ref,'conversation',marker,metadata,expected_version=0)
        return self.record(doc,manifest,kind=event.kind,request_ref=marker,idempotency_key=marker,story_number=event.story_number,emoji=event.emoji,origin=event.origin)
