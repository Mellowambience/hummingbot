import hashlib
import hmac
import json
import time
from typing import Any, Dict, Optional

import eth_account
from eth_account.messages import encode_typed_data

from hummingbot.connector.derivative.grvt_perpetual import grvt_perpetual_constants as CONSTANTS
from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, RESTRequest, WSRequest


class GrvtPerpetualAuth(AuthBase):
    """
    GRVT Authentication:
    - REST: Session cookie obtained by POST /auth/api_key/login with API key.
      Cookie `gravity=<value>` is set and included in subsequent requests.
      Header X-Grvt-Account-Id must also be set.
    - Order signing: EIP-712 typed-data signing using a private key (Ethereum wallet).
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,  # Ethereum private key for EIP-712 order signing
        sub_account_id: str,
        domain: str = CONSTANTS.DOMAIN,
    ):
        self._api_key = api_key
        self._api_secret = api_secret
        self._sub_account_id = sub_account_id
        self._domain = domain
        self._session_cookie: Optional[str] = None
        self._account_id: Optional[str] = None
        self._cookie_expiry: float = 0.0

    @property
    def sub_account_id(self) -> str:
        return self._sub_account_id

    @property
    def account_id(self) -> Optional[str]:
        return self._account_id

    def set_session(self, cookie: str, account_id: str) -> None:
        """Called after successful auth to store session cookie."""
        self._session_cookie = cookie
        self._account_id = account_id
        # Cookies typically valid for 24h; refresh conservatively at 23h
        self._cookie_expiry = time.time() + 23 * 3600

    @property
    def is_session_valid(self) -> bool:
        return (
            self._session_cookie is not None
            and self._account_id is not None
            and time.time() < self._cookie_expiry
        )

    def get_auth_login_payload(self) -> Dict[str, Any]:
        return {"api_key": self._api_key}

    async def rest_authenticate(self, request: RESTRequest) -> RESTRequest:
        """Add auth cookie and account ID header to REST requests."""
        if not self.is_session_valid:
            # Session refresh is handled by the derivative class; skip headers if not authed
            return request

        headers = dict(request.headers or {})
        headers["Cookie"] = f"gravity={self._session_cookie}"
        headers["X-Grvt-Account-Id"] = self._account_id
        request.headers = headers
        return request

    async def ws_authenticate(self, request: WSRequest) -> WSRequest:
        """Add auth headers to WebSocket handshake."""
        if not self.is_session_valid:
            return request

        headers = dict(request.headers or {})
        headers["Cookie"] = f"gravity={self._session_cookie}"
        headers["X-Grvt-Account-Id"] = self._account_id
        request.headers = headers
        return request

    def sign_order(
        self,
        instrument: str,
        is_buying: bool,
        limit_price: str,
        quantity: str,
        expiry: int,
        nonce: int,
        time_in_force: str = "GOOD_TILL_CANCEL",
        chain_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        EIP-712 order signing per GRVT spec.
        Returns the signed order payload ready for the create order endpoint.
        """
        if chain_id is None:
            chain_id = (
                CONSTANTS.TESTNET_CHAIN_ID
                if "testnet" in self._domain
                else CONSTANTS.MAINNET_CHAIN_ID
            )

        order_data = {
            "sub_account_id": self._sub_account_id,
            "is_market": limit_price == "0",
            "time_in_force": time_in_force,
            "taker_fee_percentage_cap": "0",
            "self_trade_behavior": "CANCEL_TAKER",
            "legs": [
                {
                    "instrument": instrument,
                    "size": quantity,
                    "limit_price": limit_price,
                    "is_buying_asset": is_buying,
                }
            ],
            "nonce": nonce,
            "expiration": expiry,
        }

        # EIP-712 domain for GRVT
        domain_data = {
            "name": "GRVT Exchange",
            "version": "1",
            "chainId": chain_id,
        }

        # EIP-712 typed data structure for Order
        typed_data = {
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                ],
                "Order": [
                    {"name": "sub_account_id", "type": "uint64"},
                    {"name": "is_market", "type": "bool"},
                    {"name": "time_in_force", "type": "uint8"},
                    {"name": "taker_fee_percentage_cap", "type": "uint32"},
                    {"name": "self_trade_behavior", "type": "uint8"},
                    {"name": "legs", "type": "OrderLeg[]"},
                    {"name": "nonce", "type": "uint32"},
                    {"name": "expiration", "type": "int64"},
                ],
                "OrderLeg": [
                    {"name": "instrument", "type": "uint64"},
                    {"name": "size", "type": "uint64"},
                    {"name": "limit_price", "type": "uint64"},
                    {"name": "is_buying_asset", "type": "bool"},
                ],
            },
            "primaryType": "Order",
            "domain": domain_data,
            "message": order_data,
        }

        try:
            acct = eth_account.Account.from_key(self._api_secret)
            encoded = encode_typed_data(full_message=typed_data)
            signed = acct.sign_message(encoded)
            signature = signed.signature.hex()
            if not signature.startswith("0x"):
                signature = "0x" + signature
        except Exception:
            # Fallback: return unsigned order (will be rejected, but won't crash)
            signature = "0x"

        order_data["signature"] = {
            "signer": eth_account.Account.from_key(self._api_secret).address,
            "r": "0x" + signature[2:66] if len(signature) >= 66 else "0x",
            "s": "0x" + signature[66:130] if len(signature) >= 130 else "0x",
            "v": int(signature[130:132], 16) if len(signature) >= 132 else 27,
            "expiration": str(expiry),
            "nonce": nonce,
        }

        return order_data

    def _get_timestamp(self) -> int:
        return int(time.time() * 1e9)  # GRVT uses nanoseconds
