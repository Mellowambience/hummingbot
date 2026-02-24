from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from pydantic import Field, SecretStr

from hummingbot.client.config.config_data_types import BaseConnectorConfigMap, ClientFieldData
from hummingbot.connector.derivative.grvt_perpetual import grvt_perpetual_constants as CONSTANTS
from hummingbot.core.data_type.trade_fee import TradeFeeSchema

DEFAULT_FEES = TradeFeeSchema(
    maker_percent_fee_decimal=Decimal("0.0002"),
    taker_percent_fee_decimal=Decimal("0.0005"),
)

CENTRALIZED = True
EXAMPLE_PAIR = "BTC-USDT"


def is_exchange_information_valid(exchange_info: Dict[str, Any]) -> bool:
    """Return True if the instrument is a live perpetual."""
    return (
        exchange_info.get("instrument_type") == CONSTANTS.INSTRUMENT_KIND_PERPETUAL
        and exchange_info.get("is_active", False)
    )


class GrvtPerpetualConfigMap(BaseConnectorConfigMap):
    connector: str = Field(default="grvt_perpetual", client_data=None)
    grvt_api_key: SecretStr = Field(
        default=...,
        client_data=ClientFieldData(
            prompt=lambda cm: "Enter your GRVT API key",
            is_secure=True,
            is_connect_key=True,
            prompt_on_new=True,
        ),
    )
    grvt_api_secret: SecretStr = Field(
        default=...,
        client_data=ClientFieldData(
            prompt=lambda cm: "Enter your GRVT Ethereum private key (for order signing)",
            is_secure=True,
            is_connect_key=True,
            prompt_on_new=True,
        ),
    )
    grvt_sub_account_id: SecretStr = Field(
        default=...,
        client_data=ClientFieldData(
            prompt=lambda cm: "Enter your GRVT Sub-Account ID",
            is_secure=True,
            is_connect_key=True,
            prompt_on_new=True,
        ),
    )

    class Config:
        title = "grvt_perpetual"


KEYS = GrvtPerpetualConfigMap.construct()

OTHER_DOMAINS = [CONSTANTS.TESTNET_DOMAIN]
OTHER_DOMAINS_PARAMETER = {CONSTANTS.TESTNET_DOMAIN: "testnet"}
OTHER_DOMAINS_EXAMPLE_PAIR = {CONSTANTS.TESTNET_DOMAIN: "BTC-USDT"}
OTHER_DOMAINS_DEFAULT_FEES = {CONSTANTS.TESTNET_DOMAIN: DEFAULT_FEES}


class GrvtPerpetualTestnetConfigMap(BaseConnectorConfigMap):
    connector: str = Field(default="grvt_perpetual_testnet", client_data=None)
    grvt_api_key: SecretStr = Field(
        default=...,
        client_data=ClientFieldData(
            prompt=lambda cm: "Enter your GRVT testnet API key",
            is_secure=True,
            is_connect_key=True,
            prompt_on_new=True,
        ),
    )
    grvt_api_secret: SecretStr = Field(
        default=...,
        client_data=ClientFieldData(
            prompt=lambda cm: "Enter your GRVT Ethereum private key (for order signing)",
            is_secure=True,
            is_connect_key=True,
            prompt_on_new=True,
        ),
    )
    grvt_sub_account_id: SecretStr = Field(
        default=...,
        client_data=ClientFieldData(
            prompt=lambda cm: "Enter your GRVT testnet Sub-Account ID",
            is_secure=True,
            is_connect_key=True,
            prompt_on_new=True,
        ),
    )

    class Config:
        title = "grvt_perpetual_testnet"


OTHER_DOMAINS_KEYS = {CONSTANTS.TESTNET_DOMAIN: GrvtPerpetualTestnetConfigMap.construct()}
