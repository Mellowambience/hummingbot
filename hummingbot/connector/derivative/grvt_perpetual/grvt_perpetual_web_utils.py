"""
Web utility helpers for the GRVT Perpetual connector.
"""
from typing import Any, Callable, Dict, Optional

from hummingbot.connector.derivative.grvt_perpetual import grvt_perpetual_constants as CONSTANTS
from hummingbot.core.api_throttler.async_throttler import AsyncThrottler
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.connections.data_types import RESTMethod


def public_rest_url(path_url: str, domain: str = CONSTANTS.DEFAULT_DOMAIN) -> str:
    """Return full public REST URL (market data subdomain)."""
    base = CONSTANTS.MARKET_DATA_REST_URLS[domain]
    return f"{base}{path_url}"


def private_rest_url(path_url: str, domain: str = CONSTANTS.DEFAULT_DOMAIN) -> str:
    """Return full private REST URL (edge subdomain)."""
    base = CONSTANTS.REST_URLS[domain]
    return f"{base}{path_url}"


def auth_rest_url(domain: str = CONSTANTS.DEFAULT_DOMAIN) -> str:
    """Return the auth (login) endpoint URL."""
    base = CONSTANTS.REST_URLS[domain]
    return f"{base}{CONSTANTS.AUTH_PATH}"


def build_api_factory(
    throttler: Optional[AsyncThrottler] = None,
    auth=None,
    domain: str = CONSTANTS.DEFAULT_DOMAIN,
) -> WebAssistantsFactory:
    throttler = throttler or create_throttler()
    api_factory = WebAssistantsFactory(
        throttler=throttler,
        auth=auth,
    )
    return api_factory


def create_throttler(trading_pairs=None) -> AsyncThrottler:
    return AsyncThrottler(CONSTANTS.RATE_LIMITS)


def instrument_to_trading_pair(instrument: str) -> str:
    """
    Convert GRVT instrument name to Hummingbot trading pair.
    e.g. BTC_USDT_Perp -> BTC-USDT
    """
    parts = instrument.split("_")
    if len(parts) >= 2:
        return f"{parts[0]}-{parts[1]}"
    return instrument


def trading_pair_to_instrument(trading_pair: str) -> str:
    """
    Convert Hummingbot trading pair to GRVT instrument name.
    e.g. BTC-USDT -> BTC_USDT_Perp
    """
    base, quote = trading_pair.split("-")
    return f"{base}_{quote}_{CONSTANTS.PERP_SUFFIX}"
