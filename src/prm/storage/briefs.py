"""Owner-scoped immutable Brief versions and restartable visible bindings."""
import hashlib
from prm.briefs import BriefDocumentStore,_storage_document,_stored_document,brief_owner_ref_from_authenticated_private_tuple
from .postgres import PostgresStore,StorageError,StateConflict
from psycopg.types.json import Jsonb
import json

DDL=(
    'CREATE SCHEMA pa_briefs',
    'CREATE TABLE pa_briefs.meta(version integer PRIMARY KEY,checksum text NOT NULL)',
    '''CREATE TABLE pa_briefs.documents(owner text NOT NULL,id text NOT NULL,version bigint NOT NULL,digest text NOT NULL,
       payload jsonb NOT NULL,PRIMARY KEY(owner,id,version))''',
    'GRANT USAGE ON SCHEMA pa_briefs TO pa_test_app',
    'GRANT SELECT ON pa_briefs.meta TO pa_test_app',
    'GRANT SELECT,INSERT,DELETE ON pa_briefs.documents TO pa_test_app',
)
CHECKSUM=hashlib.sha256('\n'.join(DDL).encode()).hexdigest()

def install_briefs(target):
    if target.user!='pa_test_migrator':raise StorageError('dedicated synthetic migrator required')
    with PostgresStore(target).transaction() as tx:
        tx.conn.execute('SELECT pg_advisory_xact_lock(%s)',(87291014,))
        if tx.conn.execute("SELECT to_regclass('pa_briefs.meta') AS meta").fetchone()['meta'] is None:
            for statement in DDL:tx.conn.execute(statement)
            tx.conn.execute('INSERT INTO pa_briefs.meta VALUES(1,%s)',(CHECKSUM,))
        elif tx.conn.execute('SELECT version,checksum FROM pa_briefs.meta').fetchall()!=[{'version':1,'checksum':CHECKSUM}]:raise StorageError('Brief schema differs')


class DurableBriefStore(BriefDocumentStore):
    def __init__(self,target,*,owner_ref,registry=None):
        super().__init__();self.store=PostgresStore(target);self.owner_ref=owner_ref;self.registry=registry
        self.pending_dependencies={};self.pending_classes={};self.pending_scopes={}
        self.pending_inventory={};self.pending_coverage={}

    def _document_ref(self,brief_id):return 'brief_'+hashlib.sha256(brief_id.encode()).hexdigest()[:32]
    def _binding_ref(self,conversation_id):return 'brief_binding_'+hashlib.sha256(conversation_id.encode()).hexdigest()[:32]

    def bind_visible(self,**kwargs):
        owner=brief_owner_ref_from_authenticated_private_tuple(kwargs.get('authenticated_chat_id'),kwargs.get('authenticated_actor_id'),kwargs.get('authenticated_owner_chat_id'))
        if owner!=self.owner_ref or kwargs['document'].owner_ref!=owner:raise StorageError('exact private Brief owner required')
        document=kwargs['document'];comparison=kwargs.get('comparison_document')
        with self.store.transaction() as tx:
            from prm.runtime.deletion import lineage_lock
            lineage_lock(tx.conn,owner)
            for item in (document,comparison):
                if item is None:continue
                ref=self._document_ref(item.brief_id);encoded=_storage_document(item)
                raw=json.dumps(encoded,ensure_ascii=False,sort_keys=True).encode()
                if len(raw)>256000:raise StorageError('immutable Brief exceeds its bound')
                digest=hashlib.sha256(raw).hexdigest()
                old=tx.get(owner,'result',ref,version=item.version)
                if old is not None:
                    if old.payload.get('storage_digest')!=digest:raise StateConflict('immutable Brief version differs')
                    if self.registry is not None:
                        from prm.runtime.source_access import source_current
                        source_current(tx,self.registry,owner,old.payload.get('source_scopes',[]),archive_snapshots=old.payload.get('archive_snapshots',[]),require_snapshot=True)
                else:
                    scopes=self.pending_scopes.get(item.content_digest,[]);snapshots=getattr(self,'pending_snapshots',{}).get(item.content_digest,[])
                    classes=list(self.pending_classes.get(item.content_digest,('private_archive','private_connector_content')))
                    if self.registry is not None:
                        from prm.runtime.source_access import source_current
                        source_current(tx,self.registry,owner,scopes,archive_snapshots=snapshots,require_snapshot=True)
                    inventory=list({r['evidence_ref']:r for r in self.pending_inventory.get(item.content_digest,[])}.values())
                    pages=[];chunks=[];chunk=[]
                    for row in inventory:
                        if chunk and (len(chunk)>=40 or len(json.dumps(chunk+[row],ensure_ascii=False).encode())>40000):chunks.append(chunk);chunk=[]
                        chunk.append(row)
                    if chunk:chunks.append(chunk)
                    for index,rows in enumerate(chunks):
                        page_ref='briefmaterials_'+hashlib.sha256((ref+'\x1f'+str(item.version)+'\x1f'+str(index)).encode()).hexdigest()[:32]
                        stored=tx.put(owner,'result',page_ref,{'kind':'brief_material_inventory','parent_ref':ref,'brief_version':item.version,'rows':rows,
                            'data_classes':classes,'data_class':classes[0],'source_scopes':scopes,'archive_snapshots':snapshots},expected_version=0)
                        pages.append({'ref':page_ref,'digest':stored.digest,'count':len(rows)})
                        tx.conn.execute('INSERT INTO pa_memory.dependencies VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                            (owner,'result',ref,'result',page_ref))
                    tx.put(owner,'result',ref,{'kind':'brief_manifest','brief_id':item.brief_id,'version':item.version,
                        'content_digest':item.content_digest,'storage_digest':digest,'source_data_classes':classes,'source_scopes':scopes,
                        'archive_snapshots':snapshots,'material_pages':pages,'source_coverage':self.pending_coverage.get(item.content_digest)},expected_version=item.version-1)
                    tx.conn.execute('INSERT INTO pa_briefs.documents VALUES(%s,%s,%s,%s,%s)',(owner,item.brief_id,item.version,digest,Jsonb(encoded)))
                if tx.conn.execute("SELECT to_regclass('pa_memory.dependencies') AS meta").fetchone()['meta'] is not None:
                    for dependency in self.pending_dependencies.get(item.content_digest,()):
                        parent=tx.get(owner,dependency['namespace'],dependency['object_ref'])
                        if parent is None or parent.version!=dependency['version'] or parent.digest!=dependency['digest']:
                            raise StateConflict('Brief source changed or was deleted while building')
                        tx.conn.execute('INSERT INTO pa_memory.dependencies VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                            (owner,dependency['namespace'],dependency['object_ref'],'result',ref))
            ref=self._binding_ref(kwargs['conversation_id']);old=tx.get(owner,'conversation',ref)
            binding={'response_ref':kwargs['response_ref'],'brief_id':document.brief_id,'version':document.version,
                'comparison':None if comparison is None else {'brief_id':comparison.brief_id,'version':comparison.version},
                'active_item_number':kwargs.get('active_item_number'),'forgotten':False}
            tx.put(owner,'conversation',ref,binding,expected_version=old.version if old else 0)
            if tx.conn.execute("SELECT to_regclass('pa_memory.dependencies') AS meta").fetchone()['meta'] is not None:
                for item in (document,comparison):
                    if item is not None:
                        tx.conn.execute('INSERT INTO pa_memory.dependencies VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                            (owner,'result',self._document_ref(item.brief_id),'conversation',ref))
                        tx.conn.execute('INSERT INTO pa_memory.dependencies VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                            (owner,'result',self._document_ref(item.brief_id),'result',kwargs['response_ref']))
        super().bind_visible(**kwargs)

    def _load_visible(self,conversation_id,response_ref):
        item=self.store.get(self.owner_ref,'conversation',self._binding_ref(conversation_id))
        if item is None or item.payload.get('forgotten') or item.payload['response_ref']!=response_ref:return None
        value=item.payload
        def load(ref):
            doc=self.store.get(self.owner_ref,'result',self._document_ref(ref['brief_id']),version=ref['version'])
            if doc is None:raise StorageError('bound immutable Brief version unavailable')
            document=self._decode_document(doc)
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
        return self._decode_document(item) if item else None
    def source_scopes(self,brief_id,version):
        item=self.store.get(self.owner_ref,'result',self._document_ref(brief_id),version=version)
        return tuple(item.payload.get('source_scopes',())) if item else ()
    def archive_snapshots(self,brief_id,version):
        item=self.store.get(self.owner_ref,'result',self._document_ref(brief_id),version=version)
        return tuple(item.payload.get('archive_snapshots',())) if item else ()

    def _decode_document(self,item):
        if item.payload.get('kind')!='brief_manifest':return _stored_document(item.payload)
        with self.store.transaction() as tx:
            row=tx.conn.execute('SELECT payload,digest FROM pa_briefs.documents WHERE owner=%s AND id=%s AND version=%s',
                (self.owner_ref,item.payload['brief_id'],item.payload['version'])).fetchone()
        if row is None or row['digest']!=item.payload['storage_digest'] or hashlib.sha256(json.dumps(row['payload'],ensure_ascii=False,sort_keys=True).encode()).hexdigest()!=row['digest']:
            raise StorageError('immutable Brief storage digest differs')
        document=_stored_document(row['payload'])
        if document.content_digest!=item.payload['content_digest'] or document.owner_ref!=self.owner_ref:raise StorageError('Brief identity differs')
        return document
