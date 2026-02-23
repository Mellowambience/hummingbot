"""
Private user stream data source for the GRVT Perpetual connector.
Handles authenticated WebSocket streams for orders, fills, and positions.
"""
import asyncio
import logging
from typing import Optional

import aiohttp

from hummingbot.connector.derivative.grvt_perpetual import grvt_perpetual_constants as CONSTANTS
from hummingbot.connector.derivative.grvt_perpetual.grvt_perpetual_auth import GrvtPerpetualAuth
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource


class GrvtPerpetualAPIUserStreamDataSource(UserStreamTrackerDataSource):
    _logger: Optional[logging.Logger] = None
    HEARTBEAT_INTERVAL = 30.0

    def __init__(
        self,
        auth: GrvtPerpetualAuth,
        trading_pairs=None,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
    ):
        super().__init__()
        self._auth = auth
        self._trading_pairs = trading_pairs or []
        self._domain = domain

    @classmethod
    def logger(cls) -> logging.Logger:
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger

    async def listen_for_user_stream(self, output: asyncio.Queue):
        ws_url = CONSTANTS.PRIVATE_WS_URLS[self._domain]
        while True:
            try:
                headers = self._auth.get_auth_headers()
                async with aiohttp.ClientSession(headers=headers) as session:
                    async with session.ws_connect(ws_url) as ws:
                        # Subscribe to private streams
                        for channel in [
                            CONSTANTS.WS_ORDERS_CHANNEL,
                            CONSTANTS.WS_FILLS_CHANNEL,
                            CONSTANTS.WS_POSITIONS_CHANNEL,
                        ]:
                            await ws.send_json({
                                "stream": channel,
                                "feed": [],
                                "method": "subscribe",
                                "is_full": True,
                            })

                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                data = msg.json()
                                await output.put(data)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger().error(f"GRVT private WS error: {e}. Reconnecting in 5s.")
                await asyncio.sleep(5)

    async def _connected_websocket_assistant(self):
        pass  # Handled in listen_for_user_stream
