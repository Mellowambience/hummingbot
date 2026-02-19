import hashlib
import hmac
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode

from hummingbot.connector.time_synchronizer import TimeSynchronizer
from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, RESTRequest, WSRequest


class DecibelPerpetualAuth(AuthBase):
    """
    Decibel Perpetual API authentication.
    Uses HMAC-SHA256 signature: signature = HMAC_SHA256(secret, timestamp + method + path + body)
    """

    def __init__(self, api_key: str, api_secret: str, time_provider: TimeSynchronizer):
        self._api_key = api_key
        self._api_secret = api_secret
        self._time_provider = time_provider

    async def rest_authenticate(self, request: RESTRequest) -> RESTRequest:
        timestamp = str(int(self._time_provider.time() * 1000))
        method = request.method.value.upper()
        path = request.url.split(request.url.split("/v1")[0])[-1]
        if "/v1" in request.url:
            path = "/v1" + request.url.split("/v1")[1]
        body = request.data or ""
        if isinstance(body, dict):
            import json
            body = json.dumps(body, separators=(",", ":"))

        signature = self._generate_signature(timestamp, method, path, body)

        headers = dict(request.headers or {})
        headers["DB-ACCESS-KEY"] = self._api_key
        headers["DB-ACCESS-TIMESTAMP"] = timestamp
        headers["DB-ACCESS-SIGN"] = signature
        headers["Content-Type"] = "application/json"
        request.headers = headers
        return request

    async def ws_authenticate(self, request: WSRequest) -> WSRequest:
        timestamp = str(int(self._time_provider.time() * 1000))
        signature = self._generate_signature(timestamp, "GET", "/realtime", "")
        request.payload = {
            "op": "auth",
            "args": [self._api_key, timestamp, signature],
        }
        return request

    def _generate_signature(self, timestamp: str, method: str, path: str, body: str) -> str:
        message = timestamp + method + path + (body or "")
        return hmac.new(
            self._api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def add_auth_to_params(self, params: Dict[str, Any], timestamp: Optional[str] = None) -> Dict[str, Any]:
        if timestamp is None:
            timestamp = str(int(self._time_provider.time() * 1000))
        params["timestamp"] = timestamp
        return params
