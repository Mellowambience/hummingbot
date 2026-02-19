import asyncio
from typing import Any, Dict, List, Optional

from hummingbot.connector.derivative.decibel_perpetual import decibel_perpetual_constants as CONSTANTS
from hummingbot.connector.derivative.decibel_perpetual.decibel_perpetual_auth import DecibelPerpetualAuth
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.web_assistant.connections.data_types import WSJSONRequest
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.logger import HummingbotLogger


class DecibelPerpetualAPIUserStreamDataSource(UserStreamTrackerDataSource):
    _logger: Optional[HummingbotLogger] = None

    def __init__(
        self,
        auth: DecibelPerpetualAuth,
        trading_pairs: List[str],
        connector,
        api_factory: WebAssistantsFactory,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
    ):
        super().__init__()
        self._auth = auth
        self._trading_pairs = trading_pairs
        self._connector = connector
        self._api_factory = api_factory
        self._domain = domain

    async def _connected_websocket_assistant(self) -> WSAssistant:
        ws = await self._api_factory.get_ws_assistant()
        await ws.connect(ws_url=CONSTANTS.DECIBEL_WSS_URL, ping_timeout=CONSTANTS.HEARTBEAT_TIME_INTERVAL)
        # Authenticate
        auth_request = WSJSONRequest(payload={})
        auth_request = await self._auth.ws_authenticate(auth_request)
        await ws.send(auth_request)
        # Wait for auth confirmation
        auth_resp = await ws.receive()
        if not (auth_resp and isinstance(auth_resp.data, dict) and auth_resp.data.get("success")):
            self.logger().warning(f"WebSocket auth response: {auth_resp}")
        return ws

    async def _subscribe_channels(self, ws: WSAssistant):
        subscribe_payload = {
            "op": "subscribe",
            "args": [
                CONSTANTS.WS_ORDERS_CHANNEL,
                CONSTANTS.WS_FILLS_CHANNEL,
                CONSTANTS.WS_POSITIONS_CHANNEL,
            ],
        }
        await ws.send(WSJSONRequest(payload=subscribe_payload))

    async def _get_ws_assistant(self) -> WSAssistant:
        return await self._api_factory.get_ws_assistant()

    async def _on_user_stream_interruption(self, websocket_assistant: Optional[WSAssistant]):
        await super()._on_user_stream_interruption(websocket_assistant=websocket_assistant)

    async def listen_for_user_stream(self, output: asyncio.Queue):
        while True:
            try:
                ws = await self._connected_websocket_assistant()
                await self._subscribe_channels(ws)
                async for msg in ws.iter_messages():
                    if msg.data:
                        output.put_nowait(msg.data)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger().error(f"Unexpected error in user stream: {e}", exc_info=True)
                await asyncio.sleep(5.0)
