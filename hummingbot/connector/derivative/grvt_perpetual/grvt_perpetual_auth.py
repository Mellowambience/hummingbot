"""
Authentication for the GRVT Perpetual connector.

GRVT uses session-cookie-based authentication:
1. POST /auth/api_key/login with api_key in body
2. Response sets a `gravity=...` session cookie + X-Grvt-Account-Id header
3. All subsequent private REST calls must include:
   - Cookie: gravity=<token>
   - X-Grvt-Account-Id: <sub_account_id>
4. Private WS: connect with same cookie + header (or ?x_grvt_account_id= query param)

Ref: https://api-docs.grvt.io
"""
import time
from typing import Any, Dict, Optional

from hummingbot.connector.time_synchronizer import TimeSynchronizer
from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.connections.data_types import RESTRequest, WSRequest


class GrvtPerpetualAuth(AuthBase):
    def __init__(
        self,
        api_key: str,
        sub_account_id: str,
        time_provider: TimeSynchronizer,
        domain: str = "prod",
    ):
        self._api_key = api_key
        self._sub_account_id = sub_account_id
        self._time_provider = time_provider
        self._domain = domain

        # Populated after login
        self._session_cookie: Optional[str] = None
        self._account_id: Optional[str] = None

    # ── Properties ─────────────────────────────────────────────────────────────
    @property
    def api_key(self) -> str:
        return self._api_key

    @property
    def sub_account_id(self) -> str:
        return self._sub_account_id

    @property
    def session_cookie(self) -> Optional[str]:
        return self._session_cookie

    @session_cookie.setter
    def session_cookie(self, value: str):
        self._session_cookie = value

    @property
    def account_id(self) -> Optional[str]:
        return self._account_id

    @account_id.setter
    def account_id(self, value: str):
        self._account_id = value

    def is_authenticated(self) -> bool:
        return self._session_cookie is not None and self._account_id is not None

    # ── AuthBase methods ────────────────────────────────────────────────────────
    async def rest_authenticate(self, request: RESTRequest) -> RESTRequest:
        """Inject auth headers into private REST request."""
        if self.is_authenticated():
            request.headers = request.headers or {}
            request.headers["Cookie"] = f"gravity={self._session_cookie}"
            request.headers["X-Grvt-Account-Id"] = self._account_id
        return request

    async def ws_authenticate(self, request: WSRequest) -> WSRequest:
        """Inject auth headers into private WS handshake."""
        if self.is_authenticated():
            request.additional_headers = request.additional_headers or {}
            request.additional_headers["Cookie"] = f"gravity={self._session_cookie}"
            request.additional_headers["X-Grvt-Account-Id"] = self._account_id
        return request

    def get_auth_payload(self) -> Dict[str, Any]:
        """Payload for the login endpoint."""
        return {"api_key": self._api_key}

    def get_auth_headers(self) -> Dict[str, str]:
        """Headers for private REST calls (after login)."""
        if not self.is_authenticated():
            return {}
        return {
            "Cookie": f"gravity={self._session_cookie}",
            "X-Grvt-Account-Id": self._account_id,
        }
