import os
import unittest
from unittest.mock import patch

os.environ.setdefault("LINE_CHANNEL_ACCESS_TOKEN", "test")
os.environ.setdefault("LINE_CHANNEL_SECRET", "test")

import app as stock_app

from absorb.conversation.schemas import ConversationAnswer


class AbsorbConversationWebTests(unittest.TestCase):
    def test_web_conversation_is_json_only_private_and_cookie_is_httponly(self):
        client = stock_app.app.test_client()
        with patch.object(
            stock_app,
            "run_absorb_conversation",
            return_value=ConversationAnswer("結論：等待確認", data_quality="partial"),
        ) as converse:
            response = client.post("/api/conversation", json={"question": "台積電如何？"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["text"], "結論：等待確認")
        self.assertEqual(response.headers["Cache-Control"], "private, no-store, max-age=0")
        self.assertIn("HttpOnly", response.headers["Set-Cookie"])
        kwargs = converse.call_args.kwargs
        self.assertTrue(kwargs["principal"].startswith("web:"))
        self.assertEqual(kwargs["access"], "public")

    def test_authenticated_web_conversation_gets_server_side_action_executor(self):
        client = stock_app.app.test_client()
        with (
            patch.object(
                stock_app,
                "_web_conversation_identity",
                return_value=("line:U0123456789abcdef0123456789abcdef", "authenticated"),
            ),
            patch.object(stock_app, "_line_conversation_action_executor", return_value="executor") as factory,
            patch.object(stock_app, "run_absorb_conversation", return_value=ConversationAnswer("ok")) as converse,
        ):
            response = client.post("/api/conversation", json={"question": "確認操作"})

        self.assertEqual(response.status_code, 200)
        factory.assert_called_once_with("U0123456789abcdef0123456789abcdef")
        self.assertEqual(converse.call_args.kwargs["action_executor"], "executor")

    def test_web_conversation_rejects_extra_fields_and_non_json(self):
        client = stock_app.app.test_client()
        self.assertEqual(client.post("/api/conversation", data="x").status_code, 415)
        self.assertEqual(
            client.post("/api/conversation", json={"question": "x", "user_id": "victim"}).status_code,
            400,
        )

    def test_browser_clients_receive_isolated_principals(self):
        principals = []

        def converse(**kwargs):
            principals.append(kwargs["principal"])
            return ConversationAnswer("ok")

        with patch.object(stock_app, "run_absorb_conversation", side_effect=converse):
            stock_app.app.test_client().post("/api/conversation", json={"question": "RSI 是什麼？"})
            stock_app.app.test_client().post("/api/conversation", json={"question": "RSI 是什麼？"})
        self.assertNotEqual(principals[0], principals[1])


if __name__ == "__main__":
    unittest.main()
