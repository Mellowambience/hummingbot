"""
Unit tests for GrvtPerpetualAuth.
"""
import asyncio
import unittest
from unittest.mock import MagicMock

from hummingbot.connector.derivative.grvt_perpetual.grvt_perpetual_auth import GrvtPerpetualAuth
from hummingbot.core.web_assistant.connections.data_types import RESTRequest, WSRequest


class TestGrvtPerpetualAuth(unittest.TestCase):
    def setUp(self):
        self.time_provider = MagicMock()
        self.auth = GrvtPerpetualAuth(
            api_key="test_api_key",
            sub_account_id="12345",
            time_provider=self.time_provider,
            domain="testnet",
        )

    def test_auth_payload(self):
        payload = self.auth.get_auth_payload()
        self.assertIn("api_key", payload)
        self.assertEqual(payload["api_key"], "test_api_key")

    def test_unauthenticated_headers_empty(self):
        headers = self.auth.get_auth_headers()
        self.assertEqual(headers, {})

    def test_set_session_cookie_and_account_id(self):
        self.auth.session_cookie = "test_cookie_value"
        self.auth.account_id = "12345"
        self.assertTrue(self.auth.is_authenticated())

    def test_authenticated_headers(self):
        self.auth.session_cookie = "test_cookie_value"
        self.auth.account_id = "12345"
        headers = self.auth.get_auth_headers()
        self.assertIn("Cookie", headers)
        self.assertIn("gravity=test_cookie_value", headers["Cookie"])
        self.assertIn("X-Grvt-Account-Id", headers)
        self.assertEqual(headers["X-Grvt-Account-Id"], "12345")

    def test_rest_authenticate_injects_headers(self):
        self.auth.session_cookie = "abc"
        self.auth.account_id = "999"
        request = RESTRequest(method=None, url="https://edge.grvt.io/full/v1/positions", headers={})
        result = asyncio.get_event_loop().run_until_complete(self.auth.rest_authenticate(request))
        self.assertIn("Cookie", result.headers)
        self.assertIn("X-Grvt-Account-Id", result.headers)

    def test_rest_authenticate_skips_if_not_authenticated(self):
        request = RESTRequest(method=None, url="https://edge.grvt.io/full/v1/positions", headers={})
        result = asyncio.get_event_loop().run_until_complete(self.auth.rest_authenticate(request))
        self.assertNotIn("Cookie", result.headers)


if __name__ == "__main__":
    unittest.main()
