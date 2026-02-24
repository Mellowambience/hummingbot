from typing import Any, Callable, Dict, Optional

from hummingbot.connector.derivative.grvt_perpetual import grvt_perpetual_constants as CONSTANTS
from hummingbot.connector.time_synchronizer import TimeSynchronizer
from hummingbot.core.api_throttler.async_throttler import AsyncThrottler
from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.connections.data_types import RESTMethod
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory


def public_rest_url(path_url: str, domain: str = CONSTANTS.DOMAIN) -> str:
    base = CONSTANTS.REST_URL if domain == CONSTANTS.DOMAIN else CONSTANTS.TESTNET_REST_URL
    return f"{base}{path_url}"


def private_rest_url(path_url: str, domain: str = CONSTANTS.DOMAIN) -> str:
    return public_rest_url(path_url, domain)


def auth_rest_url(domain: str = CONSTANTS.DOMAIN) -> str:
    base = CONSTANTS.REST_URL if domain == CONSTANTS.DOMAIN else CONSTANTS.TESTNET_REST_URL
    return f"{base}{CONSTANTS.AUTH_PATH}"


def ws_url(domain: str = CONSTANTS.DOMAIN, private: bool = False) -> str:
    if private:
        return CONSTANTS.TRADES_WS_URL if domain == CONSTANTS.DOMAIN else CONSTANTS.TESTNET_TRADES_WS_URL
    return CONSTANTS.WS_URL if domain == CONSTANTS.DOMAIN else CONSTANTS.TESTNET_WS_URL


def build_api_factory(
    throttler: Optional[AsyncThrottler] = None,
    time_synchronizer: Optional[TimeSynchronizer] = None,
    domain: str = CONSTANTS.DOMAIN,
    time_provider: Optional[Callable] = None,
    auth: Optional[AuthBase] = None,
) -> WebAssistantsFactory:
    throttler = throttler or create_throttler()
    return WebAssistantsFactory(
        throttler=throttler,
        auth=auth,
    )


def build_api_factory_without_time_synchronizer_pre_processor(
    throttler: Optional[AsyncThrottler] = None,
) -> WebAssistantsFactory:
    throttler = throttler or create_throttler()
    return WebAssistantsFactory(throttler=throttler)


def create_throttler() -> AsyncThrottler:
    return AsyncThrottler(CONSTANTS.RATE_LIMITS)


def grvt_symbol_to_trading_pair(instrument: str) -> str:
    """Convert GRVT instrument name (e.g. BTC_USDT_Perp) to Hummingbot pair (BTC-USDT)."""
    # GRVT format: BASE_QUOTE_Perp or BASE_QUOTE_Perp@expiry
    parts = instrument.split("_")
    if len(parts) >= 2:
        return f"{parts[0]}-{parts[1]}"
    return instrument


def trading_pair_to_grvt_symbol(trading_pair: str) -> str:
    """Convert Hummingbot pair (BTC-USDT) to GRVT perpetual instrument (BTC_USDT_Perp)."""
    base, quote = trading_pair.split("-")
    return f"{base}_{quote}_Perp"
