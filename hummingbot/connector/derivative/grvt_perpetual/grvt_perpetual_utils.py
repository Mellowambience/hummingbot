"""
Config map and utility functions for the GRVT Perpetual connector.
"""
from decimal import Decimal
from typing import Dict

from hummingbot.client.config.config_methods import using_exchange
from hummingbot.client.config.config_var import ConfigVar
from hummingbot.connector.derivative.grvt_perpetual import grvt_perpetual_constants as CONSTANTS

CENTRALIZED = True
EXAMPLE_PAIR = "BTC-USDT"

KEYS: Dict[str, ConfigVar] = {
    "grvt_perpetual_api_key": ConfigVar(
        key="grvt_perpetual_api_key",
        prompt="Enter your GRVT API key >>> ",
        required_if=using_exchange("grvt_perpetual"),
        is_secure=True,
        is_connector_specific_config=True,
    ),
    "grvt_perpetual_sub_account_id": ConfigVar(
        key="grvt_perpetual_sub_account_id",
        prompt="Enter your GRVT sub-account ID >>> ",
        required_if=using_exchange("grvt_perpetual"),
        is_secure=False,
        is_connector_specific_config=True,
    ),
}

OTHER_DOMAINS: Dict[str, str] = {
    "grvt_perpetual_testnet": "testnet",
}

OTHER_DOMAINS_PARAMETER: Dict[str, str] = {
    "grvt_perpetual_testnet": "testnet",
}

OTHER_DOMAINS_EXAMPLE_PAIR: Dict[str, str] = {
    "grvt_perpetual_testnet": "BTC-USDT",
}

OTHER_DOMAINS_DEFAULT_FEES: Dict[str, Dict] = {
    "grvt_perpetual_testnet": {"maker": Decimal("-0.0002"), "taker": Decimal("0.0005")},
}
