"""
Public order book data source for the GRVT PerVetual connector.
Handles REST snapshots and WebSocket deltas for order book, trades, and funding.
"""
import asyncio
import logging
import time
from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, List, Optional

import aiohttp

from hummingbot.connector.derivative.grvt_perpetual import grvt_perpetual_constants as CONSTANTS
from hummingbot.connector.derivative.grvt_perpetual.grvt_perpetual_web_utils import (
    public_rest_url,
    trading_pair_to_instrument,
    instrument_to_trading_pair,
)
from hummingbot.core.data_type.funding_info import FundingInfo
from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessage, OrderBookMessageType
from hummingbot.core.data_type.perpetual_api_order_book_data_source import PerpetualAPIOrderBookDataSource
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, WSJSONRequest
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory


class GrvtPerpetualAPIOrderBookDataSource(PerpetualAPIOrderBookDataSource):
    _logger: Optional[logging.Logger] = None
    HEARTBEAT_INTERVAL = 30.0
    ONE_HOUR = 60 * 60

    def __init__(
        self,
        trading_pairs: List[str],
        connector,
        api_factory: WebAssistantsFactory,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
    ):
        super().__init__(trading_pairs)
        self._connector = connector
        self._api_factory = api_factory
        self._domain = domain
        self._trading_pairs = trading_pairs
        self._message_queue: Dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)

    @classmethod
    def logger(cls) -> logging.Logger:
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger

    # └ Snapshot └└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└
    async def get_last_traded_prices(self, trading_pairs: List[str], domain: str = None) -> Dict[str, float]:
        result = {}
        for pair in trading_pairs:
            instrument = trading_pair_to_instrument(pair)
            url = public_rest_url(CONSTANTS.TICKER_PATH, domain or self._domain)
            rest = await self._api_factory.get_rest_assistant()
            resp = await rest.execute_request(
                url=url,
                data={"instrument": instrument},
                method=RESTMethod.POST,
                throttler_limit_id=CONSTANTS.TICKER_PATH,
            )
            tickers = resp.get("result", {}).get("tickers", [])
            if tickers:
                result[pair] = float(tickers[0].get("mark_price", 0))
        return result

    async def get_funding_info(self, trading_pair: str) -> FundingInfo:
        instrument = trading_pair_to_instrument(trading_pair)
        url = public_rest_url(CONSTANTS.FUNDING_RATE_PATH, self._domain)
        rest = await self._api_factory.get_rest_assistant()
        resp = await rest.execute_request(
            url=url,
            data={"instrument": instrument, "limit": 1},
            method=RESTMethod.POST,
            throttler_limit_id=CONSTANTS.FUNDING_RATE_PATH,
        )
        entries = resp.get("result", {}).get("entries", [])
        if entries:
            e = entries[0]
            return FundingInfo(
                trading_pair=trading_pair,
                index_price=Decimal(str(e.get("index_price", 0))),
                mark_price=Decimal(str(e.get("mark_price", 0))),
                next_funding_utc_timestamp=int(e.get("funding_time", int(time.time() * 1e9)) / 1e9),
                rate=Decimal(str(e.get("funding_rate", 0))),
            )
        return FundingInfo(
            trading_pair=trading_pair,
            index_price=Decimal("0"),
            mark_price=Decimal("0"),
            next_funding_utc_timestamp=int(time.time()) + 3600,
            rate=Decimal("0"),
        )

    async def get_new_order_book(self, trading_pair: str) -> OrderBook:
        snapshot_msg = await self._order_book_snapshot(trading_pair)
        order_book = self.order_book_create_function()
        order_book.apply_snapshot(snapshot_msg.bids, snapshot_msg.asks, snapshot_msg.update_id)
        return order_book

    async def _order_book_snapshot(self, trading_pair: str) -> OrderBookMessage:
        instrument = trading_pair_to_instrument(trading_pair)
        url = public_rest_url(CONSTANTS.ORDERBOOK_LEVELS_PATH, self._domain)
        rest = await self._api_factory.get_rest_assistant()
        resp = await rest.execute_request(
            url=url,
            data={"instrument": instrument, "depth": 40},
            method=RESTMethod.POST,
            throttler_limit_id=CONSTANTS.ORDERAOOK_LEVELSEPATH_,
        )
        book = resp.get("result", {}).get("book", {})
        bids = [[Decimal(str(p)), Decimal(str(s))] for p, s in book.get("bids", [])]
        asks = [[Decimal(str(p)), Decimal(str(s))] for p, s in book.get("asks", [])]
        ts = int(time.time() * 1e3)
        return OrderBookMessage(
            message_type=OrderBookMessageType.SNAPSHOT,
            content={"trading_pair": trading_pair, "update_id": ts, "bids": bids, "asks": asks},
            timestamp=ts * 1e-3,
        )

    # └ WebSocket └└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└
    async def listen_for_subscriptions(self):
        ws_url = CONSTANTS.WS_URLS[self._domain]
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(ws_url) as ws:
                        for pair in self._trading_pairs:
                            instrument = trading_pair_to_instrument(pair)
                            for channel, feed in [
                                (CONSTANTS.WS_ORDER_BOOK_CHANNEL, f"{instrument}@40-1-10"),
                                (CONSTANTS.WS_TRADES_CHANNEL, instrument),
                                (CONSTANTS.WS_FUNDING_CHANNEL, instrument),
                            ]:
                                await ws.send_json({
                                    "stream": channel,
                                    "feed": [feed],
                                    "method": "subscribe",
                                    "is_full": True,
                                })

                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                data = msg.json()
                                stream = data.get("stream", "")
                                if stream in (CONSTANTS.WS_ORDER_BOOK_CHANNEL,):
                                    await self._message_queue[self._diff_messages_queue_key].put(data)
                                elif stream == CONSTANTS.WS_TRADES_CHANNEL:
                                    await self._message_queue[self._trade_messages_queue_key].put(data)
                                elif stream == CONSTANTS.WS_FUNDING_CHANNEL:
                                    await self._message_queue[self._funding_info_messages_queue_key].put(data)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger().error(f"GRVT WS error: {e}. Reconnecting in 5s.")
                await asyncio.sleep(5)

    async def listen_for_order_book_diffs(self, ev_loop, output: asyncio.Queue):
        while True:
            msg = await self._message_queue[self._diff_messages_queue_key].get()
            try:
                parsed = self._parse_order_book_diff_message(msg)
                await output.put(parsed)
            except Exception as e:
                self.logger().error(f"Error parsing OB diff: {e}", exc_info=True)

    async def listen_for_order_book_snapshots(self, ev_loop, output: asyncio.Queue):
        while True:
            for pair in self._trading_pairs:
                try:
                    snapshot = await self._order_book_snapshot(pair)
                    await output.put(snapshot)
                except Exception as e:
                    self.logger().error(f"Error fetching OB snapshot for {pair}: {e}")
            await asyncio.sleep(self.ONE_HOUR)

    async def listen_for_trades(self, ev_loop, output: asyncio.Queue):
        while True:
            msg = await self._message_queue[self._trade_messages_queue_key].get()
            try:
                parsed = self._parse_trade_message(msg)
                await output.put(parsed)
            except Exception as e:
                self.logger().error(f"Error parsing trade: {e}", exc_info=True)

    async def listen_for_funding_info(self, output: asyncio.Queue):
        while True:
            msg = await self._message_queue[self._funding_info_messages_queue_key].get()
            try:
                parsed = self._parse_funding_info_message(msg)
                await output.put(parsed)
            except Exception as e:
                self.logger().error(f"Error parsing funding info: {e}", exc_info=True)

    # └ Parsers └└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└└
    def _parse_order_book_diff_message(self, raw: Dict) -> OrderBookMessage:
        feed = raw.get("feed", {})
        selector = raw.get("selector", "")
        instrument = selector.split("@")[0] if "@" in selector else selector
        trading_pair = instrument_to_trading_pair(instrument)
        seq = int(raw.get("sequence_number", 0))
        bids = [[Decimal(str(p)), Decimal(str(s))] for p, s in feed.get("bids", [])]
        asks = [[Decimal(str(p)), Decimal(str(s))] for p, s in feed.get("asks", [])]
        ts = int(feed.get("event_time", time.time() * 1e9)) / 1e9
        msg_type = OrderBookMessageType.SNAPSHOT if seq == 0 else OrderBookMessageType.DIFF
        return OrderBookMessage(
            message_type=msg_type,
            content={"trading_pair": trading_pair, "update_id": seq, "bids": bids, "asks": asks},
            timestamp=ts,
        )

    def _parse_trade_message(self, raw: Dict) -> OrderBookMessage:
        feed = raw.get("feed", {})
        selector = raw.get("selector", "")
        instrument = selector.split("@")[0] if "@" in selector else selector
        trading_pair = instrument_to_trading_pair(instrument)
        ts = int(feed.get("event_time", time.time() * 1e9)) / 1e9
        return OrderBookMessage(
            message_type=OrderBookMessageType.TRADE,
            content={
                "trading_pair": trading_pair,
                "trade_type": float(1 if feed.get("is_taker_buyer", True) else 2),
                "trade_id": str(feed.get("event_time", ts)),
                "update_id": int(ts),
                "price": str(feed.get("price", "0")),
                "amount": str(feed.get("size", "0")),
            },
            timestamp=ts,
        )

    def _parse_funding_info_message(self, raw: Dict) -> FundingInfo:
        feed = raw.get("feed", {})
        selector = raw.get("selector", "")
        instrument = selector.split("@")[0] if "@" in selector else selector
        trading_pair = instrument_to_trading_pair(instrument)
        return FundingInfo(
            trading_pair=trading_pair,
            index_price=Decimal(str(feed.get("index_price", 0))),
            mark_price=Decimal(str(feed.get("mark_price", 0))),
            next_funding_utc_timestamp=int(feed.get("funding_time", int(time.time() * 1e9)) / 1e9),
            rate=Decimal(str(feed.get("funding_rate", 0))),
        )
