"""Owner-scoped immutable Brief versions and restartable visible bindings."""
import hashlib
from prm.briefs import BriefDocumentStore,_storage_document,_stored_document,brief_owner_ref_from_authenticated_private_tuple
from .postgres import PostgresStore,StorageError,StateConflict


class DurableBriefStore(BriefDocumentStore):
    def __init__(self,target,*,owner_ref):
        super().__init__();self.store=PostgresStore(target);self.owner_ref=owner_ref

    def _document_ref(self,brief_id):return 'brief_'+hashlib.sha256(brief_id.encode()).hexdigest()[:32]
    def _binding_ref(self,conversation_id):return 'brief_binding_'+hashlib.sha256(conversation_id.encode()).hexdigest()[:32]

    def bind_visible(self,**kwargs):
        owner=brief_owner_ref_from_authenticated_private_tuple(kwargs.get('authenticated_chat_id'),kwargs.get('authenticated_actor_id'),kwargs.get('authenticated_owner_chat_id'))
        if owner!=self.owner_ref or kwargs['document'].owner_ref!=owner:raise StorageError('exact private Brief owner required')
        document=kwargs['document'];comparison=kwargs.get('comparison_document')
        with self.store.transaction() as tx:
            for item in (document,comparison):
                if item is None:continue
                ref=self._document_ref(item.brief_id);encoded=_storage_document(item)
                old=tx.get(owner,'result',ref,version=item.version)
                if old is not None:
                    if old.payload!=encoded:raise StateConflict('immutable Brief version differs')
                else:tx.put(owner,'result',ref,encoded,expected_version=item.version-1)
            ref=self._binding_ref(kwargs['conversation_id']);old=tx.get(owner,'conversation',ref)
            binding={'response_ref':kwargs['response_ref'],'brief_id':document.brief_id,'version':document.version,
                'comparison':None if comparison is None else {'brief_id':comparison.brief_id,'version':comparison.version},
                'active_item_number':kwargs.get('active_item_number'),'forgotten':False}
            tx.put(owner,'conversation',ref,binding,expected_version=old.version if old else 0)
        super().bind_visible(**kwargs)

    def _load_visible(self,conversation_id,response_ref):
        item=self.store.get(self.owner_ref,'conversation',self._binding_ref(conversation_id))
        if item is None or item.payload.get('forgotten') or item.payload['response_ref']!=response_ref:return None
        value=item.payload
        def load(ref):
            doc=self.store.get(self.owner_ref,'result',self._document_ref(ref['brief_id']),version=ref['version'])
            if doc is None:raise StorageError('bound immutable Brief version unavailable')
            document=_stored_document(doc.payload)
            if document.owner_ref!=self.owner_ref:raise StorageError('bound Brief owner differs')
            return document
        return value,load(value),load(value['comparison']) if value['comparison'] else None

    def resolve_visible(self,*,conversation_id,response_ref):
        loaded=self._load_visible(conversation_id,response_ref)
        return (loaded[1],loaded[2]) if loaded else None

    def visible_item_number(self,*,conversation_id,response_ref):
        loaded=self._load_visible(conversation_id,response_ref)
        return loaded[0]['active_item_number'] if loaded else None

    def forget_conversation(self,conversation_id):
        with self.store.transaction() as tx:
            ref=self._binding_ref(conversation_id);old=tx.get(self.owner_ref,'conversation',ref)
            if old:tx.put(self.owner_ref,'conversation',ref,{'forgotten':True},expected_version=old.version)
        super().forget_conversation(conversation_id)

    def get_persisted_document(self,*,authenticated_chat_id,authenticated_actor_id,authenticated_owner_chat_id,brief_id,version,**kwargs):
        owner=brief_owner_ref_from_authenticated_private_tuple(authenticated_chat_id,authenticated_actor_id,authenticated_owner_chat_id)
        if owner!=self.owner_ref:return None
        item=self.store.get(owner,'result',self._document_ref(brief_id),version=version)
        return _stored_document(item.payload) if item else None
