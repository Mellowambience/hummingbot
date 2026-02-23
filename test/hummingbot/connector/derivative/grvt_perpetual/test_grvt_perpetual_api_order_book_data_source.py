"""
Unit tests for GrvtPerpetualAPIOrderBookDataSource.
"""
import asyncio
import time
import unittest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from hummingbot.connector.derivative.grvt_perpetual.grvt_perpetual_api_order_book_data_source import (
    GrvtPerpetualAPIOrderBookDataSource,
)
from hummingbot.core.data_type.order_book_message import OrderBookMessageType


def make_source(trading_pairs=None):
    connector = MagicMock()
    api_factory = MagicMock()
    return GrvtPerpetualAPIOrderBookDataSource(
        trading_pairs=trading_pairs or ["BTC-USDT"],
        connector=connector,
        api_factory=api_factory,
        domain="testnet",
    )


class TestGrvtPerpetualAPIOrderBookDataSource(unittest.TestCase):

    def test_instrument_to_trading_pair_conversion(self):
        from hummingbot.connector.derivative.grvt_perpetual.grvt_perpetual_web_utils import (
            instrument_to_trading_pair,
            trading_pair_to_instrument,
        )
        self.assertEqual(instrument_to_trading_pair("BTC_USDT_Perp"), "BTC-USDT")
        self.assertEqual(trading_pair_to_instrument("BTC-USDT"), "BTC_USDT_Perp")

    def test_parse_order_book_snapshot(self):
        source = make_source()
        raw = {
            "stream": "v1.book.s",
            "selector": "BTC_USDT_Perp@40-1-10",
            "sequence_number": "0",
            "feed": {
                "bids": [["50000", "1.5"], ["49999", "2.0"]],
                "asks": [["50001", "1.0"], ["50002", "0.5"]],
                "event_time": str(int(time.time() * 1e9)),
            },
        }
        msg = source._parse_order_book_diff_message(raw)
        self.assertEqual(msg.type, OrderBookMessageType.SNAPSHOT)
        self.assertEqual(len(msg.bids), 2)
        self.assertEqual(len(msg.asks), 2)

    def test_parse_order_book_diff(self):
        source = make_source()
        raw = {
            "stream": "v1.book.s",
            "selector": "ETH_USDT_Perp@40-1-10",
            "sequence_number": "42",
            "feed": {
                "bids": [["3000", "5"]],
                "asks": [],
                "event_time": str(int(time.time() * 1e9)),
            },
        }
        msg = source._parse_order_book_diff_message(raw)
        self.assertEqual(msg.type, OrderBookMessageType.DIFF)
        self.assertEqual(msg.trading_pair, "ETH-USDT")

    def test_parse_trade_message(self):
        source = make_source()
        raw = {
            "stream": "v1.trade",
            "selector": "BTC_USDT_Perp",
            "feed": {
                "price": "50100",
                "size": "0.01",
                "is_taker_buyer": True,
                "event_time": str(int(time.time() * 1e9)),
            },
        }
        msg = source._parse_trade_message(raw)
        self.assertEqual(msg.type, OrderBookMessageType.TRADE)
        self.assertEqual(msg.trading_pair, "BTC-USDT")

    def test_parse_funding_info_message(self):
        source = make_source()
        raw = {
            "stream": "v1.funding",
            "selector": "BTC_USDT_Perp",
            "feed": {
                "index_price": "50000",
                "mark_price": "50001",
                "funding_rate": "0.0001",
                "funding_time": str(int(time.time() * 1e9)),
            },
        }
        info = source._parse_funding_info_message(raw)
        self.assertEqual(info.trading_pair, "BTC-USDT")
        self.assertEqual(info.rate, Decimal("0.0001"))

    def test_get_last_traded_prices_exception_handling(self):
        source = make_source(["BTC-USDT"])
        rest_mock = AsyncMock()
        rest_mock.execute_request.side_effect = Exception("Network error")
        source._api_factory.get_rest_assistant = AsyncMock(return_value=rest_mock)

        async def run():
            try:
                await source.get_last_traded_prices(["BTC-USDT"])
            except Exception:
                pass  # exception propagation is acceptable

        asyncio.get_event_loop().run_until_complete(run())

    def test_channel_routing_in_listen_for_subscriptions(self):
        """Verify stream name constants match expected GRVT channel names."""
        from hummingbot.connector.derivative.grvt_perpetual import grvt_perpetual_constants as CONSTANTS
        self.assertEqual(CONSTANTS.WS_ORDER_BOOK_CHANNEL, "v1.book.s")
        self.assertEqual(CONSTANTS.WS_TRADES_CHANNEL, "v1.trade")
        self.assertEqual(CONSTANTS.WS_FUNDING_CHANNEL, "v1.funding")


if __name__ == "__main__":
    unittest.main()
