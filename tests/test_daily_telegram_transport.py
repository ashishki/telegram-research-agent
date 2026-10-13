"""Real loopback Bot API wires; no live bot/account or external provider."""
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace
from urllib.parse import parse_qs
import json
import pytest

from prm.runtime.transports import BotAPITransport, BoundedTelegramSender
from prm.runtime.delivery import KnownDeliveryRejection
from prm.telegram_contracts import TelegramDestination
from prm.storage.postgres import StorageError


@pytest.fixture
def telegram_http():
    state = SimpleNamespace(requests=[], responses=[], origin=None)
    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            state.requests.append((self.path, parse_qs(self.rfile.read(int(self.headers['Content-Length'])).decode())))
            status, value = state.responses.pop(0) if state.responses else (200, {'ok': True, 'result': {'chat': {'id': 42}, 'message_id': len(state.requests)}})
            if status == 0: self.close_connection = True; return
            self.send_response(status)
            if status == 302: self.send_header('Location', state.origin + '/must-not-follow')
            self.send_header('Content-Type', 'application/json'); self.end_headers()
            self.wfile.write(value if isinstance(value, bytes) else json.dumps(value).encode())
    server = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    state.origin = f'http://127.0.0.1:{server.server_port}'
    thread = Thread(target=server.serve_forever); thread.start()
    try: yield state
    finally: server.shutdown(); thread.join(timeout=5); server.server_close()


@pytest.mark.parametrize('status,body,expected', [
    (200, {'ok': True, 'result': True}, 'accepted'),
    (400, {'ok': False, 'error_code': 400, 'description': 'sensitive_marker'}, 'known_rejected'),
    (429, {'ok': False, 'error_code': 429, 'parameters': {'retry_after': 12}}, 'known_rejected'),
    (500, {'ok': False, 'error_code': 500}, 'unknown'),
    (200, b'broken_sensitive_marker', 'unknown'),
    (0, {}, 'unknown'), (302, {}, 'unknown'),
])
def test_typed_outcomes_and_redaction(telegram_http, status, body, expected):
    telegram_http.responses.append((status, body))
    api = BotAPITransport(token='synthetic_secret', origin=telegram_http.origin, synthetic=True)
    value = api.request('answerCallbackQuery', {'callback_query_id': 'synthetic_callback'})
    assert value.kind == expected
    assert 'sensitive_marker' not in repr(value) and 'synthetic_secret' not in repr(value)
    assert len(telegram_http.requests) == 1
    if status == 429: assert value.retry_after == 12


def test_response_bound_and_unsupported_method(telegram_http):
    api = BotAPITransport(token='synthetic_secret', origin=telegram_http.origin, synthetic=True)
    telegram_http.responses.append((200, b' ' * 64001))
    assert api.request('answerCallbackQuery', {'callback_query_id': 'synthetic_callback'}).kind == 'unknown'
    with pytest.raises(StorageError): api.request('sendRichMessage', {})
    assert len(telegram_http.requests) == 1


def test_exact_thread_and_reply_wire_receipt(telegram_http):
    telegram_http.responses.append((200, {'ok': True, 'result': {'chat': {'id': 42}, 'message_id': 99, 'message_thread_id': 7}}))
    sender = BoundedTelegramSender(token='synthetic_secret', owner_chat_id='42', destination_ref='destination_private',
        origin=telegram_http.origin, synthetic=True, message_thread_id=7)
    receipt = sender.send_with_options('destination_private', 'Synthetic reply', 'attempt_synthetic', reply_to_message_id=15)
    assert receipt.destination == TelegramDestination(chat_id='42', message_thread_id=7)
    assert receipt.message_id == 99 and receipt.method == 'sendMessage'
    body = telegram_http.requests[0][1]
    assert body['message_thread_id'] == ['7']
    assert json.loads(body['reply_parameters'][0]) == {'message_id': 15, 'allow_sending_without_reply': False}


@pytest.mark.parametrize('result', [
    {'chat': {'id': 43}, 'message_id': 1}, {'chat': {'id': 42}, 'message_id': True},
    {'chat': {'id': 42}, 'message_id': 0}, {'chat': {'id': 42}, 'message_id': 1, 'message_thread_id': 3},
])
def test_wrong_receipt_is_unknown_no_fallback(telegram_http, result):
    telegram_http.responses.append((200, {'ok': True, 'result': result}))
    sender = BoundedTelegramSender(token='synthetic_secret', owner_chat_id='42', destination_ref='destination_private', origin=telegram_http.origin, synthetic=True)
    with pytest.raises(StorageError, match='identity'): sender('destination_private', 'Synthetic', 'attempt_synthetic')
    assert len(telegram_http.requests) == 1


def test_retry_after_is_typed_rejection_without_automatic_retry(telegram_http):
    telegram_http.responses.append((429, {'ok': False, 'error_code': 429, 'parameters': {'retry_after': 21}}))
    sender = BoundedTelegramSender(token='synthetic_secret', owner_chat_id='42', destination_ref='destination_private', origin=telegram_http.origin, synthetic=True)
    with pytest.raises(KnownDeliveryRejection) as failure: sender('destination_private', 'Synthetic', 'attempt_synthetic')
    assert failure.value.retry_after == 21 and len(telegram_http.requests) == 1
