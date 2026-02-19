import asyncio
import hashlib
import hmac
from unittest import TestCase
from unittest.mock import MagicMock, patch

from hummingbot.connector.derivative.decibel_perpetual.decibel_perpetual_auth import DecibelPerpetualAuth
from hummingbot.connector.time_synchronizer import TimeSynchronizer
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, RESTRequest, WSRequest


class TestDecibelPerpetualAuth(TestCase):
    def setUp(self):
        self.api_key = "test_key"
        self.api_secret = "test_secret"
        self.time_synchronizer = MagicMock(spec=TimeSynchronizer)
        self.time_synchronizer.time.return_value = 1700000000.0
        self.auth = DecibelPerpetualAuth(
            api_key=self.api_key,
            api_secret=self.api_secret,
            time_provider=self.time_synchronizer,
        )

    def test_rest_authenticate_adds_headers(self):
        request = RESTRequest(
            method=RESTMethod.GET,
            url="https://api.decibel.trade/v1/account/overview",
        )
        result = asyncio.get_event_loop().run_until_complete(self.auth.rest_authenticate(request))
        self.assertIn("DB-ACCESS-KEY", result.headers)
        self.assertIn("DB-ACCESS-TIMESTAMP", result.headers)
        self.assertIn("DB-ACCESS-SIGN", result.headers)
        self.assertEqual(result.headers["DB-ACCESS-KEY"], self.api_key)

    def test_signature_is_valid_hmac_sha256(self):
        timestamp = "1700000000000"
        method = "GET"
        path = "/v1/account/overview"
        body = ""
        message = timestamp + method + path + body
        expected = hmac.new(
            self.api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        result = self.auth._generate_signature(timestamp, method, path, body)
        self.assertEqual(result, expected)

    def test_ws_authenticate_sets_auth_payload(self):
        request = WSRequest(payload={})
        result = asyncio.get_event_loop().run_until_complete(self.auth.ws_authenticate(request))
        self.assertIn("op", result.payload)
        self.assertEqual(result.payload["op"], "auth")
        args = result.payload["args"]
        self.assertEqual(args[0], self.api_key)

    def test_add_auth_to_params_adds_timestamp(self):
        params = {"market": "BTC-USD"}
        result = self.auth.add_auth_to_params(params)
        self.assertIn("timestamp", result)

    def test_different_methods_produce_different_signatures(self):
        sig_get = self.auth._generate_signature("1700000000000", "GET", "/v1/orders", "")
        sig_post = self.auth._generate_signature("1700000000000", "POST", "/v1/orders", "")
        self.assertNotEqual(sig_get, sig_post)
