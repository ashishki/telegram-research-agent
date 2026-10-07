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
