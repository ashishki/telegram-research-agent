"""Source enumeration facts, identities and bounded selection; never authority."""
from __future__ import annotations
from dataclasses import dataclass,field
from datetime import datetime,timezone
import hashlib
import json
from prm.storage.postgres import StorageError

CLASSES=frozenset({'private_archive','private_connector_metadata','private_connector_content','user_provided','public','model_generated'})


def _text(value,maximum,*,optional=False):
    if optional and value is None:return
    if not isinstance(value,str) or not 0<len(value)<=maximum or value.strip()!=value:raise StorageError('bounded explicit source reference required')


def _time(value):
    if value is None:return None
    if isinstance(value,str):
        try:value=datetime.fromisoformat(value.replace('Z','+00:00'))
        except ValueError:return None
    if not isinstance(value,datetime) or value.tzinfo is None:return None
    return value.astimezone(timezone.utc)


def _json(value,limit=65536):
    try:raw=json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
    except (TypeError,ValueError,RecursionError):raise StorageError('bounded JSON source observation required') from None
    if len(raw.encode())>limit:raise StorageError('source observation exceeds bound')
    return raw


@dataclass(frozen=True)
class SourceResource:
    owner_ref: str | None
    resource_ref: str
    kind: str
    data_class: str
    connection_ref: str | None = None
    account_ref: str | None = None
    scope_digest: str | None = None

    def __post_init__(self):
        for value in (self.owner_ref,self.connection_ref,self.account_ref,self.scope_digest):_text(value,256,optional=True)
        _text(self.resource_ref,256)
        if self.kind not in {'archive','web','github','mail','calendar','contacts','academic','local'} or self.data_class not in CLASSES:
            raise StorageError('explicit source kind/data class required')
        if self.data_class!='public' and self.owner_ref is None:raise StorageError('private source owner required')
        if self.account_ref is not None and self.connection_ref is None:raise StorageError('source account requires connection identity')

    def to_dict(self):return {name:getattr(self,name) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class SourceRecord:
    resource: SourceResource
    external_ref: str
    source_version: str | None
    publication_time: datetime | None
    event_time: datetime | None
    discovery_time: datetime | None
    encoded_payload: str = field(repr=False)

    def __post_init__(self):
        if type(self.resource)is not SourceResource:raise StorageError('typed source resource required')
        _text(self.external_ref,2048);_text(self.source_version,256,optional=True)
        for value in (self.publication_time,self.event_time,self.discovery_time):
            if value is not None and (not isinstance(value,datetime) or value.tzinfo is None):raise StorageError('aware source time or explicit unknown required')
        if not isinstance(self.encoded_payload,str):raise StorageError('immutable source payload required')
        try:value=json.loads(self.encoded_payload)
        except (ValueError,RecursionError):raise StorageError('invalid immutable source payload') from None
        if not isinstance(value,dict) or _json(value)!=self.encoded_payload:raise StorageError('canonical source payload required')

    @classmethod
    def from_item(cls,item,resource):
        if not isinstance(item,dict):raise StorageError('source item must be an observation object')
        reference=item.get('evidence_id') or item.get('id') or item.get('post_id') or item.get('path') or item.get('source_url')
        if type(reference)is int:reference=str(reference)
        version=item.get('source_version') or item.get('blob_sha') or item.get('changeKey')
        return cls(resource,reference,version,_time(item.get('publication_time')) if 'publication_time' in item else _time(item.get('posted_at') or item.get('published_at')),
            _time(item.get('event_time')),_time(item.get('first_discovered_at') or item.get('discovery_time') or item.get('discovered_at')), _json(item))

    @property
    def payload(self):return json.loads(self.encoded_payload)
    @property
    def evidence_ref(self):
        identity=[self.resource.to_dict(),self.external_ref,self.source_version,hashlib.sha256(self.encoded_payload.encode()).hexdigest()]
        return 'evidence_'+hashlib.sha256(_json(identity).encode()).hexdigest()[:32]

    def metadata(self):
        return {'evidence_ref':self.evidence_ref,'resource':self.resource.to_dict(),'external_ref':self.external_ref,
            'source_version':self.source_version,'payload_digest':hashlib.sha256(self.encoded_payload.encode()).hexdigest(),
            'publication_time':self.publication_time.isoformat() if self.publication_time else None,
            'event_time':self.event_time.isoformat() if self.event_time else None,'discovery_time':self.discovery_time.isoformat() if self.discovery_time else None}


@dataclass(frozen=True)
class SourceBatch:
    items: tuple[SourceRecord,...] = field(repr=False)
    selected_resources: tuple[SourceResource,...]
    checked_at: datetime | None
    completeness: str
    omitted_count: int | None = None
    reason: str | None = None
    continuation: str | None = field(default=None,repr=False)
    watermark: str | None = None
    schema_version: str = 'assistant.source_batch.v1'

    def __post_init__(self):
        if not isinstance(self.items,tuple) or len(self.items)>2048 or not isinstance(self.selected_resources,tuple) or not 1<=len(self.selected_resources)<=16 or any(type(r)is not SourceResource for r in self.selected_resources):raise StorageError('bounded typed source batch required')
        if len({r.owner_ref for r in self.selected_resources})!=1:raise StorageError('source batch owners differ')
        if any(type(i)is not SourceRecord or i.resource not in self.selected_resources for i in self.items):raise StorageError('source item outside selected resources')
        if len({i.evidence_ref for i in self.items})!=len(self.items):raise StorageError('duplicate source identity within a batch')
        if self.checked_at is not None and (not isinstance(self.checked_at,datetime) or self.checked_at.tzinfo is None):raise StorageError('aware actual source check time required')
        if self.schema_version!='assistant.source_batch.v1':raise StorageError('unsupported source batch schema')
        if self.completeness not in {'complete','partial','unknown','unavailable'}:raise StorageError('explicit source completeness required')
        if self.omitted_count is not None and (type(self.omitted_count)is not int or not 0<=self.omitted_count<=1000000000):raise StorageError('known nonnegative omitted count or unknown required')
        for value,limit in ((self.reason,256),(self.continuation,2048),(self.watermark,256)):_text(value,limit,optional=True)
        if self.completeness=='complete' and (self.omitted_count!=0 or self.continuation is not None or self.checked_at is None):raise StorageError('complete source batch requires finished checked enumeration')
        if self.completeness=='unavailable' and self.items:raise StorageError('unavailable source cannot claim received items')
        if self.completeness!='complete' and self.reason is None:raise StorageError('source limitation reason required')
        _json([i.payload for i in self.items],2097152)

    @classmethod
    def from_items(cls,items,resource,*,checked_at,completeness,omitted_count=None,reason=None,continuation=None,watermark=None):
        if not isinstance(items,(list,tuple)):raise StorageError('bounded source item list required')
        return cls(tuple(SourceRecord.from_item(i,resource) for i in items),(resource,),checked_at,completeness,omitted_count,reason,continuation,watermark)

    @property
    def received_count(self):return len(self.items)
    def __iter__(self):return (item.payload for item in self.items)
    def __len__(self):return len(self.items)
    def metadata(self):
        return {'schema_version':self.schema_version,'selected_resources':[r.to_dict() for r in self.selected_resources],
            'checked_at':self.checked_at.isoformat() if self.checked_at else None,'completeness':self.completeness,
            'received_count':len(self.items),'omitted_count':self.omitted_count,'reason':self.reason,
            'has_continuation':self.continuation is not None,'watermark':self.watermark}


def normalize_source_batch(value,resource,*,checked_at):
    if type(value)is SourceBatch:
        if value.selected_resources!=(resource,):raise StorageError('collector resource/owner differs')
        return value
    if isinstance(value,dict):value=value.get('items')
    if not isinstance(value,(list,tuple)):raise StorageError('source batch observation required')
    return SourceBatch.from_items(value,resource,checked_at=checked_at,completeness='unknown',reason='legacy_bounded_collector')


@dataclass(frozen=True)
class EvidenceBundle:
    batches: tuple[SourceBatch,...] = field(repr=False)
    selected: tuple[SourceRecord,...] = field(repr=False)
    candidate_count: int
    cited_count: int | None = None
    excluded_refs: tuple[str,...] = ()

    def __post_init__(self):
        if not isinstance(self.batches,tuple) or not self.batches or len(self.batches)>16 or any(type(b)is not SourceBatch for b in self.batches):raise StorageError('typed evidence batches required')
        if not isinstance(self.selected,tuple) or len(self.selected)>48 or any(type(r)is not SourceRecord or not any(r in b.items for b in self.batches) for r in self.selected):raise StorageError('selected evidence outside received source snapshots')
        identities={r.evidence_ref for b in self.batches for r in b.items}
        if not isinstance(self.excluded_refs,tuple) or len(set(self.excluded_refs))!=len(self.excluded_refs) or not set(self.excluded_refs)<=identities:raise StorageError('excluded projections must bind received evidence')
        eligible=identities-set(self.excluded_refs)
        if type(self.candidate_count)is not int or self.candidate_count!=len(eligible) or len({r.evidence_ref for r in self.selected})!=len(self.selected) or not {r.evidence_ref for r in self.selected}<=eligible:raise StorageError('actual distinct eligible candidate count required')
        if self.cited_count is not None and (type(self.cited_count)is not int or not 0<=self.cited_count<=len(self.selected)):raise StorageError('actual cited subset count required')

    @classmethod
    def select(cls,batches,*,maximum_items,eligible_refs=None):
        if not isinstance(batches,tuple) or not 1<=len(batches)<=16 or any(type(b)is not SourceBatch for b in batches) or type(maximum_items)is not int or not 0<=maximum_items<=48:raise StorageError('bounded typed evidence selection required')
        if len({r.owner_ref for b in batches for r in b.selected_resources})!=1:raise StorageError('evidence owners differ')
        identities={r.evidence_ref for b in batches for r in b.items}
        if eligible_refs is not None and (not isinstance(eligible_refs,frozenset) or not eligible_refs<=identities):raise StorageError('eligible projections must bind received evidence')
        excluded_set=identities-eligible_refs if eligible_refs is not None else set()
        excluded=tuple(sorted(excluded_set))
        candidates=[];seen=set();index=0
        while any(index<len(b.items) for b in batches):
            for batch in batches:
                if index<len(batch.items):
                    item=batch.items[index]
                    if item.evidence_ref not in seen and item.evidence_ref not in excluded_set:candidates.append(item);seen.add(item.evidence_ref)
            index+=1
        return cls(batches,tuple(candidates[:maximum_items]),len(candidates),excluded_refs=excluded)

    @property
    def received_count(self):return sum(len(b.items) for b in self.batches)
    @property
    def selected_count(self):return len(self.selected)
    @property
    def model_omitted_count(self):return self.candidate_count-len(self.selected)
    @property
    def conflict_count(self):
        versions={}
        for b in self.batches:
            for r in b.items:
                key=_json([r.resource.to_dict(),r.external_ref,r.source_version])
                versions.setdefault(key,set()).add(r.encoded_payload)
        return sum(len(values)>1 for values in versions.values())
    def with_citations(self,refs):
        from dataclasses import replace
        if not isinstance(refs,tuple) or len(set(refs))!=len(refs) or not set(refs)<={r.evidence_ref for r in self.selected}:raise StorageError('citations must bind exact selected evidence identities')
        return replace(self,cited_count=len(refs))
    def metadata(self):
        return {'schema_version':'assistant.evidence_bundle.v1','batches':[b.metadata() for b in self.batches],
            'received_count':self.received_count,'candidate_count':self.candidate_count,'selected_count':len(self.selected),
            'model_omitted_count':self.model_omitted_count,'cited_count':self.cited_count,'conflict_count':self.conflict_count,
            'projection_rejected_count':len(self.excluded_refs),
            'selected_evidence':[r.metadata() for r in self.selected]}
