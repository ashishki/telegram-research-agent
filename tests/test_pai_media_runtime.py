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
