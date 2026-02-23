"""
Main exchange class for the GRVT Perpetual connector.
Implements PerpetualDerivativePyBase for Hummingbot v2.1+ connector standard.
"""
import asyncio
import logging
from decimal import Decimal
from typing import Any, AsyncIterable, Dict, List, Optional, Tuple

from hummingbot.connector.derivative.grvt_perpetual import grvt_perpetual_constants as CONSTANTS
from hummingbot.connector.derivative.grvt_perpetual.grvt_perpetual_api_order_book_data_source import (
    GrvtPerpetualAPIOrderBookDataSource,
)
from hummingbot.connector.derivative.grvt_perpetual.grvt_perpetual_api_user_stream_data_source import (
    GrvtPerpetualAPIUserStreamDataSource,
)
from hummingbot.connector.derivative.grvt_perpetual.grvt_perpetual_auth import GrvtPerpetualAuth
from hummingbot.connector.derivative.grvt_perpetual.grvt_perpetual_web_utils import (
    build_api_factory,
    private_rest_url,
    public_rest_url,
    trading_pair_to_instrument,
    instrument_to_trading_pair,
)
from hummingbot.connector.perpetual_derivative_py_base import PerpetualDerivativePyBase
from hummingbot.connector.time_synchronizer import TimeSynchronizer
from hummingbot.connector.trading_rule import TradingRule
from hummingbot.core.data_type.common import OrderType, PositionAction, PositionMode, TradeType
from hummingbot.core.data_type.in_flight_order import InFlightOrder, OrderState, OrderUpdate, TradeUpdate
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.data_type.trade_fee import TradeFeeBase
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.core.web_assistant.connections.data_types import RESTMethod


class GrvtPerpetualDerivative(PerpetualDerivativePyBase):
    """
    GRVT Perpetual connector — REST + WebSocket, v2.1+ standard.
    API Docs: https://api-docs.grvt.io
    """
    UPDATE_ORDER_STATUS_MIN_INTERVAL = 10.0
    TRADING_PAIR_SPLITTER = CONSTANTS.TRADING_PAIR_SPLITTER

    web_utils = None  # set at module import in conftest.yml

    def __init__(
        self,
        client_config_map: Any,
        grvt_perpetual_api_key: str,
        grvt_perpetual_sub_account_id: str,
        trading_pairs: Optional[List[str]] = None,
        trading_required: bool = True,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
    ):
        self._api_key = grvt_perpetual_api_key
        self._sub_account_id = grvt_perpetual_sub_account_id
        self._domain = domain
        self._trading_pairs = trading_pairs or []
        self._trading_required = trading_required

        self._time_synchronizer = TimeSynchronizer()
        self._auth = GrvtPerpetualAuth(
            api_key=grvt_perpetual_api_key,
            sub_account_id=grvt_perpetual_sub_account_id,
            time_provider=self._time_synchronizer,
            domain=domain,
        )
        self._api_factory = build_api_factory(auth=self._auth, domain=domain)
        super().__init__(client_config_map)

    @property
    def name(self) -> str:
        return "grvt_perpetual" if self._domain == CONSTANTS.DEFAULT_DOMAIN else f"grvt_perpetual_{self._domain}"

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
    def client_order_id_max_length(self) -> int:
        return 64

    @property
    def client_order_id_prefix(self) -> str:
        return "hbot-grvt-"

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

    # ── Auth / Login ──────────────────────────────────────────────────────────
    async def _authenticate(self):
        """Perform API key login and store session cookie."""
        from hummingbot.connector.derivative.grvt_perpetual.grvt_perpetual_web_utils import auth_rest_url
        rest = await self._api_factory.get_rest_assistant()
        resp = await rest.execute_request(
            url=auth_rest_url(self._domain),
            data=self._auth.get_auth_payload(),
            method=RESTMethod.POST,
            headers={"Content-Type": "application/json"},
            return_err=True,
        )
        cookie = resp.get("cookie", "")
        account_id = resp.get("account_id", self._sub_account_id)
        if cookie:
            self._auth.session_cookie = cookie
            self._auth.account_id = account_id

    # ── Data Sources ───────────────────────────────────────────────────────────
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
            domain=self._domain,
        )

    # ── Trading Rules ──────────────────────────────────────────────────────────
    async def _format_trading_rules(self, raw_trading_pair_info: Dict) -> List[TradingRule]:
        trading_rules = []
        instruments = raw_trading_pair_info.get("result", {}).get("instruments", [])
        for inst in instruments:
            try:
                instrument = inst.get("instrument", "")
                trading_pair = instrument_to_trading_pair(instrument)
                if "_Perp" not in instrument:
                    continue
                base_decimals = int(inst.get("base_decimals", 4))
                quote_decimals = int(inst.get("quote_decimals", 2))
                min_size = Decimal(str(inst.get("min_size", "0.001")))
                tick_size = Decimal(str(inst.get("tick_size", "0.01")))
                trading_rules.append(TradingRule(
                    trading_pair=trading_pair,
                    min_order_size=min_size,
                    min_price_increment=tick_size,
                    min_base_amount_increment=Decimal(f"1e-{base_decimals}"),
                    min_notional_size=Decimal("1"),
                    supports_limit_orders=True,
                    supports_market_orders=True,
                ))
            except Exception as e:
                self.logger().warning(f"Error parsing trading rule for {inst}: {e}")
        return trading_rules

    # ── Order Management ───────────────────────────────────────────────────────
    async def _place_order(
        self,
        order_id: str,
        trading_pair: str,
        amount: Decimal,
        trade_type: TradeType,
        order_type: OrderType,
        price: Decimal,
        position_action: PositionAction = PositionAction.OPEN,
        **kwargs,
    ) -> Tuple[str, float]:
        instrument = trading_pair_to_instrument(trading_pair)
        side = 1 if trade_type == TradeType.BUY else 2  # 1=BID 2=ASK
        order_payload: Dict[str, Any] = {
            "instrument": instrument,
            "client_order_id": order_id,
            "type": 2 if order_type == OrderType.LIMIT else 1,  # 1=MARKET 2=LIMIT
            "side": side,
            "size": str(amount),
        }
        if order_type == OrderType.LIMIT:
            order_payload["limit_price"] = str(price)

        rest = await self._api_factory.get_rest_assistant()
        resp = await rest.execute_request(
            url=private_rest_url(CONSTANTS.CREATE_ORDER_PATH, self._domain),
            data=order_payload,
            method=RESTMethod.POST,
            throttler_limit_id=CONSTANTS.CREATE_ORDER_PATH,
        )
        exchange_order_id = resp.get("result", {}).get("order_id", order_id)
        ts = resp.get("result", {}).get("create_time", asyncio.get_event_loop().time())
        return exchange_order_id, float(ts)

    async def _place_cancel(self, order_id: str, tracked_order: InFlightOrder):
        rest = await self._api_factory.get_rest_assistant()
        await rest.execute_request(
            url=private_rest_url(CONSTANTS.CANCEL_ORDER_PATH, self._domain),
            data={"order_id": tracked_order.exchange_order_id or order_id},
            method=RESTMethod.POST,
            throttler_limit_id=CONSTANTS.CANCEL_ORDER_PATH,
        )

    # ── Position / Account ─────────────────────────────────────────────────────
    async def _get_position_mode(self) -> Optional[PositionMode]:
        return PositionMode.ONEWAY

    async def _trading_pair_position_mode_set(self, mode: PositionMode, trading_pair: str) -> Tuple[bool, str]:
        if mode != PositionMode.ONEWAY:
            return False, "GRVT only supports one-way (net) position mode."
        return True, ""

    async def _set_leverage(self, trading_pair: str, leverage: int = 1):
        # GRVT leverage is per sub-account, not per instrument
        pass

    async def _fetch_last_fee_payment(self, trading_pair: str) -> Tuple[int, Decimal, Decimal]:
        instrument = trading_pair_to_instrument(trading_pair)
        rest = await self._api_factory.get_rest_assistant()
        resp = await rest.execute_request(
            url=private_rest_url(CONSTANTS.FUNDING_HISTORY_PATH, self._domain),
            data={"instrument": instrument, "limit": 1},
            method=RESTMethod.POST,
            throttler_limit_id=CONSTANTS.FUNDING_HISTORY_PATH,
        )
        entries = resp.get("result", {}).get("entries", [])
        if entries:
            e = entries[0]
            ts = int(int(e.get("event_time", 0)) / 1e9)
            rate = Decimal(str(e.get("funding_rate", 0)))
            payment = Decimal(str(e.get("total_pnl", 0)))
            return ts, rate, payment
        return 0, Decimal("0"), Decimal("0")

    # ── Order Status Sync ──────────────────────────────────────────────────────
    async def _all_trade_updates_for_order(self, order: InFlightOrder) -> List[TradeUpdate]:
        return []

    async def _request_order_status(self, tracked_order: InFlightOrder) -> OrderUpdate:
        rest = await self._api_factory.get_rest_assistant()
        resp = await rest.execute_request(
            url=private_rest_url(CONSTANTS.GET_ORDER_PATH, self._domain),
            data={"order_id": tracked_order.exchange_order_id},
            method=RESTMethod.POST,
            throttler_limit_id=CONSTANTS.OPEN_ORDERS_PATH,
        )
        result = resp.get("result", {}).get("order", {})
        status_map = {
            "PENDING": OrderState.PENDING_CREATE,
            "OPEN": OrderState.OPEN,
            "FILLED": OrderState.FILLED,
            "CANCELLED": OrderState.CANCELED,
            "REJECTED": OrderState.FAILED,
        }
        new_state = status_map.get(result.get("status", "OPEN"), OrderState.OPEN)
        return OrderUpdate(
            client_order_id=tracked_order.client_order_id,
            exchange_order_id=str(result.get("order_id", tracked_order.exchange_order_id)),
            trading_pair=tracked_order.trading_pair,
            update_timestamp=int(result.get("update_time", 0)) / 1e9,
            new_state=new_state,
        )

    # ── User stream parsing ────────────────────────────────────────────────────
    async def _user_stream_event_listener(self):
        async for event_message in self._iter_user_event_queue():
            try:
                stream = event_message.get("stream", "")
                feed = event_message.get("feed", {})
                if stream == CONSTANTS.WS_ORDERS_CHANNEL:
                    await self._process_order_event(feed)
                elif stream == CONSTANTS.WS_FILLS_CHANNEL:
                    await self._process_fill_event(feed)
                elif stream == CONSTANTS.WS_POSITIONS_CHANNEL:
                    await self._process_position_event(feed)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger().error(f"Error processing user stream event: {e}", exc_info=True)

    async def _process_order_event(self, feed: Dict):
        status_map = {
            "PENDING": OrderState.PENDING_CREATE,
            "OPEN": OrderState.OPEN,
            "FILLED": OrderState.FILLED,
            "CANCELLED": OrderState.CANCELED,
            "REJECTED": OrderState.FAILED,
        }
        new_state = status_map.get(feed.get("status", "OPEN"), OrderState.OPEN)
        client_order_id = feed.get("client_order_id", "")
        exchange_order_id = str(feed.get("order_id", ""))
        instrument = feed.get("instrument", "")
        trading_pair = instrument_to_trading_pair(instrument)
        ts = int(feed.get("update_time", 0)) / 1e9

        order_update = OrderUpdate(
            client_order_id=client_order_id,
            exchange_order_id=exchange_order_id,
            trading_pair=trading_pair,
            update_timestamp=ts,
            new_state=new_state,
        )
        self._order_tracker.process_order_update(order_update)

    async def _process_fill_event(self, feed: Dict):
        pass  # TradeUpdate processing would go here

    async def _process_position_event(self, feed: Dict):
        pass  # Position update processing would go here

    def _get_fee(self, base_currency: str, quote_currency: str, order_type: OrderType,
                 order_side: TradeType, amount: Decimal, price: Decimal = Decimal("0"),
                 is_maker: Optional[bool] = None) -> TradeFeeBase:
        from hummingbot.core.data_type.trade_fee import AddedToCostTradeFee, TokenAmount
        # GRVT: maker rebate -0.02%, taker 0.05%
        if is_maker:
            return AddedToCostTradeFee(flat_fees=[TokenAmount(quote_currency, amount * price * Decimal("-0.0002"))])
        return AddedToCostTradeFee(flat_fees=[TokenAmount(quote_currency, amount * price * Decimal("0.0005"))])

    async def _update_balances(self):
        rest = await self._api_factory.get_rest_assistant()
        try:
            resp = await rest.execute_request(
                url=private_rest_url(CONSTANTS.SUB_ACCOUNTS_PATH, self._domain),
                data={"sub_account_id": self._sub_account_id},
                method=RESTMethod.POST,
                throttler_limit_id=CONSTANTS.POSITIONS_PATH,
            )
            result = resp.get("result", {}).get("summary", {})
            # Parse spot balances from the sub-account summary
            total_equity = Decimal(str(result.get("total_equity", "0")))
            available = Decimal(str(result.get("available_balance", "0")))
            self._account_available_balances["USDT"] = available
            self._account_balances["USDT"] = total_equity
        except Exception as e:
            self.logger().warning(f"Error updating GRVT balances: {e}")
