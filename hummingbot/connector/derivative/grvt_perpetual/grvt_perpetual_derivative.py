import asyncio
import time
from decimal import Decimal
from typing import Any, AsyncIterable, Dict, List, Optional, Tuple

from bidict import bidict

from hummingbot.connector.constants import s_decimal_NaN
from hummingbot.connector.derivative.grvt_perpetual import (
    grvt_perpetual_constants as CONSTANTS,
    grvt_perpetual_web_utils as web_utils,
)
from hummingbot.connector.derivative.grvt_perpetual.grvt_perpetual_api_order_book_data_source import (
    GrvtPerpetualAPIOrderBookDataSource,
)
from hummingbot.connector.derivative.grvt_perpetual.grvt_perpetual_api_user_stream_data_source import (
    GrvtPerpetualAPIUserStreamDataSource,
)
from hummingbot.connector.derivative.grvt_perpetual.grvt_perpetual_auth import GrvtPerpetualAuth
from hummingbot.connector.derivative.grvt_perpetual.grvt_perpetual_web_utils import (
    private_rest_url,
    public_rest_url,
    trading_pair_to_grvt_symbol,
    grvt_symbol_to_trading_pair,
)
from hummingbot.connector.perpetual_derivative_py_base import PerpetualDerivativePyBase
from hummingbot.connector.trading_rule import TradingRule
from hummingbot.connector.utils import combine_to_hb_trading_pair
from hummingbot.core.api_throttler.async_throttler import AsyncThrottler
from hummingbot.core.data_type.cancellation_result import CancellationResult
from hummingbot.core.data_type.common import OrderType, PositionAction, PositionMode, PositionSide, TradeType
from hummingbot.core.data_type.funding_info import FundingInfo
from hummingbot.core.data_type.in_flight_order import InFlightOrder, OrderUpdate, TradeUpdate
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.data_type.trade_fee import TokenAmount, TradeFeeBase
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.utils.async_utils import safe_ensure_future, safe_gather
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, RESTRequest
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory


class GrvtPerpetualDerivative(PerpetualDerivativePyBase):
    """
    GRVT Perpetual connector implementing the Hummingbot v2.1+ PerpetualDerivativePyBase interface.

    Authentication: Session cookie via API key login + EIP-712 order signing.
    Markets: Perpetual futures on GRVT L2 (ZKSync-based chain).
    """

    SHORT_POLL_INTERVAL = 5.0
    UPDATE_ORDER_STATUS_MIN_INTERVAL = 10.0
    LONG_POLL_INTERVAL = 120.0

    def __init__(
        self,
        client_config_map: Any,
        grvt_api_key: str,
        grvt_api_secret: str,
        grvt_sub_account_id: str,
        trading_pairs: Optional[List[str]] = None,
        trading_required: bool = True,
        domain: str = CONSTANTS.DOMAIN,
    ):
        self._domain = domain
        self._trading_required = trading_required
        self._auth = GrvtPerpetualAuth(
            api_key=grvt_api_key,
            api_secret=grvt_api_secret,
            sub_account_id=grvt_sub_account_id,
            domain=domain,
        )
        self._throttler = AsyncThrottler(CONSTANTS.RATE_LIMITS)
        self._api_factory = web_utils.build_api_factory(
            throttler=self._throttler,
            domain=domain,
            auth=self._auth,
        )
        super().__init__(client_config_map)
        self._trading_pairs = trading_pairs or []
        self._instrument_info: Dict[str, Any] = {}

    @property
    def name(self) -> str:
        return CONSTANTS.EXCHANGE_NAME if self._domain == CONSTANTS.DOMAIN else CONSTANTS.TESTNET_DOMAIN

    @property
    def authenticator(self) -> GrvtPerpetualAuth:
        return self._auth

    @property
    def rate_limits_rules(self):
        return CONSTANTS.RATE_LIMITS

    @property
    def domain(self) -> str:
        return self._domain

    @property
    def client_order_id_max_length(self) -> Optional[int]:
        return CONSTANTS.MAX_ORDER_ID_LEN

    @property
    def client_order_id_prefix(self) -> str:
        return CONSTANTS.BROKER_ID

    @property
    def trading_rules_request_path(self) -> str:
        return CONSTANTS.INSTRUMENTS_PATH

    @property
    def trading_pairs_request_path(self) -> str:
        return CONSTANTS.INSTRUMENTS_PATH

    @property
    def check_network_request_path(self) -> str:
        return CONSTANTS.INSTRUMENTS_PATH

    @property
    def trading_pairs(self) -> List[str]:
        return self._trading_pairs

    @property
    def is_cancel_request_in_exchange_synchronous(self) -> bool:
        return False

    @property
    def is_trading_required(self) -> bool:
        return self._trading_required

    @property
    def funding_fee_poll_interval(self) -> int:
        return 120

    # =================== Auth session management ===================

    async def _ensure_authenticated(self) -> None:
        """Ensure session cookie is valid; re-authenticate if needed."""
        if self._auth.is_session_valid:
            return
        rest = await self._api_factory.get_rest_assistant()
        url = web_utils.auth_rest_url(self._domain)
        request = RESTRequest(
            method=RESTMethod.POST,
            url=url,
            data=self._auth.get_auth_login_payload(),
            is_auth_required=False,
            headers={"Content-Type": "application/json", "Cookie": "rm=true;"},
        )
        try:
            response = await rest.call(request=request)
            # Cookie is in response headers; account ID in body
            raw = getattr(response, "_aiohttp_response", None)
            cookie_val = ""
            account_id = ""
            if raw is not None:
                set_cookie = raw.headers.get("set-cookie", "")
                for part in set_cookie.split(";"):
                    if "gravity=" in part:
                        cookie_val = part.strip().split("gravity=")[-1]
                        break
                account_id = raw.headers.get("x-grvt-account-id", "")
            if not cookie_val:
                # Fallback: try JSON body
                data = await response.json()
                account_id = data.get("account_id", account_id)
            if cookie_val or account_id:
                self._auth.set_session(cookie_val, account_id)
        except Exception as e:
            self.logger().warning(f"GRVT authentication failed: {e}")

    # =================== Trading rules ===================

    async def _format_trading_rules(self, exchange_info_dict: Dict[str, Any]) -> List[TradingRule]:
        rules = []
        instruments = exchange_info_dict.get("result", []) or []
        for inst in instruments:
            if not web_utils.is_exchange_information_valid(inst):
                continue
            try:
                instrument_name = inst["instrument"]
                trading_pair = grvt_symbol_to_trading_pair(instrument_name)
                base_asset = inst.get("base_asset", "")
                quote_asset = inst.get("quote_asset", "USDT")

                # GRVT uses string decimals; convert to Decimal
                min_order_size = Decimal(str(inst.get("min_size", "0.001")))
                tick_size = Decimal(str(inst.get("tick_size", "0.01")))
                step_size = Decimal(str(inst.get("min_size", "0.001")))

                rules.append(TradingRule(
                    trading_pair=trading_pair,
                    min_order_size=min_order_size,
                    min_price_increment=tick_size,
                    min_base_amount_increment=step_size,
                    min_notional_size=Decimal("10"),
                    buy_order_collateral_token=quote_asset,
                    sell_order_collateral_token=quote_asset,
                ))
            except Exception as e:
                self.logger().warning(f"Could not parse trading rule for {inst.get('instrument', '?')}: {e}")
        return rules

    async def _update_trading_fees(self) -> None:
        pass  # Use DEFAULT_FEES from utils.py

    # =================== Order placement ===================

    async def _place_order(
        self,
        order_id: str,
        trading_pair: str,
        amount: Decimal,
        trade_type: TradeType,
        order_type: OrderType,
        price: Decimal,
        position_action: PositionAction = PositionAction.NIL,
        **kwargs,
    ) -> Tuple[str, float]:
        await self._ensure_authenticated()

        instrument = trading_pair_to_grvt_symbol(trading_pair)
        is_buying = trade_type == TradeType.BUY

        # Use market order if OrderType.MARKET
        if order_type == OrderType.MARKET:
            limit_price = "0"
            tif = CONSTANTS.TIME_IN_FORCE_IOC
        else:
            limit_price = str(price)
            tif = CONSTANTS.TIME_IN_FORCE_GTC

        nonce = int(time.time() * 1000) % (2**32)
        expiry = int(time.time() + 3600) * 1_000_000_000  # 1 hour from now, nanoseconds

        signed_order = self._auth.sign_order(
            instrument=instrument,
            is_buying=is_buying,
            limit_price=limit_price,
            quantity=str(amount),
            expiry=expiry,
            nonce=nonce,
            time_in_force=tif,
        )

        rest = await self._api_factory.get_rest_assistant()
        url = private_rest_url(CONSTANTS.CREATE_ORDER_PATH, self._domain)
        request = RESTRequest(
            method=RESTMethod.POST,
            url=url,
            data=signed_order,
            is_auth_required=True,
        )
        response = await rest.call(request=request)
        data = await response.json()
        result = data.get("result", {})
        exchange_order_id = str(result.get("order_id", ""))
        return exchange_order_id, self.current_timestamp

    async def _place_cancel(self, order_id: str, tracked_order: InFlightOrder) -> bool:
        await self._ensure_authenticated()
        rest = await self._api_factory.get_rest_assistant()
        url = private_rest_url(CONSTANTS.CANCEL_ORDER_PATH, self._domain)
        request = RESTRequest(
            method=RESTMethod.POST,
            url=url,
            data={
                "sub_account_id": self._auth.sub_account_id,
                "order_id": tracked_order.exchange_order_id,
            },
            is_auth_required=True,
        )
        response = await rest.call(request=request)
        data = await response.json()
        return data.get("result") is not None

    async def cancel_all(self, timeout_seconds: float) -> List[CancellationResult]:
        incomplete_orders = [o for o in self.in_flight_orders.values() if not o.is_done]
        tasks = [self._execute_cancel(o.client_order_id, o.trading_pair) for o in incomplete_orders]
        results = await safe_gather(*tasks, return_exceptions=True)
        return [
            CancellationResult(o.client_order_id, not isinstance(r, Exception))
            for o, r in zip(incomplete_orders, results)
        ]

    # =================== Status updates ===================

    async def _get_last_traded_price(self, trading_pair: str) -> float:
        prices = await self._order_book_data_source.get_last_traded_prices([trading_pair])
        return prices.get(trading_pair, 0.0)

    async def _update_balances(self) -> None:
        await self._ensure_authenticated()
        rest = await self._api_factory.get_rest_assistant()
        url = private_rest_url(CONSTANTS.GET_BALANCES_PATH, self._domain)
        request = RESTRequest(
            method=RESTMethod.POST,
            url=url,
            data={"sub_account_id": self._auth.sub_account_id},
            is_auth_required=True,
        )
        response = await rest.call(request=request)
        data = await response.json()
        result = data.get("result", {})

        self._account_available_balances.clear()
        self._account_balances.clear()

        # GRVT account summary: total_equity and spot_balances
        spot_balances = result.get("spot_balances", [])
        for bal in spot_balances:
            currency = bal.get("currency", "USDT")
            total = Decimal(str(bal.get("total_balance", 0)))
            available = Decimal(str(bal.get("available_balance", 0)))
            self._account_balances[currency] = total
            self._account_available_balances[currency] = available

        # Also track total equity as USDT if no spot balance
        if not spot_balances:
            equity = Decimal(str(result.get("total_equity", 0)))
            self._account_balances["USDT"] = equity
            self._account_available_balances["USDT"] = equity

    async def _request_order_status(self, tracked_order: InFlightOrder) -> OrderUpdate:
        await self._ensure_authenticated()
        rest = await self._api_factory.get_rest_assistant()
        url = private_rest_url(CONSTANTS.GET_ORDER_PATH, self._domain)
        request = RESTRequest(
            method=RESTMethod.POST,
            url=url,
            data={
                "sub_account_id": self._auth.sub_account_id,
                "order_id": tracked_order.exchange_order_id,
            },
            is_auth_required=True,
        )
        response = await rest.call(request=request)
        data = await response.json()
        result = data.get("result", {})

        grvt_status = result.get("status", "OPEN")
        new_state = CONSTANTS.ORDER_STATE_MAP.get(grvt_status, tracked_order.current_state)

        return OrderUpdate(
            trading_pair=tracked_order.trading_pair,
            update_timestamp=self.current_timestamp,
            new_state=new_state,
            client_order_id=tracked_order.client_order_id,
            exchange_order_id=str(result.get("order_id", tracked_order.exchange_order_id)),
        )

    async def _all_trade_updates_for_order(self, order: InFlightOrder) -> List[TradeUpdate]:
        await self._ensure_authenticated()
        rest = await self._api_factory.get_rest_assistant()
        url = private_rest_url(CONSTANTS.GET_TRADE_HISTORY_PATH, self._domain)
        request = RESTRequest(
            method=RESTMethod.POST,
            url=url,
            data={
                "sub_account_id": self._auth.sub_account_id,
                "order_id": order.exchange_order_id,
            },
            is_auth_required=True,
        )
        response = await rest.call(request=request)
        data = await response.json()
        trades = data.get("result", []) or []
        updates = []
        for trade in trades:
            instrument = trade.get("instrument", "")
            trading_pair = grvt_symbol_to_trading_pair(instrument) if instrument else order.trading_pair
            fee_amount = Decimal(str(trade.get("fee", "0")))
            fee = TradeFeeBase.new_perpetual_fee(
                fee_schema=self.trade_fee_schema(),
                position_action=PositionAction.OPEN,
                percent_token="USDT",
                flat_fees=[TokenAmount(amount=fee_amount, token="USDT")],
            )
            updates.append(TradeUpdate(
                trade_id=str(trade.get("event_time", "")),
                client_order_id=order.client_order_id,
                exchange_order_id=str(trade.get("order_id", "")),
                trading_pair=trading_pair,
                fee=fee,
                fill_base_amount=Decimal(str(trade.get("size", "0"))),
                fill_quote_amount=Decimal(str(trade.get("size", "0"))) * Decimal(str(trade.get("price", "0"))),
                fill_price=Decimal(str(trade.get("price", "0"))),
                fill_timestamp=int(trade.get("event_time", 0)) / 1e9,
            ))
        return updates

    # =================== Position management ===================

    async def _update_positions(self) -> None:
        await self._ensure_authenticated()
        rest = await self._api_factory.get_rest_assistant()
        url = private_rest_url(CONSTANTS.GET_POSITIONS_PATH, self._domain)
        request = RESTRequest(
            method=RESTMethod.POST,
            url=url,
            data={"sub_account_id": self._auth.sub_account_id},
            is_auth_required=True,
        )
        response = await rest.call(request=request)
        data = await response.json()
        positions = data.get("result", []) or []

        for pos_data in positions:
            instrument = pos_data.get("instrument", "")
            if not instrument:
                continue
            trading_pair = grvt_symbol_to_trading_pair(instrument)
            size = Decimal(str(pos_data.get("net_size", "0")))
            entry_price = Decimal(str(pos_data.get("avg_entry_price", "0")))
            leverage = Decimal(str(pos_data.get("leverage", "1")))
            unrealized_pnl = Decimal(str(pos_data.get("unrealized_pnl", "0")))
            side = PositionSide.LONG if size >= 0 else PositionSide.SHORT

            pos_key = self._perpetual_trading.position_key(trading_pair, side)
            if size == Decimal("0"):
                self._perpetual_trading.remove_position(pos_key)
            else:
                position = self._perpetual_trading.get_position(trading_pair, side)
                if position is None:
                    position = self._perpetual_trading.set_position(
                        trading_pair=trading_pair,
                        position_side=side,
                        amount=abs(size),
                        entry_price=entry_price,
                        unrealized_pnl=unrealized_pnl,
                        leverage=leverage,
                    )
                else:
                    position.update_position(
                        position_side=side,
                        amount=abs(size),
                        entry_price=entry_price,
                        unrealized_pnl=unrealized_pnl,
                    )

    async def get_funding_info(self, trading_pair: str) -> FundingInfo:
        return await self._order_book_data_source.get_funding_info(trading_pair)

    async def _get_position_mode(self) -> PositionMode:
        return PositionMode.ONEWAY

    async def _trading_pair_position_mode_set(self, mode: PositionMode, trading_pair: str) -> Tuple[bool, str]:
        if mode == PositionMode.ONEWAY:
            return True, ""
        return False, "GRVT only supports one-way position mode."

    async def _set_trading_pair_leverage(self, trading_pair: str, leverage: int) -> Tuple[bool, str]:
        # GRVT leverage is managed at sub-account level, not per-pair
        return True, ""

    async def _fetch_last_fee_payment(self, trading_pair: str) -> Tuple[int, Decimal, Decimal]:
        await self._ensure_authenticated()
        rest = await self._api_factory.get_rest_assistant()
        url = private_rest_url(CONSTANTS.GET_FUNDING_PAYMENTS_PATH, self._domain)
        request = RESTRequest(
            method=RESTMethod.POST,
            url=url,
            data={
                "sub_account_id": self._auth.sub_account_id,
                "instrument": trading_pair_to_grvt_symbol(trading_pair),
            },
            is_auth_required=True,
        )
        response = await rest.call(request=request)
        data = await response.json()
        results = data.get("result", []) or []

        if not results:
            return 0, s_decimal_NaN, s_decimal_NaN

        latest = results[-1]
        ts = int(latest.get("event_time", 0)) // 1_000_000_000
        rate = Decimal(str(latest.get("funding_rate", "0")))
        payment = Decimal(str(latest.get("payment", "0")))
        return ts, rate, payment

    # =================== WS message processing ===================

    async def _process_user_stream_event(self, event_message: Dict[str, Any]) -> None:
        stream = event_message.get("stream", "")
        feed = event_message.get("feed", {})

        if CONSTANTS.WS_ORDER_STREAM in stream:
            await self._process_order_event(feed)
        elif CONSTANTS.WS_FILLS_STREAM in stream:
            await self._process_fill_event(feed)
        elif CONSTANTS.WS_POSITION_STREAM in stream:
            await self._process_position_event(feed)

    async def _process_order_event(self, data: Dict[str, Any]) -> None:
        order_id = str(data.get("order_id", ""))
        grvt_status = data.get("status", "OPEN")
        new_state = CONSTANTS.ORDER_STATE_MAP.get(grvt_status)
        if not new_state:
            return

        tracked = self._order_tracker.fetch_tracked_order(exchange_order_id=order_id)
        if tracked is None:
            return

        update = OrderUpdate(
            trading_pair=tracked.trading_pair,
            update_timestamp=int(data.get("event_time", time.time() * 1e9)) / 1e9,
            new_state=new_state,
            client_order_id=tracked.client_order_id,
            exchange_order_id=order_id,
        )
        self._order_tracker.process_order_update(update)

    async def _process_fill_event(self, data: Dict[str, Any]) -> None:
        order_id = str(data.get("order_id", ""))
        tracked = self._order_tracker.fetch_tracked_order(exchange_order_id=order_id)
        if tracked is None:
            return

        instrument = data.get("instrument", "")
        trading_pair = grvt_symbol_to_trading_pair(instrument) if instrument else tracked.trading_pair
        fee_amount = Decimal(str(data.get("fee", "0")))
        fee = TradeFeeBase.new_perpetual_fee(
            fee_schema=self.trade_fee_schema(),
            position_action=PositionAction.OPEN,
            percent_token="USDT",
            flat_fees=[TokenAmount(amount=fee_amount, token="USDT")],
        )

        trade_update = TradeUpdate(
            trade_id=str(data.get("event_time", "")),
            client_order_id=tracked.client_order_id,
            exchange_order_id=order_id,
            trading_pair=trading_pair,
            fee=fee,
            fill_base_amount=Decimal(str(data.get("size", "0"))),
            fill_quote_amount=Decimal(str(data.get("size", "0"))) * Decimal(str(data.get("price", "0"))),
            fill_price=Decimal(str(data.get("price", "0"))),
            fill_timestamp=int(data.get("event_time", 0)) / 1e9,
        )
        self._order_tracker.process_trade_update(trade_update)

    async def _process_position_event(self, data: Dict[str, Any]) -> None:
        await self._update_positions()

    # =================== Data source factories ===================

    def _create_web_assistants_factory(self) -> WebAssistantsFactory:
        return self._api_factory

    def _create_order_book_data_source(self) -> OrderBookTrackerDataSource:
        return GrvtPerpetualAPIOrderBookDataSource(
            trading_pairs=self._trading_pairs,
            connector=self,
            api_factory=self._api_factory,
            domain=self._domain,
        )

    def _create_user_stream_data_source(self) -> UserStreamTrackerDataSource:
        return GrvtPerpetualAPIUserStreamDataSource(
            auth=self._auth,
            trading_pairs=self._trading_pairs,
            connector=self,
            api_factory=self._api_factory,
            domain=self._domain,
        )

    # =================== Initialization ===================

    async def _initialize_trading_pair_symbols_from_exchange_info(self, exchange_info: Dict[str, Any]):
        mapping = bidict()
        instruments = exchange_info.get("result", []) or []
        for inst in instruments:
            if inst.get("instrument_type") == CONSTANTS.INSTRUMENT_KIND_PERPETUAL:
                name = inst.get("instrument", "")
                pair = grvt_symbol_to_trading_pair(name)
                mapping[name] = pair
        self._set_trading_pair_symbol_map(mapping)

    async def _get_last_traded_prices(self, trading_pairs: List[str]) -> Dict[str, float]:
        return await self._order_book_data_source.get_last_traded_prices(trading_pairs)

    def supported_order_types(self) -> List[OrderType]:
        return [OrderType.LIMIT, OrderType.MARKET, OrderType.LIMIT_MAKER]

    def supported_position_modes(self) -> List[PositionMode]:
        return [PositionMode.ONEWAY]

    def get_buy_collateral_token(self, trading_pair: str) -> str:
        return "USDT"

    def get_sell_collateral_token(self, trading_pair: str) -> str:
        return "USDT"
