"""Deferred actual cleanup, malicious MIME and transcript invalidation."""
from tests.pai_runtime_fixtures import pai
from prm.runtime.media import MediaRuntime
from prm.storage.postgres import StorageError
import pytest


def test_malicious_mime_is_rejected_before_file_and_plain_voice_is_cleaned(pai):
    runtime=MediaRuntime(pai.root,temporary_root=pai.path/'media')
    with pytest.raises(StorageError):runtime.ingest(content=b'<script>steal()</script>',kind='image',mime_type='image/png')
    assert not list(runtime.path.iterdir())
    asset=runtime.ingest(content=b'OggSsynthetic_voice',kind='voice',mime_type='audio/ogg')
    assert runtime.extract(asset)['status']=='transcription_unavailable'
    runtime.cleanup(asset);assert not (runtime.path/asset.media_ref).exists()


def test_speech_rejection_is_distinct_from_invalid_reply_and_fences_survive(pai):
    from dataclasses import replace
    from tests.pai_runtime_fixtures import allow
    from prm.runtime.speech import SpeechTranscriber
    from prm.runtime.model_errors import ModelProviderRejected,ModelResponseInvalid
    from prm.runtime.model_attempts import ModelAttemptAlreadyRecorded
    from prm.runtime.cost_cache import CostCacheRuntime
    root=pai.root;media=MediaRuntime(root,temporary_root=pai.path/'speech_errors')
    allow(pai,'media.transcribe','resource_voice','user_provided','voice.transcription')
    rejected=SpeechTranscriber(root,endpoint=replace(root.model_endpoint,endpoint=pai.origin+'/speech/rejected'),upper_bound=0,resource_ref='resource_voice')
    asset=media.ingest(content=b'OggS synthetic voice input',kind='voice',mime_type='audio/ogg')
    try:
        with pytest.raises(ModelProviderRejected) as failure:rejected(asset,media.path/asset.media_ref,task_ref='speech_rejected_task')
        assert failure.value.status_code==404 and not failure.value.retry_allowed
        retry=media.ingest(content=b'OggS synthetic voice input',kind='voice',mime_type='audio/ogg')
        try:
            with pytest.raises(ModelAttemptAlreadyRecorded):rejected(retry,media.path/retry.media_ref,task_ref='speech_rejected_task')
        finally:media.cleanup(retry)
        assert len([row for row in pai.requests if row[0]=='rejected'])==1
        assert CostCacheRuntime(root).task_cost('speech_rejected_task')['unknown_priced_attempts']==1
        malformed=SpeechTranscriber(root,endpoint=replace(root.model_endpoint,endpoint=pai.origin+'/speech/malformed'),upper_bound=0,resource_ref='resource_voice')
        invalid=media.ingest(content=b'OggS synthetic invalid reply input',kind='voice',mime_type='audio/ogg')
        try:
            with pytest.raises(ModelResponseInvalid):malformed(invalid,media.path/invalid.media_ref,task_ref='speech_invalid_task')
        finally:media.cleanup(invalid)
        invalid_retry=media.ingest(content=b'OggS synthetic invalid reply input',kind='voice',mime_type='audio/ogg')
        try:
            with pytest.raises(ModelAttemptAlreadyRecorded):malformed(invalid_retry,media.path/invalid_retry.media_ref,task_ref='speech_invalid_task')
        finally:media.cleanup(invalid_retry)
        assert len([row for row in pai.requests if row[0]=='malformed'])==1
    finally:media.cleanup(asset)


def test_vision_http_rejection_preserves_logical_retry_fence(pai):
    from dataclasses import replace
    from tests.pai_runtime_fixtures import allow
    from prm.runtime.vision import VisionAdapter
    from prm.runtime.model_errors import ModelProviderRejected
    from prm.runtime.model_attempts import ModelAttemptAlreadyRecorded
    root=pai.root;media=MediaRuntime(root,temporary_root=pai.path/'vision_errors')
    allow(pai,'media.vision','resource_image','user_provided','media.vision')
    adapter=VisionAdapter(root,endpoint=replace(root.model_endpoint,endpoint=pai.origin+'/vision/rejected'),upper_bound=0,resource_ref='resource_image')
    asset=media.ingest(content=b'\x89PNG\r\n\x1a\nsynthetic_image',kind='image',mime_type='image/png')
    try:
        with pytest.raises(ModelProviderRejected) as failure:adapter(asset,'Synthetic question',media.path/asset.media_ref,task_ref='vision_rejected_task')
        assert failure.value.status_code==404 and not failure.value.retry_allowed
        retry=media.ingest(content=b'\x89PNG\r\n\x1a\nsynthetic_image',kind='image',mime_type='image/png')
        try:
            with pytest.raises(ModelAttemptAlreadyRecorded):adapter(retry,'Synthetic question',media.path/retry.media_ref,task_ref='vision_rejected_task')
        finally:media.cleanup(retry)
        assert len([row for row in pai.requests if row[0]=='rejected'])==1
    finally:media.cleanup(asset)


def media_adapter(pai,modality,endpoint_suffix):
    from dataclasses import replace
    from tests.pai_runtime_fixtures import allow
    from prm.runtime.speech import SpeechTranscriber
    from prm.runtime.vision import VisionAdapter
    root=pai.root
    if modality=='speech':
        allow(pai,'media.transcribe','resource_voice','user_provided','voice.transcription')
        adapter=SpeechTranscriber(root,endpoint=replace(root.model_endpoint,endpoint=pai.origin+'/speech/'+endpoint_suffix),
            upper_bound=3,resource_ref='resource_voice')
        def invoke(asset,path,task):return adapter(asset,path,task_ref=task)
        return invoke,{'content':b'OggS synthetic voice input','kind':'voice','mime_type':'audio/ogg'}
    allow(pai,'media.vision','resource_image','user_provided','media.vision')
    adapter=VisionAdapter(root,endpoint=replace(root.model_endpoint,endpoint=pai.origin+'/vision/'+endpoint_suffix),
        upper_bound=3,resource_ref='resource_image')
    def invoke(asset,path,task):return adapter(asset,'Synthetic question',path,task_ref=task)
    return invoke,{'content':b'\x89PNG\r\n\x1a\nsynthetic image','kind':'image','mime_type':'image/png'}


@pytest.mark.parametrize('modality',['speech','vision'])
@pytest.mark.parametrize('failure_stage',['ack_loss','accounting'])
def test_media_post_attempt_failures_are_typed_and_reconstructed_clients_cannot_replay(pai,monkeypatch,modality,failure_stage):
    from prm.runtime.cost_cache import CostCacheRuntime
    from prm.runtime.model_errors import MediaOutcomeUnknown,MediaAccountingUnconfirmed
    from prm.runtime.model_attempts import ModelAttemptAlreadyRecorded
    media=MediaRuntime(pai.root,temporary_root=pai.path/'fenced_media')
    suffix='ack-loss' if failure_stage=='ack_loss' else 'accepted'
    invoke,content=media_adapter(pai,modality,suffix)
    task='media_failure_'+modality+'_'+failure_stage
    if failure_stage=='accounting':
        def failed_record(*args,**kwargs):raise StorageError('synthetic usage acknowledgment lost')
        monkeypatch.setattr(CostCacheRuntime,'record',failed_record)
    asset=media.ingest(**content)
    expected=MediaOutcomeUnknown if failure_stage=='ack_loss' else MediaAccountingUnconfirmed
    with pytest.raises(expected) as failure:invoke(asset,media.path/asset.media_ref,task)
    error=failure.value
    assert not error.retry_allowed and error.receipt.external_call_attempted
    assert error.receipt.delivery_outcome==('unknown' if failure_stage=='ack_loss' else 'accepted')
    assert error.attempt_ref.startswith('model_attempt_')
    if failure_stage=='accounting':
        assert error.result==('Synthetic transcription.' if modality=='speech' else {'status':'ok','text':'Synthetic image answer.',
            'media_ref':asset.media_ref,'page_refs':[1],'extraction_method':'vision'})
        assert not error.receipt.usage_recorded and error.receipt.estimated_cost_usd is None
        assert error.receipt.text==('Synthetic transcription.' if modality=='speech' else 'Synthetic image answer.')
    assert len(error.operation_refs)==1 and 'Anthropic' not in str(error)
    operation=next(op for op in pai.root.registry.snapshot(pai.root.owner_ref)['operations'] if op['ref']==error.operation_refs[0])
    assert operation['state'] in {'unknown','accepted'} and operation['actual'] is None
    assert all(window['consumed']==3 for window in pai.root.registry.snapshot(pai.root.owner_ref)['windows'])
    before=len(pai.requests)
    retry,content=media_adapter(pai,modality,suffix)
    second=media.ingest(**content)
    with pytest.raises(ModelAttemptAlreadyRecorded):retry(second,media.path/second.media_ref,task)
    assert len(pai.requests)==before==1
    assert all(window['reserved']==0 and window['consumed']==3 for window in pai.root.registry.snapshot(pai.root.owner_ref)['windows'])


@pytest.mark.parametrize('modality',['speech','vision'])
def test_media_file_growth_is_rejected_without_transport_or_logical_fence(pai,modality):
    media=MediaRuntime(pai.root,temporary_root=pai.path/'oversized_media')
    invoke,content=media_adapter(pai,modality,'accepted')
    asset=media.ingest(**content);path=media.path/asset.media_ref
    path.write_bytes(content['content']+b'x'*(16000001 if modality=='speech' else 5000001))
    task='media_local_growth_'+modality
    with pytest.raises(StorageError,match='bounded media identity changed'):invoke(asset,path,task)
    assert not pai.requests
    with pai.root.queue.store.transaction() as tx:
        count=tx.conn.execute("SELECT count(*) AS n FROM pa_runtime.object_heads WHERE owner=%s AND object_id LIKE 'model_attempt_%%'",(pai.root.owner_ref,)).fetchone()['n']
    assert count==0
    assert all(window['reserved']==0 and window['consumed']==0 for window in pai.root.registry.snapshot(pai.root.owner_ref)['windows'])
    valid=media.ingest(**content)
    assert invoke(valid,media.path/valid.media_ref,task)
    assert len(pai.requests)==1


def test_vision_encoded_body_bound_precedes_attempt_and_releases_reservation(pai,monkeypatch):
    from prm.runtime import vision
    media=MediaRuntime(pai.root,temporary_root=pai.path/'body_bound')
    invoke,content=media_adapter(pai,'vision','accepted');asset=media.ingest(**content)
    with monkeypatch.context() as bounds:
        bounds.setattr(vision,'MAX_VISION_BODY_BYTES',100)
        with pytest.raises(StorageError,match='vision request exceeds bounded scope'):
            invoke(asset,media.path/asset.media_ref,'vision_body_bound')
    assert not pai.requests
    with pai.root.queue.store.transaction() as tx:
        count=tx.conn.execute("SELECT count(*) AS n FROM pa_runtime.object_heads WHERE owner=%s AND object_id LIKE 'model_attempt_%%'",(pai.root.owner_ref,)).fetchone()['n']
    assert count==0
    assert all(window['reserved']==0 for window in pai.root.registry.snapshot(pai.root.owner_ref)['windows'])
    valid=media.ingest(**content)
    assert invoke(valid,media.path/valid.media_ref,'vision_body_bound')['status']=='ok'
    assert len(pai.requests)==1


@pytest.mark.parametrize('suffix,error_name',[('rejected','ModelProviderRejected'),('malformed','ModelResponseInvalid')])
def test_media_bookkeeping_failure_preserves_non_retryable_provider_reason(pai,monkeypatch,suffix,error_name):
    from prm.runtime import model_errors
    from prm.runtime.cost_cache import CostCacheRuntime
    invoke,content=media_adapter(pai,'speech',suffix)
    media=MediaRuntime(pai.root,temporary_root=pai.path/'reason_preserved');asset=media.ingest(**content)
    def failed_record(*args,**kwargs):raise StorageError('synthetic usage acknowledgment lost')
    monkeypatch.setattr(CostCacheRuntime,'record',failed_record)
    with pytest.raises(getattr(model_errors,error_name)) as failure:invoke(asset,media.path/asset.media_ref,'preserved_'+suffix)
    assert not failure.value.retry_allowed and failure.value.attempt_ref.startswith('model_attempt_')
    assert len(failure.value.operation_refs)==1 and len(pai.requests)==1


@pytest.mark.parametrize('modality',['speech','vision'])
def test_media_runtime_preserves_accepted_result_when_accounting_is_unconfirmed(pai,monkeypatch,modality):
    import struct
    import zlib
    from dataclasses import replace
    from tests.pai_runtime_fixtures import allow
    from prm.runtime.cost_cache import CostCacheRuntime
    from prm.runtime.speech import SpeechTranscriber
    from prm.runtime.vision import VisionAdapter
    media=MediaRuntime(pai.root,temporary_root=pai.path/'accepted_media_result')
    def failed_record(*args,**kwargs):raise StorageError('synthetic accounting acknowledgment lost')
    monkeypatch.setattr(CostCacheRuntime,'record',failed_record)
    if modality=='speech':
        allow(pai,'media.transcribe','resource_voice','user_provided','voice.transcription')
        media.transcriber=SpeechTranscriber(pai.root,endpoint=replace(pai.root.model_endpoint,endpoint=pai.origin+'/speech/accepted'),upper_bound=1,resource_ref='resource_voice')
        asset=media.ingest(content=b'OggS synthetic accepted voice',kind='voice',mime_type='audio/ogg')
        result=media.extract(asset,task_ref='accepted_voice_runtime')
        assert result['status']=='transcribed' and result['pages']==[[1,'Synthetic transcription.']]
        stored=pai.root.queue.store.get(pai.root.owner_ref,'result',result['transcript_ref'])
        assert stored.payload['text']=='Synthetic transcription.'
        media.cleanup(asset)
    else:
        allow(pai,'media.vision','resource_image','user_provided','media.vision')
        media.vision=VisionAdapter(pai.root,endpoint=replace(pai.root.model_endpoint,endpoint=pai.origin+'/vision/accepted'),upper_bound=1,resource_ref='resource_image')
        def chunk(kind,data):return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data))
        image=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!IIBBBBB',1,1,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(b'\x00\xff\xff\xff\xff'))+chunk(b'IEND',b'')
        asset=media.ingest(content=image,kind='image',mime_type='image/png')
        result=media.question(asset,'Synthetic image question',request_ref='accepted_image_runtime')
        assert result['status']=='ok' and result['text']=='Synthetic image answer.'
        assert not (media.path/asset.media_ref).exists()
    assert result['accounting_status']=='unconfirmed'
    assert len(pai.requests)==1
    assert all(window['consumed']==1 for window in pai.root.registry.snapshot(pai.root.owner_ref)['windows'])


@pytest.mark.parametrize('pages',[
    [[0,'bad']], [[-1,'bad']], [[33,'bad']], [[True,'bad']], [[1,{}]],
    [[1,'first'],[1,'duplicate']], [[2,'second'],[1,'first']], 'not-pages', []])
def test_extraction_page_shape_and_numbering_are_rejected(pages):
    with pytest.raises(StorageError,match='extraction output malformed'):
        MediaRuntime._validated_pages({'status':'extracted','pages':pages},maximum=32)


def test_ocr_plain_callable_cannot_receive_media_without_its_dedicated_scope(pai,monkeypatch):
    import struct,zlib
    def chunk(kind,data):return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data))
    image=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!IIBBBBB',1,1,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(b'\x00\xff\xff\xff\xff'))+chunk(b'IEND',b'')
    calls=[];runtime=MediaRuntime(pai.root,temporary_root=pai.path/'ocr_scope',ocr=lambda *args:calls.append(args))
    asset=runtime.ingest(content=image,kind='image',mime_type='image/png')
    assert runtime.extract(asset)['status']=='ocr_unavailable' and calls==[]
    class Ocr:
        provider_ref='provider_openai';connection_ref='connection_fixture';upper_bound=1
        def __call__(self,*args):calls.append(args);return {'status':'ocr','pages':[[1,'Synthetic OCR text.']]}
    runtime.ocr=Ocr()
    assert runtime.extract(asset)['status']=='ocr_unavailable' and calls==[]
    from tests.pai_runtime_fixtures import allow
    allow(pai,'media.ocr',asset.media_ref,'user_provided','media.ocr')
    assert runtime.extract(asset,task_ref='ocr_owned_task')['pages']==[[1,'Synthetic OCR text.']]
    assert len(calls)==1
    from prm.runtime.model_attempts import ModelAttemptAlreadyRecorded
    with pytest.raises(ModelAttemptAlreadyRecorded):runtime.extract(asset,task_ref='ocr_owned_task')
    assert len(calls)==1


def test_download_rejects_foreign_or_unbound_input_before_any_transport(pai):
    from prm.runtime.media_download import TelegramMediaDownloader
    from prm.capabilities import CapabilityDenied
    adapter=TelegramMediaDownloader(pai.root,token='synthetic_download',resource_ref='resource_input',upper_bound=0)
    with pytest.raises(CapabilityDenied,match='authenticated owner input'):adapter.download('synthetic_file',kind='image')
    pai.root.queue.store.put(pai.root.owner_ref,'conversation','download_foreign',{'chat_id':'42','actor_id':'99','owner_chat_id':'42',
        'media_input':{'file_ref':'synthetic_file','kind':'image'}},expected_version=0)
    with pytest.raises(CapabilityDenied,match='owner differs'):adapter.download('synthetic_file',kind='image',request_ref='download_foreign')
    pai.root.queue.store.put(pai.root.owner_ref,'conversation','download_owned',{'chat_id':'42','actor_id':'42','owner_chat_id':'42',
        'media_input':{'file_ref':'synthetic_file','kind':'image'}},expected_version=0)
    with pytest.raises(CapabilityDenied,match='differs from authenticated'):adapter.download('other_file',kind='image',request_ref='download_owned')
    assert pai.requests==[] and pai.root.registry.snapshot(pai.root.owner_ref)['operations']==[]
