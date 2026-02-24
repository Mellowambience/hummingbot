"""
Tests for GRVT Perpetual connector.
Covers: auth, order book data source, user stream data source, and derivative.
"""
import asyncio
import json
import time
from decimal import Decimal
from typing import Any, Dict
from unittest import TestCase
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from hummingbot.connector.derivative.grvt_perpetual.grvt_perpetual_auth import GrvtPerpetualAuth
from hummingbot.connector.derivative.grvt_perpetual import grvt_perpetual_constants as CONSTANTS
from hummingbot.connector.derivative.grvt_perpetual.grvt_perpetual_web_utils import (
    grvt_symbol_to_trading_pair,
    trading_pair_to_grvt_symbol,
    public_rest_url,
    private_rest_url,
)


# =================== Auth Tests ===================

class TestGrvtPerpetualAuth(TestCase):

    def setUp(self):
        self.api_key = "test_api_key"
        # Use a known test private key (not a real key)
        self.api_secret = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
        self.sub_account_id = "123456789"
        self.auth = GrvtPerpetualAuth(
            api_key=self.api_key,
            api_secret=self.api_secret,
            sub_account_id=self.sub_account_id,
        )

    def test_initial_state_not_authenticated(self):
        self.assertFalse(self.auth.is_session_valid)
        self.assertIsNone(self.auth.account_id)

    def test_set_session_marks_valid(self):
        self.auth.set_session("test_cookie_value", "acct_123")
        self.assertTrue(self.auth.is_session_valid)
        self.assertEqual(self.auth.account_id, "acct_123")

    def test_session_expires(self):
        self.auth.set_session("cookie", "acct")
        self.auth._cookie_expiry = time.time() - 1  # expired
        self.assertFalse(self.auth.is_session_valid)

    def test_get_auth_login_payload(self):
        payload = self.auth.get_auth_login_payload()
        self.assertEqual(payload["api_key"], self.api_key)

    def test_sign_order_returns_dict_with_signature(self):
        result = self.auth.sign_order(
            instrument="BTC_USDT_Perp",
            is_buying=True,
            limit_price="50000",
            quantity="0.1",
            expiry=int(time.time() + 3600) * 1_000_000_000,
            nonce=12345,
        )
        self.assertIn("signature", result)
        self.assertIn("legs", result)
        self.assertEqual(result["legs"][0]["instrument"], "BTC_USDT_Perp")
        self.assertEqual(result["legs"][0]["is_buying_asset"], True)

    def test_sign_order_market_has_zero_price(self):
        result = self.auth.sign_order(
            instrument="ETH_USDT_Perp",
            is_buying=False,
            limit_price="0",
            quantity="1.0",
            expiry=int(time.time() + 3600) * 1_000_000_000,
            nonce=99999,
        )
        self.assertEqual(result["legs"][0]["limit_price"], "0")
        self.assertTrue(result["is_market"])

    def test_sign_order_sell_side(self):
        result = self.auth.sign_order(
            instrument="BTC_USDT_Perp",
            is_buying=False,
            limit_price="60000",
            quantity="0.5",
            expiry=int(time.time() + 3600) * 1_000_000_000,
            nonce=54321,
        )
        self.assertFalse(result["legs"][0]["is_buying_asset"])

    def test_rest_authenticate_adds_cookie_header(self):
        self.auth.set_session("my_cookie", "acct_456")

        request = MagicMock()
        request.headers = {}

        async def run():
            return await self.auth.rest_authenticate(request)

        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertIn("Cookie", result.headers)
        self.assertIn("gravity=my_cookie", result.headers["Cookie"])
        self.assertEqual(result.headers["X-Grvt-Account-Id"], "acct_456")

    def test_rest_authenticate_skips_if_not_authed(self):
        request = MagicMock()
        request.headers = {}

        async def run():
            return await self.auth.rest_authenticate(request)

        result = asyncio.get_event_loop().run_until_complete(run())
        # Should not add cookie if not authenticated
        self.assertNotIn("Cookie", result.headers)

    def test_ws_authenticate_adds_headers(self):
        self.auth.set_session("ws_cookie", "acct_ws")
        request = MagicMock()
        request.headers = {}

        async def run():
            return await self.auth.ws_authenticate(request)

        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertIn("Cookie", result.headers)

    def test_timestamp_nanoseconds(self):
        ts = self.auth._get_timestamp()
        self.assertGreater(ts, 1_000_000_000_000_000_000)  # > 1s in nanoseconds


# =================== Web Utils Tests ===================

class TestGrvtWebUtils(TestCase):

    def test_grvt_symbol_to_trading_pair_perp(self):
        self.assertEqual(grvt_symbol_to_trading_pair("BTC_USDT_Perp"), "BTC-USDT")

    def test_grvt_symbol_to_trading_pair_eth(self):
        self.assertEqual(grvt_symbol_to_trading_pair("ETH_USDT_Perp"), "ETH-USDT")

    def test_trading_pair_to_grvt_symbol(self):
        self.assertEqual(trading_pair_to_grvt_symbol("BTC-USDT"), "BTC_USDT_Perp")

    def test_trading_pair_roundtrip(self):
        pairs = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "ARB-USDT"]
        for pair in pairs:
            grvt = trading_pair_to_grvt_symbol(pair)
            back = grvt_symbol_to_trading_pair(grvt)
            self.assertEqual(back, pair, f"Roundtrip failed for {pair}")

    def test_public_rest_url_mainnet(self):
        url = public_rest_url(CONSTANTS.INSTRUMENTS_PATH, CONSTANTS.DOMAIN)
        self.assertTrue(url.startswith("https://edge.grvt.io"))

    def test_public_rest_url_testnet(self):
        url = public_rest_url(CONSTANTS.INSTRUMENTS_PATH, CONSTANTS.TESTNET_DOMAIN)
        self.assertTrue(url.startswith("https://edge.testnet.grvt.io"))

    def test_private_rest_url_matches_public(self):
        pub = public_rest_url(CONSTANTS.CREATE_ORDER_PATH)
        priv = private_rest_url(CONSTANTS.CREATE_ORDER_PATH)
        self.assertEqual(pub, priv)


# =================== Constants Tests ===================

class TestGrvtConstants(TestCase):

    def test_order_state_map_complete(self):
        required = ["OPEN", "FILLED", "CANCELLED", "PARTIALLY_FILLED", "REJECTED", "EXPIRED"]
        for state in required:
            self.assertIn(state, CONSTANTS.ORDER_STATE_MAP, f"Missing state: {state}")

    def test_rate_limits_defined(self):
        self.assertGreater(len(CONSTANTS.RATE_LIMITS), 0)

    def test_chain_ids(self):
        self.assertEqual(CONSTANTS.MAINNET_CHAIN_ID, 325)
        self.assertEqual(CONSTANTS.TESTNET_CHAIN_ID, 326)

    def test_ws_streams_defined(self):
        self.assertTrue(CONSTANTS.WS_ORDER_BOOK_STREAM.startswith("v1."))
        self.assertTrue(CONSTANTS.WS_ORDER_STREAM.startswith("v1."))
        self.assertTrue(CONSTANTS.WS_FILLS_STREAM.startswith("v1."))

    def test_rest_paths_start_with_slash(self):
        paths = [
            CONSTANTS.INSTRUMENTS_PATH,
            CONSTANTS.CREATE_ORDER_PATH,
            CONSTANTS.CANCEL_ORDER_PATH,
            CONSTANTS.GET_POSITIONS_PATH,
            CONSTANTS.GET_BALANCES_PATH,
        ]
        for p in paths:
            self.assertTrue(p.startswith("/"), f"Path should start with /: {p}")


# =================== Order Book Data Source Tests ===================

class TestGrvtOrderBookDataSource(TestCase):

    def setUp(self):
        self.trading_pairs = ["BTC-USDT", "ETH-USDT"]

    def test_channel_originating_message_book(self):
        from hummingbot.connector.derivative.grvt_perpetual.grvt_perpetual_api_order_book_data_source import (
            GrvtPerpetualAPIOrderBookDataSource,
        )
        ds = GrvtPerpetualAPIOrderBookDataSource.__new__(GrvtPerpetualAPIOrderBookDataSource)
        ds._diff_messages_queue_key = "diff"
        ds._trade_messages_queue_key = "trade"
        ds._funding_info_messages_queue_key = "funding"

        self.assertEqual(ds._channel_originating_message({"stream": "v1.book.s"}), "diff")
        self.assertEqual(ds._channel_originating_message({"stream": "v1.trade"}), "trade")
        self.assertEqual(ds._channel_originating_message({"stream": "v1.mini.s"}), "funding")
        self.assertEqual(ds._channel_originating_message({"stream": "v1.ticker"}), "funding")

    def test_parse_ob_diff_message_delta(self):
        from hummingbot.connector.derivative.grvt_perpetual.grvt_perpetual_api_order_book_data_source import (
            GrvtPerpetualAPIOrderBookDataSource,
        )
        from hummingbot.core.data_type.order_book_message import OrderBookMessageType
        ds = GrvtPerpetualAPIOrderBookDataSource.__new__(GrvtPerpetualAPIOrderBookDataSource)
        ds._domain = CONSTANTS.DOMAIN

        msg = {
            "stream": "v1.book.s",
            "selector": "BTC_USDT_Perp@500-100-10",
            "sequence_number": "5",
            "feed": {
                "bids": [{"price": "50000", "size": "1.5"}],
                "asks": [{"price": "50001", "size": "0.5"}],
                "event_time": str(int(time.time() * 1e9)),
            },
        }
        queue = asyncio.Queue()
        asyncio.get_event_loop().run_until_complete(ds._parse_order_book_diff_message(msg, queue))
        result = queue.get_nowait()
        self.assertEqual(result.type, OrderBookMessageType.DIFF)
        self.assertEqual(result.content["trading_pair"], "BTC-USDT")
        self.assertEqual(len(result.content["bids"]), 1)
        self.assertEqual(len(result.content["asks"]), 1)

    def test_parse_ob_snapshot_message(self):
        from hummingbot.connector.derivative.grvt_perpetual.grvt_perpetual_api_order_book_data_source import (
            GrvtPerpetualAPIOrderBookDataSource,
        )
        from hummingbot.core.data_type.order_book_message import OrderBookMessageType
        ds = GrvtPerpetualAPIOrderBookDataSource.__new__(GrvtPerpetualAPIOrderBookDataSource)
        ds._domain = CONSTANTS.DOMAIN

        msg = {
            "stream": "v1.book.s",
            "selector": "ETH_USDT_Perp@500-100-10",
            "sequence_number": "0",  # 0 = snapshot
            "feed": {
                "bids": [{"price": "3000", "size": "10"}],
                "asks": [{"price": "3001", "size": "5"}],
                "event_time": str(int(time.time() * 1e9)),
            },
        }
        queue = asyncio.Queue()
        asyncio.get_event_loop().run_until_complete(ds._parse_order_book_diff_message(msg, queue))
        result = queue.get_nowait()
        self.assertEqual(result.type, OrderBookMessageType.SNAPSHOT)

    def test_parse_trade_message(self):
        from hummingbot.connector.derivative.grvt_perpetual.grvt_perpetual_api_order_book_data_source import (
            GrvtPerpetualAPIOrderBookDataSource,
        )
        from hummingbot.core.data_type.order_book_message import OrderBookMessageType
        ds = GrvtPerpetualAPIOrderBookDataSource.__new__(GrvtPerpetualAPIOrderBookDataSource)

        msg = {
            "stream": "v1.trade",
            "selector": "BTC_USDT_Perp",
            "sequence_number": "1",
            "feed": {
                "price": "50000",
                "size": "0.1",
                "is_taker_buyer": True,
                "event_time": str(int(time.time() * 1e9)),
            },
        }
        queue = asyncio.Queue()
        asyncio.get_event_loop().run_until_complete(ds._parse_trade_message(msg, queue))
        result = queue.get_nowait()
        self.assertEqual(result.type, OrderBookMessageType.TRADE)
        self.assertEqual(result.content["trading_pair"], "BTC-USDT")
        self.assertEqual(float(result.content["price"]), 50000.0)


# =================== Derivative Tests ===================

class TestGrvtPerpetualDerivative(TestCase):

    def _make_connector(self):
        from hummingbot.connector.derivative.grvt_perpetual.grvt_perpetual_derivative import (
            GrvtPerpetualDerivative,
        )
        config_map = MagicMock()
        config_map.network_timeout = 30
        connector = GrvtPerpetualDerivative.__new__(GrvtPerpetualDerivative)
        connector._domain = CONSTANTS.DOMAIN
        connector._auth = GrvtPerpetualAuth(
            api_key="key",
            api_secret="0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
            sub_account_id="123",
        )
        connector._trading_pairs = ["BTC-USDT"]
        connector._instrument_info = {}
        return connector

    def test_name_mainnet(self):
        c = self._make_connector()
        self.assertEqual(c.name, CONSTANTS.EXCHANGE_NAME)

    def test_name_testnet(self):
        c = self._make_connector()
        c._domain = CONSTANTS.TESTNET_DOMAIN
        self.assertEqual(c.name, CONSTANTS.TESTNET_DOMAIN)

    def test_client_order_id_prefix(self):
        c = self._make_connector()
        self.assertEqual(c.client_order_id_prefix, "HBOT")

    def test_supported_order_types(self):
        from hummingbot.core.data_type.common import OrderType
        c = self._make_connector()
        types = c.supported_order_types()
        self.assertIn(OrderType.LIMIT, types)
        self.assertIn(OrderType.MARKET, types)

    def test_supported_position_modes(self):
        from hummingbot.core.data_type.common import PositionMode
        c = self._make_connector()
        modes = c.supported_position_modes()
        self.assertEqual(modes, [PositionMode.ONEWAY])

    def test_collateral_tokens_usdt(self):
        c = self._make_connector()
        self.assertEqual(c.get_buy_collateral_token("BTC-USDT"), "USDT")
        self.assertEqual(c.get_sell_collateral_token("ETH-USDT"), "USDT")

    def test_format_trading_rules_parses_valid(self):
        from hummingbot.connector.derivative.grvt_perpetual.grvt_perpetual_derivative import (
            GrvtPerpetualDerivative,
        )
        c = self._make_connector()
        exchange_info = {
            "result": [
                {
                    "instrument": "BTC_USDT_Perp",
                    "instrument_type": "PERPETUAL",
                    "is_active": True,
                    "base_asset": "BTC",
                    "quote_asset": "USDT",
                    "min_size": "0.001",
                    "tick_size": "0.5",
                },
                {
                    "instrument": "BTC_USDT_Spot",
                    "instrument_type": "SPOT",
                    "is_active": True,
                },
            ]
        }
        rules = asyncio.get_event_loop().run_until_complete(c._format_trading_rules(exchange_info))
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].trading_pair, "BTC-USDT")
        self.assertEqual(rules[0].min_order_size, Decimal("0.001"))
        self.assertEqual(rules[0].min_price_increment, Decimal("0.5"))

    def test_format_trading_rules_skips_inactive(self):
        c = self._make_connector()
        exchange_info = {
            "result": [
                {
                    "instrument": "ETH_USDT_Perp",
                    "instrument_type": "PERPETUAL",
                    "is_active": False,
                },
            ]
        }
        rules = asyncio.get_event_loop().run_until_complete(c._format_trading_rules(exchange_info))
        self.assertEqual(len(rules), 0)

    def test_is_cancel_request_synchronous(self):
        c = self._make_connector()
        self.assertFalse(c.is_cancel_request_in_exchange_synchronous)

    def test_position_mode_oneway(self):
        from hummingbot.core.data_type.common import PositionMode
        c = self._make_connector()
        mode = asyncio.get_event_loop().run_until_complete(c._get_position_mode())
        self.assertEqual(mode, PositionMode.ONEWAY)

    def test_set_leverage_always_succeeds(self):
        c = self._make_connector()
        ok, msg = asyncio.get_event_loop().run_until_complete(
            c._set_trading_pair_leverage("BTC-USDT", 10)
        )
        self.assertTrue(ok)

    def test_position_mode_hedge_rejected(self):
        from hummingbot.core.data_type.common import PositionMode
        c = self._make_connector()
        ok, msg = asyncio.get_event_loop().run_until_complete(
            c._trading_pair_position_mode_set(PositionMode.HEDGE, "BTC-USDT")
        )
        self.assertFalse(ok)
        self.assertIn("one-way", msg.lower())
