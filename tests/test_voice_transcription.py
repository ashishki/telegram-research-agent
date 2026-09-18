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


def _authorization(
    *,
    capability: str,
    operation: str,
    provider_ref: str,
    resource_ref: str = "resource_voice",
    purpose: str = "voice.transcription",
    connection_ref: str | None = None,
):
    if connection_ref is None:
        connection_ref = (
            voice._telegram_connection_ref("bot-token")
            if provider_ref == "provider_telegram"
            else voice._openai_connection_ref("openai-key")
        )
    assert connection_ref is not None
    now = datetime.now(timezone.utc).replace(microsecond=0)
    grant = CapabilityGrant(
        grant_id=f"grant_synthetic_{capability.replace('.', '_')}",
        owner_ref="owner_synthetic_primary",
        connection_ref=connection_ref,
        capability=capability,
        resource_refs=(resource_ref,),
        operations=(operation,),
        data_classes=("user_provided",),
        purpose=purpose,
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
        purpose=purpose,
        connection_ref=connection_ref,
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

    def test_transcribe_telegram_voice_uses_only_the_in_memory_bound_attachment(self):
        attachment = voice._VerifiedTelegramVoiceAttachment(file_id="voice-1", audio_bytes=b"fake audio")
        with patch.dict(os.environ, {"OPENAI_API_KEY": "openai-key"}, clear=False):
            with patch("bot.voice._download_telegram_voice", return_value=attachment):
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

    def test_verified_telegram_attachment_keeps_the_downloaded_bytes_bound_to_its_file_id(self):
        attachment = voice._VerifiedTelegramVoiceAttachment(
            file_id="voice-1",
            audio_bytes=b"verified Telegram bytes",
        )
        captured = {}

        def fake_open(request_obj, timeout):
            captured["body"] = request_obj.data
            captured["url"] = request_obj.full_url
            return _FakeResponse({"text": "verified transcript"})

        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "openai-key",
                "OPENAI_AUDIO_TRANSCRIPTIONS_URL": "https://attacker.invalid/collect",
            },
            clear=False,
        ):
            with patch("bot.voice._open_openai_transcription_request", side_effect=fake_open):
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
        self.assertEqual(captured["url"], voice.OPENAI_TRANSCRIPTIONS_ENDPOINT)
        self.assertIn(b"verified Telegram bytes", captured["body"])
        self.assertNotIn(b"substituted local bytes", captured["body"])

    def test_voice_failures_and_download_logs_redact_attachment_identifiers_and_provider_payloads(self):
        attachment = voice._VerifiedTelegramVoiceAttachment(
            file_id="private-file-id-sentinel",
            audio_bytes=b"voice bytes",
        )

        with patch.dict(os.environ, {"OPENAI_API_KEY": "openai-key"}, clear=False):
            with patch(
                "bot.voice._open_openai_transcription_request",
                side_effect=RuntimeError("provider-payload-sentinel"),
            ):
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

        rendered = "\n".join(download_logs.output)
        assert "private-file-id-sentinel" not in rendered
        assert "private/provider/path.ogg" not in rendered
        assert downloaded.file_id == "private-file-id-sentinel"
        assert downloaded.audio_bytes == b"synthetic voice bytes"

    def test_transcription_rejects_an_unapproved_endpoint_before_opening_any_network_transport(self):
        malicious = voice.request.Request(
            "https://attacker.invalid/v1/audio/transcriptions",
            data=b"synthetic",
            method="POST",
        )
        with patch("bot.voice.request.build_opener") as build_opener:
            with self.assertRaisesRegex(voice.VoiceTranscriptionError, "not approved"):
                voice._open_openai_transcription_request(malicious, timeout=120)

        build_opener.assert_not_called()

    def test_transcription_redirect_handler_never_constructs_a_redirect_request(self):
        handler = voice._RejectRedirects()
        assert handler.redirect_request(
            voice.request.Request(voice.OPENAI_TRANSCRIPTIONS_ENDPOINT),
            None,
            302,
            "Found",
            {},
            "https://attacker.invalid/collect",
        ) is None

    def test_voice_download_keeps_raw_bytes_in_memory_without_local_staging(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            def fake_urlopen(request_obj, timeout):
                url = getattr(request_obj, "full_url", str(request_obj))
                if "getFile?" in url:
                    return _FakeResponse({"ok": True, "result": {"file_path": "voice/synthetic.ogg"}})
                return _FakeResponse(b"synthetic voice bytes")

            with patch("bot.voice.request.urlopen", side_effect=fake_urlopen):
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

            self.assertEqual(downloaded.file_id, "private-file-id-sentinel")
            self.assertEqual(downloaded.audio_bytes, b"synthetic voice bytes")
            self.assertEqual(list(Path(tmpdir).iterdir()), [])

    def test_voice_download_rejects_an_unsafe_attachment_id_before_network_or_storage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("bot.voice.request.urlopen") as urlopen:
                with self.assertRaisesRegex(voice.VoiceTranscriptionError, "identifier is invalid"):
                    voice._download_telegram_voice(
                        token="bot-token",
                        file_id="../private-file-id-sentinel",
                        media_dir=tmpdir,
                        get_file_authorization=None,
                        download_file_authorization=None,
                        owner_ref="owner_synthetic_primary",
                        connection_ref=None,
                        resource_ref="../private-file-id-sentinel",
                    )
            urlopen.assert_not_called()
            self.assertEqual(list(Path(tmpdir).iterdir()), [])

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

    def test_voice_transports_reject_reservations_for_another_purpose_before_network(self):
        valid_download = lambda: _authorization(
            capability="media.voice_download",
            operation="read",
            provider_ref="provider_telegram",
            resource_ref="voice-1",
        )
        for wrong_layer in ("telegram_read", "openai_transcription"):
            download_purpose = "answer.request" if wrong_layer == "telegram_read" else "voice.transcription"
            transcription_purpose = "answer.request" if wrong_layer == "openai_transcription" else "voice.transcription"
            with patch.dict(os.environ, {"OPENAI_API_KEY": "openai-key"}, clear=False), patch(
                "bot.voice.request.urlopen"
            ) as urlopen:
                with self.assertRaises(VoiceTranscriptionUnavailable):
                    transcribe_telegram_voice(
                        token="bot-token",
                        file_id="voice-1",
                        download_authorization=_authorization(
                            capability="media.voice_download",
                            operation="read",
                            provider_ref="provider_telegram",
                            resource_ref="voice-1",
                            purpose=download_purpose,
                        ),
                        download_file_authorization=valid_download(),
                        transcription_authorization=_authorization(
                            capability="media.transcribe",
                            operation="model_egress",
                            provider_ref="provider_openai",
                            resource_ref="voice-1",
                            purpose=transcription_purpose,
                        ),
                        owner_ref="owner_synthetic_primary",
                    )
            urlopen.assert_not_called()

    def test_voice_transports_reject_grants_bound_to_another_configured_connection_before_network(self):
        valid_download = lambda: _authorization(
            capability="media.voice_download",
            operation="read",
            provider_ref="provider_telegram",
            resource_ref="voice-1",
        )
        with patch.dict(os.environ, {"OPENAI_API_KEY": "openai-key"}, clear=False):
            for wrong_layer in ("telegram_read", "openai_transcription"):
                download_connection = (
                    "connection_telegram_other"
                    if wrong_layer == "telegram_read"
                    else voice._telegram_connection_ref("bot-token")
                )
                transcription_connection = (
                    "connection_openai_other"
                    if wrong_layer == "openai_transcription"
                    else voice._openai_connection_ref("openai-key")
                )
                with patch("bot.voice.request.urlopen") as urlopen:
                    with self.assertRaises(VoiceTranscriptionUnavailable):
                        transcribe_telegram_voice(
                            token="bot-token",
                            file_id="voice-1",
                            download_authorization=_authorization(
                                capability="media.voice_download",
                                operation="read",
                                provider_ref="provider_telegram",
                                resource_ref="voice-1",
                                connection_ref=download_connection,
                            ),
                            download_file_authorization=valid_download(),
                            transcription_authorization=_authorization(
                                capability="media.transcribe",
                                operation="model_egress",
                                provider_ref="provider_openai",
                                resource_ref="voice-1",
                                connection_ref=transcription_connection,
                            ),
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

            def fake_transcription_open(request_obj, timeout):
                transcription_bodies.append(request_obj.data)
                return _FakeResponse({"text": "integrated synthetic transcript"})

            with patch.dict(os.environ, {"OPENAI_API_KEY": "openai-key"}, clear=False):
                with patch("bot.voice.request.urlopen", side_effect=fake_urlopen), patch(
                    "bot.voice._open_openai_transcription_request",
                    side_effect=fake_transcription_open,
                ):
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
            self.assertEqual(len(urls), 2)
            self.assertEqual(len(transcription_bodies), 1)
            self.assertIn(b"synthetic voice bytes", transcription_bodies[0])
            self.assertEqual(list(Path(tmpdir).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
