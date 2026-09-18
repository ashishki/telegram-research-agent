import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from bot.voice import (
    VoiceTranscriptionUnavailable,
    transcribe_audio_file,
    transcribe_telegram_voice,
)
from prm.capabilities import AuthorizationRequest, CapabilityGrant, CapabilityRegistry, ProviderPolicy


class _FakeResponse:
    def __init__(self, payload: dict | bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        if isinstance(self.payload, bytes):
            return self.payload
        return json.dumps(self.payload).encode("utf-8")


def _authorization(*, capability: str, operation: str, provider_ref: str):
    now = datetime(2026, 9, 18, tzinfo=timezone.utc)
    grant = CapabilityGrant(
        grant_id=f"grant_synthetic_{capability.replace('.', '_')}",
        owner_ref="owner_synthetic_primary",
        connection_ref=None,
        capability=capability,
        resource_refs=("resource_voice",),
        operations=(operation,),
        data_classes=("user_provided",),
        purpose="voice.transcription",
        provider_policy=ProviderPolicy((provider_ref,)),
        issued_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(hours=1),
        revision=1,
    )
    request = AuthorizationRequest(
        owner_ref="owner_synthetic_primary",
        capability=capability,
        resource_ref="resource_voice",
        operation=operation,
        data_class="user_provided",
        provider_ref=provider_ref,
        purpose="voice.transcription",
        expected_grant_revision=1,
    )
    return CapabilityRegistry((grant,)).authorize_and_reserve(request, now=now)


class TestVoiceTranscription(unittest.TestCase):
    def test_transcribe_audio_file_requires_openai_key(self):
        with tempfile.NamedTemporaryFile(suffix=".ogg") as tmp:
            with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
                with self.assertRaises(VoiceTranscriptionUnavailable):
                    transcribe_audio_file(tmp.name)

    def test_transcribe_audio_file_posts_multipart_and_returns_text(self):
        with tempfile.NamedTemporaryFile(suffix=".ogg") as tmp:
            tmp.write(b"fake audio")
            tmp.flush()

            captured = {}

            def fake_urlopen(request_obj, timeout):
                captured["timeout"] = timeout
                captured["url"] = request_obj.full_url
                captured["headers"] = dict(request_obj.header_items())
                captured["body"] = request_obj.data
                return _FakeResponse({"text": "Полезный отчет, target=actions."})

            with patch.dict(os.environ, {"OPENAI_API_KEY": "openai-key"}, clear=False):
                with patch("bot.voice.request.urlopen", side_effect=fake_urlopen):
                    transcript = transcribe_audio_file(
                        tmp.name,
                        transcription_authorization=_authorization(
                            capability="media.transcribe",
                            operation="model_egress",
                            provider_ref="provider_openai",
                        ),
                    )

        self.assertEqual(transcript, "Полезный отчет, target=actions.")
        self.assertEqual(captured["timeout"], 120)
        self.assertEqual(captured["url"], "https://api.openai.com/v1/audio/transcriptions")
        self.assertIn("Bearer openai-key", captured["headers"]["Authorization"])
        self.assertIn(b'name="model"', captured["body"])
        self.assertIn(b"whisper-1", captured["body"])
        self.assertIn(b'name="file"', captured["body"])
        self.assertIn(b"fake audio", captured["body"])

    def test_transcribe_telegram_voice_deletes_local_audio_after_transcription(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            voice_path = Path(tmpdir) / "voice.ogg"
            voice_path.write_bytes(b"fake audio")

            with patch.dict(os.environ, {"OPENAI_API_KEY": "openai-key"}, clear=False):
                with patch("bot.voice._download_telegram_voice", return_value=str(voice_path)):
                    with patch("bot.voice.transcribe_audio_file", return_value="voice transcript"):
                        transcript = transcribe_telegram_voice(
                            token="bot-token",
                            file_id="voice-1",
                            download_authorization=_authorization(
                                capability="media.voice_download",
                                operation="read",
                                provider_ref="provider_telegram",
                            ),
                            transcription_authorization=_authorization(
                                capability="media.transcribe",
                                operation="model_egress",
                                provider_ref="provider_openai",
                            ),
                        )

            self.assertEqual(transcript, "voice transcript")
            self.assertFalse(voice_path.exists())


if __name__ == "__main__":
    unittest.main()
