import asyncio
import json
import time
from unittest import TestCase
from unittest.mock import AsyncMock, MagicMock, patch

from hummingbot.connector.derivative.decibel_perpetual.decibel_perpetual_api_order_book_data_source import (
    DecibelPerpetualAPIOrderBookDataSource,
)
from hummingbot.core.data_type.order_book_message import OrderBookMessageType


class TestDecibelPerpetualAPIOrderBookDataSource(TestCase):
    def setUp(self):
        self.trading_pairs = ["BTC-USD"]
        self.connector = MagicMock()
        self.connector.exchange_symbol_associated_to_pair = AsyncMock(return_value="BTC-USD")
        self.connector.convert_from_exchange_trading_pair = MagicMock(return_value="BTC-USD")
        self.api_factory = MagicMock()
        self.rest_assistant = AsyncMock()
        self.api_factory.get_rest_assistant = AsyncMock(return_value=self.rest_assistant)
        self.data_source = DecibelPerpetualAPIOrderBookDataSource(
            trading_pairs=self.trading_pairs,
            connector=self.connector,
            api_factory=self.api_factory,
        )

    def test_get_new_order_book_successful(self):
        mock_response = {
            "timestamp": int(time.time() * 1000),
            "data": {
                "bids": [["50000.0", "1.5"], ["49999.0", "2.0"]],
                "asks": [["50001.0", "1.0"], ["50002.0", "3.0"]],
            }
        }
        self.rest_assistant.execute_request = AsyncMock(return_value=mock_response)
        snapshot = asyncio.get_event_loop().run_until_complete(
            self.data_source._order_book_snapshot("BTC-USD")
        )
        self.assertEqual(snapshot.type, OrderBookMessageType.SNAPSHOT)
        self.assertEqual(snapshot.content["trading_pair"], "BTC-USD")
        self.assertEqual(len(snapshot.content["bids"]), 2)
        self.assertEqual(len(snapshot.content["asks"]), 2)
        self.assertEqual(snapshot.content["bids"][0][0], 50000.0)

    def test_get_new_order_book_raises_exception(self):
        self.rest_assistant.execute_request = AsyncMock(side_effect=Exception("Network error"))
        with self.assertRaises(Exception):
            asyncio.get_event_loop().run_until_complete(
                self.data_source._order_book_snapshot("BTC-USD")
            )

    def test_get_last_traded_prices_successful(self):
        mock_response = [
            {"market": "BTC-USD", "markPrice": "50000.0"},
        ]
        self.rest_assistant.execute_request = AsyncMock(return_value=mock_response)
        prices = asyncio.get_event_loop().run_until_complete(
            self.data_source.get_last_traded_prices(["BTC-USD"])
        )
        self.assertIn("BTC-USD", prices)
        self.assertEqual(prices["BTC-USD"], 50000.0)

    def test_get_funding_info(self):
        mock_response = {
            "data": {
                "indexPrice": "50000.0",
                "markPrice": "50010.0",
                "nextFundingTime": str(int(time.time() * 1000) + 3600000),
                "fundingRate": "0.0001",
            }
        }
        self.rest_assistant.execute_request = AsyncMock(return_value=mock_response)
        info = asyncio.get_event_loop().run_until_complete(
            self.data_source.get_funding_info("BTC-USD")
        )
        self.assertEqual(info.trading_pair, "BTC-USD")
        self.assertEqual(float(info.mark_price), 50010.0)
        self.assertEqual(float(info.rate), 0.0001)

    def test_channel_originating_message_orderbook(self):
        event = {"channel": "orderbook.BTC-USD", "data": {}}
        channel = self.data_source._channel_originating_message(event)
        self.assertEqual(channel, self.data_source._diff_messages_queue_key)

    def test_channel_originating_message_trades(self):
        event = {"channel": "trades.BTC-USD", "data": {}}
        channel = self.data_source._channel_originating_message(event)
        self.assertEqual(channel, self.data_source._trade_messages_queue_key)

    def test_parse_trade_message(self):
        raw = {
            "channel": "trades.BTC-USD",
            "market": "BTC-USD",
            "data": {
                "id": 12345,
                "side": "buy",
                "price": "50000.0",
                "size": "0.5",
                "timestamp": int(time.time() * 1000),
            },
        }
        queue = asyncio.Queue()
        asyncio.get_event_loop().run_until_complete(
            self.data_source._parse_trade_message(raw, queue)
        )
        self.assertFalse(queue.empty())
        msg = queue.get_nowait()
        self.assertEqual(msg.type, OrderBookMessageType.TRADE)
        self.assertEqual(msg.content["price"], 50000.0)
