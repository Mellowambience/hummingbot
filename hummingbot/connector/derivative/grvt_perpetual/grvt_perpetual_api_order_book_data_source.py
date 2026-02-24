import asyncio
import time
from typing import Any, Dict, List, Optional

from hummingbot.connector.derivative.grvt_perpetual import grvt_perpetual_constants as CONSTANTS
from hummingbot.connector.derivative.grvt_perpetual.grvt_perpetual_web_utils import (
    grvt_symbol_to_trading_pair,
    public_rest_url,
    trading_pair_to_grvt_symbol,
    ws_url,
)
from hummingbot.core.data_type.common import TradeType
from hummingbot.core.data_type.funding_info import FundingInfo, FundingInfoUpdate
from hummingbot.core.data_type.order_book_message import OrderBookMessage, OrderBookMessageType
from hummingbot.core.data_type.perpetual_api_order_book_data_source import PerpetualAPIOrderBookDataSource
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, RESTRequest, WSJSONRequest
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.logger import HummingbotLogger


class GrvtPerpetualAPIOrderBookDataSource(PerpetualAPIOrderBookDataSource):

    def __init__(
        self,
        trading_pairs: List[str],
        connector,
        api_factory: WebAssistantsFactory,
        domain: str = CONSTANTS.DOMAIN,
    ):
        super().__init__(trading_pairs)
        self._connector = connector
        self._api_factory = api_factory
        self._domain = domain
        self._trading_pairs = trading_pairs

    async def get_last_traded_prices(self, trading_pairs: List[str], domain: Optional[str] = None) -> Dict[str, float]:
        result = {}
        rest = await self._api_factory.get_rest_assistant()
        for pair in trading_pairs:
            instrument = trading_pair_to_grvt_symbol(pair)
            url = public_rest_url(CONSTANTS.TICKER_PATH, domain or self._domain)
            request = RESTRequest(
                method=RESTMethod.POST,
                url=url,
                data={"instrument": instrument},
                is_auth_required=False,
            )
            response = await rest.call(request=request)
            data = await response.json()
            if data.get("result"):
                result[pair] = float(data["result"].get("mark_price", 0))
        return result

    async def _request_order_book_snapshot(self, trading_pair: str) -> Dict[str, Any]:
        instrument = trading_pair_to_grvt_symbol(trading_pair)
        rest = await self._api_factory.get_rest_assistant()
        url = public_rest_url(CONSTANTS.ORDER_BOOK_PATH, self._domain)
        request = RESTRequest(
            method=RESTMethod.POST,
            url=url,
            data={"instrument": instrument, "depth": 50},
            is_auth_required=False,
        )
        response = await rest.call(request=request)
        return await response.json()

    async def _subscribe_channels(self, ws: WSAssistant) -> None:
        for pair in self._trading_pairs:
            instrument = trading_pair_to_grvt_symbol(pair)
            # Subscribe order book
            await ws.send(WSJSONRequest({
                "stream": CONSTANTS.WS_ORDER_BOOK_STREAM,
                "feed": [f"{instrument}@500-100-10"],
                "method": "subscribe",
                "is_full": True,
            }))
            # Subscribe trades
            await ws.send(WSJSONRequest({
                "stream": CONSTANTS.WS_TRADES_STREAM,
                "feed": [instrument],
                "method": "subscribe",
                "is_full": True,
            }))
            # Subscribe ticker (for funding info)
            await ws.send(WSJSONRequest({
                "stream": CONSTANTS.WS_TICKER_STREAM,
                "feed": [instrument],
                "method": "subscribe",
                "is_full": True,
            }))

    def _channel_originating_message(self, event_message: Dict[str, Any]) -> str:
        stream = event_message.get("stream", "")
        if "book" in stream:
            return self._diff_messages_queue_key
        elif "trade" in stream:
            return self._trade_messages_queue_key
        elif "mini" in stream or "ticker" in stream:
            return self._funding_info_messages_queue_key
        return ""

    async def _parse_order_book_diff_message(self, raw_message: Dict[str, Any], message_queue: asyncio.Queue) -> None:
        feed = raw_message.get("feed", {})
        selector = raw_message.get("selector", "")
        instrument = selector.split("@")[0] if "@" in selector else selector
        trading_pair = grvt_symbol_to_trading_pair(instrument)

        bids = [[float(b["price"]), float(b["size"])] for b in feed.get("bids", [])]
        asks = [[float(a["price"]), float(a["size"])] for a in feed.get("asks", [])]

        seq = int(raw_message.get("sequence_number", 0))
        msg_type = OrderBookMessageType.SNAPSHOT if seq == 0 else OrderBookMessageType.DIFF

        msg = OrderBookMessage(
            message_type=msg_type,
            content={
                "trading_pair": trading_pair,
                "update_id": seq,
                "bids": bids,
                "asks": asks,
            },
            timestamp=int(feed.get("event_time", time.time() * 1e9)) / 1e9,
        )
        await message_queue.put(msg)

    async def _parse_trade_message(self, raw_message: Dict[str, Any], message_queue: asyncio.Queue) -> None:
        feed = raw_message.get("feed", {})
        selector = raw_message.get("selector", "")
        instrument = selector.split("@")[0] if "@" in selector else selector
        trading_pair = grvt_symbol_to_trading_pair(instrument)

        trade_type = TradeType.BUY if feed.get("is_taker_buyer", False) else TradeType.SELL
        msg = OrderBookMessage(
            message_type=OrderBookMessageType.TRADE,
            content={
                "trading_pair": trading_pair,
                "trade_type": float(trade_type.value),
                "trade_id": str(feed.get("event_time", "")),
                "price": float(feed.get("price", 0)),
                "amount": float(feed.get("size", 0)),
            },
            timestamp=int(feed.get("event_time", time.time() * 1e9)) / 1e9,
        )
        await message_queue.put(msg)

    async def _parse_funding_info_message(
        self, raw_message: Dict[str, Any], message_queue: asyncio.Queue
    ) -> None:
        feed = raw_message.get("feed", {})
        selector = raw_message.get("selector", "")
        trading_pair = grvt_symbol_to_trading_pair(selector)

        info_update = FundingInfoUpdate(
            trading_pair=trading_pair,
            index_price=float(feed.get("index_price", 0)),
            mark_price=float(feed.get("mark_price", 0)),
            next_funding_utc_timestamp=int(feed.get("next_funding_time", 0)) // 1_000_000_000,
            rate=float(feed.get("funding_rate_curr", 0)),
        )
        await message_queue.put(info_update)

    async def get_funding_info(self, trading_pair: str) -> FundingInfo:
        instrument = trading_pair_to_grvt_symbol(trading_pair)
        rest = await self._api_factory.get_rest_assistant()
        url = public_rest_url(CONSTANTS.FUNDING_RATE_PATH, self._domain)
        request = RESTRequest(
            method=RESTMethod.POST,
            url=url,
            data={"instrument": instrument},
            is_auth_required=False,
        )
        response = await rest.call(request=request)
        data = await response.json()
        result = data.get("result", {})

        ticker_url = public_rest_url(CONSTANTS.TICKER_PATH, self._domain)
        ticker_req = RESTRequest(
            method=RESTMethod.POST,
            url=ticker_url,
            data={"instrument": instrument},
            is_auth_required=False,
        )
        ticker_resp = await rest.call(request=ticker_req)
        ticker_data = await ticker_resp.json()
        ticker = ticker_data.get("result", {})

        return FundingInfo(
            trading_pair=trading_pair,
            index_price=float(ticker.get("index_price", 0)),
            mark_price=float(ticker.get("mark_price", 0)),
            next_funding_utc_timestamp=int(ticker.get("next_funding_time", 0)) // 1_000_000_000,
            rate=float(result.get("funding_rate", 0)),
        )

    async def _connected_websocket_assistant(self) -> WSAssistant:
        ws = await self._api_factory.get_ws_assistant()
        await ws.connect(
            ws_url=ws_url(self._domain, private=False),
            ping_timeout=20,
            message_timeout=30,
        )
        return ws
