import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import bot.voice as voice
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


def _authorization(*, capability: str, operation: str, provider_ref: str, resource_ref: str = "resource_voice"):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    grant = CapabilityGrant(
        grant_id=f"grant_synthetic_{capability.replace('.', '_')}",
        owner_ref="owner_synthetic_primary",
        connection_ref=None,
        capability=capability,
        resource_refs=(resource_ref,),
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
        resource_ref=resource_ref,
        operation=operation,
        data_class="user_provided",
        provider_ref=provider_ref,
        purpose="voice.transcription",
        expected_grant_revision=1,
    )
    return CapabilityRegistry((grant,)).authorize_and_reserve(request, now=now)


class TestVoiceTranscription(unittest.TestCase):
    def test_transcribe_audio_file_rejects_an_unverified_local_path(self):
        with tempfile.NamedTemporaryFile(suffix=".ogg") as tmp:
            with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
                with self.assertRaises(VoiceTranscriptionUnavailable):
                    transcribe_audio_file(tmp.name)

    def test_transcribe_audio_file_rejects_resource_substitution_before_upload_construction(self):
        with tempfile.NamedTemporaryFile(suffix=".ogg") as tmp:
            tmp.write(b"fake audio")
            tmp.flush()

            with patch.dict(os.environ, {"OPENAI_API_KEY": "openai-key"}, clear=False):
                with patch("bot.voice._build_multipart_body") as multipart_body:
                    with patch("bot.voice.request.urlopen") as urlopen:
                        with self.assertRaises(VoiceTranscriptionUnavailable):
                            transcribe_audio_file(
                                tmp.name,
                                transcription_authorization=_authorization(
                                    capability="media.transcribe",
                                    operation="model_egress",
                                    provider_ref="provider_openai",
                                ),
                                owner_ref="owner_synthetic_primary",
                                connection_ref=None,
                                resource_ref="resource_voice",
                            )

        multipart_body.assert_not_called()
        urlopen.assert_not_called()

    def test_transcribe_telegram_voice_deletes_local_audio_after_transcription(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            voice_path = Path(tmpdir) / "voice.ogg"
            voice_path.write_bytes(b"fake audio")

            with patch.dict(os.environ, {"OPENAI_API_KEY": "openai-key"}, clear=False):
                with patch("bot.voice._download_telegram_voice", return_value=str(voice_path)):
                    with patch("bot.voice._transcribe_verified_telegram_audio", return_value="voice transcript"):
                        transcript = transcribe_telegram_voice(
                            token="bot-token",
                            file_id="voice-1",
                            download_authorization=_authorization(
                                capability="media.voice_download",
                                operation="read",
                                provider_ref="provider_telegram",
                                resource_ref="voice-1",
                            ),
                            download_file_authorization=_authorization(
                                capability="media.voice_download",
                                operation="read",
                                provider_ref="provider_telegram",
                                resource_ref="voice-1",
                            ),
                            transcription_authorization=_authorization(
                                capability="media.transcribe",
                                operation="model_egress",
                                provider_ref="provider_openai",
                                resource_ref="voice-1",
                            ),
                            owner_ref="owner_synthetic_primary",
                            connection_ref=None,
                        )

            self.assertEqual(transcript, "voice transcript")
            self.assertFalse(voice_path.exists())

    def test_verified_telegram_attachment_keeps_the_downloaded_bytes_bound_to_its_file_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            voice_path = Path(tmpdir) / "voice.ogg"
            voice_path.write_bytes(b"verified Telegram bytes")
            attachment = voice._verified_telegram_voice_attachment(
                local_path=str(voice_path),
                file_id="voice-1",
            )
            voice_path.write_bytes(b"substituted local bytes")
            captured = {}

            def fake_urlopen(request_obj, timeout):
                captured["body"] = request_obj.data
                return _FakeResponse({"text": "verified transcript"})

            with patch.dict(os.environ, {"OPENAI_API_KEY": "openai-key"}, clear=False):
                with patch("bot.voice.request.urlopen", side_effect=fake_urlopen):
                    transcript = voice._transcribe_verified_telegram_audio(
                        attachment,
                        transcription_authorization=_authorization(
                            capability="media.transcribe",
                            operation="model_egress",
                            provider_ref="provider_openai",
                            resource_ref="voice-1",
                        ),
                        owner_ref="owner_synthetic_primary",
                    )

            self.assertEqual(transcript, "verified transcript")
            self.assertIn(b"verified Telegram bytes", captured["body"])
            self.assertNotIn(b"substituted local bytes", captured["body"])

    def test_voice_failures_and_download_logs_redact_attachment_identifiers_and_provider_payloads(self):
        with tempfile.TemporaryDirectory(prefix="private-local-path-sentinel-") as tmpdir:
            voice_path = Path(tmpdir) / "private-file-id-sentinel.ogg"
            voice_path.write_bytes(b"voice bytes")
            attachment = voice._verified_telegram_voice_attachment(
                local_path=str(voice_path),
                file_id="private-file-id-sentinel",
            )

            with patch.dict(os.environ, {"OPENAI_API_KEY": "openai-key"}, clear=False):
                with patch("bot.voice.request.urlopen", side_effect=RuntimeError("provider-payload-sentinel")):
                    with self.assertLogs(voice.LOGGER, level="WARNING") as transcribe_logs:
                        with self.assertRaises(voice.VoiceTranscriptionError) as error:
                            voice._transcribe_verified_telegram_audio(
                                attachment,
                                transcription_authorization=_authorization(
                                    capability="media.transcribe",
                                    operation="model_egress",
                                    provider_ref="provider_openai",
                                    resource_ref="private-file-id-sentinel",
                                ),
                                owner_ref="owner_synthetic_primary",
                            )

            rendered = "\n".join(transcribe_logs.output)
            assert "provider-payload-sentinel" not in str(error.exception)
            assert "private-file-id-sentinel" not in str(error.exception)
            assert "provider-payload-sentinel" not in rendered
            assert "private-file-id-sentinel" not in rendered
            assert "private-local-path-sentinel" not in rendered

    def test_telegram_error_response_and_download_log_redact_private_values(self):
        response_payload = {"ok": False, "private_provider_payload": "provider-payload-sentinel"}
        with patch("bot.voice.request.urlopen", return_value=_FakeResponse(response_payload)):
            with self.assertRaises(voice.VoiceTranscriptionError) as error:
                voice._get_telegram_file_path(
                    token="bot-token",
                    file_id="private-file-id-sentinel",
                    authorization=_authorization(
                        capability="media.voice_download",
                        operation="read",
                        provider_ref="provider_telegram",
                        resource_ref="private-file-id-sentinel",
                    ),
                    owner_ref="owner_synthetic_primary",
                    connection_ref=None,
                    resource_ref="private-file-id-sentinel",
                )

        assert "provider-payload-sentinel" not in str(error.exception)

        with tempfile.TemporaryDirectory(prefix="private-local-path-sentinel-") as tmpdir:
            def fake_urlopen(request_obj, timeout):
                url = getattr(request_obj, "full_url", str(request_obj))
                if "getFile?" in url:
                    return _FakeResponse({"ok": True, "result": {"file_path": "private/provider/path.ogg"}})
                return _FakeResponse(b"synthetic voice bytes")

            with patch("bot.voice.request.urlopen", side_effect=fake_urlopen):
                with self.assertLogs(voice.LOGGER, level="INFO") as download_logs:
                    downloaded = voice._download_telegram_voice(
                        token="bot-token",
                        file_id="private-file-id-sentinel",
                        media_dir=tmpdir,
                        get_file_authorization=_authorization(
                            capability="media.voice_download",
                            operation="read",
                            provider_ref="provider_telegram",
                            resource_ref="private-file-id-sentinel",
                        ),
                        download_file_authorization=_authorization(
                            capability="media.voice_download",
                            operation="read",
                            provider_ref="provider_telegram",
                            resource_ref="private-file-id-sentinel",
                        ),
                        owner_ref="owner_synthetic_primary",
                        connection_ref=None,
                        resource_ref="private-file-id-sentinel",
                    )
            voice._delete_local_file(downloaded)

        rendered = "\n".join(download_logs.output)
        assert "private-file-id-sentinel" not in rendered
        assert "private-local-path-sentinel" not in rendered
        assert "private/provider/path.ogg" not in rendered

    def test_transcribe_telegram_voice_requires_a_reservation_for_each_telegram_call(self):
        download_authorization = _authorization(
            capability="media.voice_download",
            operation="read",
            provider_ref="provider_telegram",
            resource_ref="voice-1",
        )
        transcription_authorization = _authorization(
            capability="media.transcribe",
            operation="model_egress",
            provider_ref="provider_openai",
            resource_ref="voice-1",
        )

        with patch("bot.voice.request.urlopen") as urlopen:
            with self.assertRaises(VoiceTranscriptionUnavailable):
                transcribe_telegram_voice(
                    token="bot-token",
                    file_id="voice-1",
                    download_authorization=download_authorization,
                    transcription_authorization=transcription_authorization,
                    owner_ref="owner_synthetic_primary",
                )

        urlopen.assert_not_called()

    def test_transcribe_telegram_voice_uses_each_real_policy_layer_once(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            urls: list[str] = []
            transcription_bodies: list[bytes] = []

            def fake_urlopen(request_obj, timeout):
                url = getattr(request_obj, "full_url", str(request_obj))
                urls.append(url)
                if "getFile?" in url:
                    return _FakeResponse({"ok": True, "result": {"file_path": "voice/synthetic.ogg"}})
                if "/file/bot" in url:
                    return _FakeResponse(b"synthetic voice bytes")
                transcription_bodies.append(request_obj.data)
                return _FakeResponse({"text": "integrated synthetic transcript"})

            with patch.dict(os.environ, {"OPENAI_API_KEY": "openai-key"}, clear=False):
                with patch("bot.voice.request.urlopen", side_effect=fake_urlopen):
                    transcript = transcribe_telegram_voice(
                        token="bot-token",
                        file_id="voice-1",
                        media_dir=tmpdir,
                        download_authorization=_authorization(
                            capability="media.voice_download",
                            operation="read",
                            provider_ref="provider_telegram",
                            resource_ref="voice-1",
                        ),
                        download_file_authorization=_authorization(
                            capability="media.voice_download",
                            operation="read",
                            provider_ref="provider_telegram",
                            resource_ref="voice-1",
                        ),
                        transcription_authorization=_authorization(
                            capability="media.transcribe",
                            operation="model_egress",
                            provider_ref="provider_openai",
                            resource_ref="voice-1",
                        ),
                        owner_ref="owner_synthetic_primary",
                    )

            self.assertEqual(transcript, "integrated synthetic transcript")
            self.assertEqual(len(urls), 3)
            self.assertEqual(len(transcription_bodies), 1)
            self.assertIn(b"synthetic voice bytes", transcription_bodies[0])
            self.assertEqual(list(Path(tmpdir).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
