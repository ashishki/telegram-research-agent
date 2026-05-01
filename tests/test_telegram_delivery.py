import unittest
from unittest.mock import patch

from bot.telegram_delivery import send_text


class TestSendText(unittest.TestCase):
    def test_send_text_allows_parse_mode_override(self):
        with patch("bot.telegram_delivery._send_text_internal") as mock_send:
            send_text(chat_id="123", text="hello", token="token", parse_mode="Markdown")

        mock_send.assert_called_once_with(
            chat_id="123",
            text="hello",
            token="token",
            parse_mode="Markdown",
            reply_markup=None,
        )

    def test_send_text_forwards_reply_markup(self):
        markup = {"inline_keyboard": [[{"text": "ok", "callback_data": "idea:1:done"}]]}

        with patch("bot.telegram_delivery._send_text_internal") as mock_send:
            send_text(chat_id="123", text="hello", token="token", parse_mode=None, reply_markup=markup)

        mock_send.assert_called_once_with(
            chat_id="123",
            text="hello",
            token="token",
            parse_mode=None,
            reply_markup=markup,
        )


if __name__ == "__main__":
    unittest.main()
