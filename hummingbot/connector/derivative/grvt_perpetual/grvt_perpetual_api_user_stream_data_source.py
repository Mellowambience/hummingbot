import asyncio
from typing import Any, Dict, Optional

from hummingbot.connector.derivative.grvt_perpetual import grvt_perpetual_constants as CONSTANTS
from hummingbot.connector.derivative.grvt_perpetual.grvt_perpetual_auth import GrvtPerpetualAuth
from hummingbot.connector.derivative.grvt_perpetual.grvt_perpetual_web_utils import ws_url
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.web_assistant.connections.data_types import WSJSONRequest
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.logger import HummingbotLogger


class GrvtPerpetualAPIUserStreamDataSource(UserStreamTrackerDataSource):

    def __init__(
        self,
        auth: GrvtPerpetualAuth,
        trading_pairs: list,
        connector,
        api_factory: WebAssistantsFactory,
        domain: str = CONSTANTS.DOMAIN,
    ):
        super().__init__()
        self._auth = auth
        self._trading_pairs = trading_pairs
        self._connector = connector
        self._api_factory = api_factory
        self._domain = domain

    async def _connected_websocket_assistant(self) -> WSAssistant:
        ws = await self._api_factory.get_ws_assistant()
        # Authenticated WS uses the trades endpoint
        ws_endpoint = ws_url(self._domain, private=True)
        if self._auth.account_id:
            ws_endpoint += f"?x_grvt_account_id={self._auth.account_id}"
        await ws.connect(
            ws_url=ws_endpoint,
            ping_timeout=20,
            message_timeout=30,
        )
        return ws

    async def _subscribe_channels(self, websocket_assistant: WSAssistant) -> None:
        """Subscribe to order, position, and fill streams."""
        sub_account = self._auth.sub_account_id

        # Orders stream
        await websocket_assistant.send(WSJSONRequest({
            "stream": CONSTANTS.WS_ORDER_STREAM,
            "feed": [sub_account],
            "method": "subscribe",
            "is_full": True,
        }))

        # Positions stream
        await websocket_assistant.send(WSJSONRequest({
            "stream": CONSTANTS.WS_POSITION_STREAM,
            "feed": [sub_account],
            "method": "subscribe",
            "is_full": True,
        }))

        # Fills stream
        await websocket_assistant.send(WSJSONRequest({
            "stream": CONSTANTS.WS_FILLS_STREAM,
            "feed": [sub_account],
            "method": "subscribe",
            "is_full": True,
        }))

    async def _process_websocket_messages(
        self, websocket_assistant: WSAssistant, queue: asyncio.Queue
    ) -> None:
        async for ws_response in websocket_assistant.iter_messages():
            data = ws_response.data
            if isinstance(data, dict) and "feed" in data:
                await queue.put(data)
