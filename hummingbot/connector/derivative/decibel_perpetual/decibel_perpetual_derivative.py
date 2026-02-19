import asyncio
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from hummingbot.connector.derivative.decibel_perpetual import decibel_perpetual_constants as CONSTANTS
from hummingbot.connector.derivative.decibel_perpetual.decibel_perpetual_api_order_book_data_source import (
    DecibelPerpetualAPIOrderBookDataSource,
)
from hummingbot.connector.derivative.decibel_perpetual.decibel_perpetual_api_user_stream_data_source import (
    DecibelPerpetualAPIUserStreamDataSource,
)
from hummingbot.connector.derivative.decibel_perpetual.decibel_perpetual_auth import DecibelPerpetualAuth
from hummingbot.connector.derivative.decibel_perpetual.decibel_perpetual_web_utils import (
    build_api_factory,
    private_rest_url,
    public_rest_url,
)
from hummingbot.connector.perpetual_derivative_py_base import PerpetualDerivativePyBase
from hummingbot.connector.trading_rule import TradingRule
from hummingbot.core.data_type.common import OrderType, PositionAction, PositionMode, PositionSide, TradeType
from hummingbot.core.data_type.funding_info import FundingInfo
from hummingbot.core.data_type.in_flight_order import InFlightOrder, OrderState, OrderUpdate, TradeUpdate
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.data_type.perpetual_api_order_book_data_source import PerpetualAPIOrderBookDataSource
from hummingbot.core.data_type.trade_fee import DeductedFromReturnsTradeFee, TokenAmount, TradeFeeBase
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.event.events import MarketEvent
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.core.utils.estimate_fee import build_trade_fee
from hummingbot.core.web_assistant.connections.data_types import RESTMethod


class DecibelPerpetualDerivative(PerpetualDerivativePyBase):
    web_utils = None  # set in __init__

    def __init__(
        self,
        client_config_map,
        decibel_perpetual_api_key: str,
        decibel_perpetual_api_secret: str,
        trading_pairs: Optional[List[str]] = None,
        trading_required: bool = True,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
    ):
        self._api_key = decibel_perpetual_api_key
        self._api_secret = decibel_perpetual_api_secret
        self._domain = domain
        self._trading_required = trading_required
        self._trading_pairs = trading_pairs or []
        self._last_trade_history_timestamp: Optional[float] = None
        super().__init__(client_config_map)

    @property
    def authenticator(self) -> DecibelPerpetualAuth:
        return DecibelPerpetualAuth(
            api_key=self._api_key,
            api_secret=self._api_secret,
            time_provider=self._time_synchronizer,
        )

    @property
    def name(self) -> str:
        return "decibel_perpetual"

    @property
    def rate_limits_rules(self):
        return CONSTANTS.RATE_LIMITS

    @property
    def domain(self) -> str:
        return self._domain

    @property
    def client_order_id_max_length(self) -> int:
        return 36

    @property
    def client_order_id_prefix(self) -> str:
        return "decibel-"

    @property
    def trading_rules_request_path(self) -> str:
        return CONSTANTS.MARKETS_PATH_URL

    @property
    def trading_pairs_request_path(self) -> str:
        return CONSTANTS.MARKETS_PATH_URL

    @property
    def check_network_request_path(self) -> str:
        return CONSTANTS.SERVER_TIME_PATH_URL

    @property
    def trading_pairs(self) -> List[str]:
        return self._trading_pairs

    @property
    def is_cancel_request_in_exchange_synchronous(self) -> bool:
        return True

    @property
    def is_trading_required(self) -> bool:
        return self._trading_required

    @property
    def funding_fee_poll_interval(self) -> int:
        return 120

    @property
    def supported_position_modes(self) -> List[PositionMode]:
        return [PositionMode.ONEWAY, PositionMode.HEDGE]

    def supported_order_types(self) -> List[OrderType]:
        return [OrderType.LIMIT, OrderType.MARKET, OrderType.LIMIT_MAKER]

    def get_buy_collateral_token(self, trading_pair: str) -> str:
        _, quote = self.split_trading_pair(trading_pair)
        return quote

    def get_sell_collateral_token(self, trading_pair: str) -> str:
        _, quote = self.split_trading_pair(trading_pair)
        return quote

    def _is_request_exception_related_to_time_synchronizer(self, request_exception: Exception) -> bool:
        error_description = str(request_exception)
        return "timestamp" in error_description.lower() or "expired" in error_description.lower()

    def _create_web_assistants_factory(self):
        return build_api_factory(
            throttler=self._throttler,
            time_synchronizer=self._time_synchronizer,
            auth=self.authenticator,
        )

    def _create_order_book_data_source(self) -> PerpetualAPIOrderBookDataSource:
        return DecibelPerpetualAPIOrderBookDataSource(
            trading_pairs=self._trading_pairs,
            connector=self,
            api_factory=self._web_assistants_factory,
            domain=self._domain,
        )

    def _create_user_stream_data_source(self) -> UserStreamTrackerDataSource:
        return DecibelPerpetualAPIUserStreamDataSource(
            auth=self.authenticator,
            trading_pairs=self._trading_pairs,
            connector=self,
            api_factory=self._web_assistants_factory,
            domain=self._domain,
        )

    def _get_fee(self, base_currency, quote_currency, order_type, order_side, amount, price=None, is_maker=None):
        is_maker = order_type is OrderType.LIMIT_MAKER
        return build_trade_fee(
            self.name,
            is_maker,
            base_currency=base_currency,
            quote_currency=quote_currency,
            order_type=order_type,
            order_side=order_side,
            amount=amount,
            price=price,
        )

    async def _place_order(
        self, order_id, trading_pair, amount, trade_type, order_type, price, position_action=PositionAction.OPEN, **kwargs
    ) -> Tuple[str, float]:
        exchange_symbol = await self.exchange_symbol_associated_to_pair(trading_pair)
        side = "buy" if trade_type == TradeType.BUY else "sell"
        order_type_str = "limit" if order_type in (OrderType.LIMIT, OrderType.LIMIT_MAKER) else "market"
        reduce_only = position_action == PositionAction.CLOSE

        body = {
            "market": exchange_symbol,
            "side": side,
            "type": order_type_str,
            "size": str(amount),
            "clientId": order_id,
            "reduceOnly": reduce_only,
        }
        if order_type_str == "limit":
            body["price"] = str(price)
        if order_type == OrderType.LIMIT_MAKER:
            body["postOnly"] = True

        rest_assistant = await self._web_assistants_factory.get_rest_assistant()
        response = await rest_assistant.execute_request(
            url=private_rest_url(CONSTANTS.CREATE_ORDER_PATH_URL),
            method=RESTMethod.POST,
            data=body,
            is_auth_required=True,
            throttler_limit_id=CONSTANTS.CREATE_ORDER_PATH_URL,
        )
        data = response.get("data", response)
        exchange_order_id = str(data.get("id", data.get("orderId", "")))
        transact_time = float(data.get("createdAt", self._time_synchronizer.time() * 1000)) / 1000.0
        return exchange_order_id, transact_time

    async def _place_cancel(self, order_id: str, tracked_order: InFlightOrder):
        exchange_order_id = await tracked_order.get_exchange_order_id()
        rest_assistant = await self._web_assistants_factory.get_rest_assistant()
        path = CONSTANTS.CANCEL_ORDER_PATH_URL.format(order_id=exchange_order_id)
        await rest_assistant.execute_request(
            url=private_rest_url(path),
            method=RESTMethod.DELETE,
            is_auth_required=True,
            throttler_limit_id=CONSTANTS.CANCEL_ORDER_PATH_URL,
        )
        return True

    async def _format_trading_rules(self, exchange_info_dict: Dict[str, Any]) -> List[TradingRule]:
        trading_rules = []
        markets = exchange_info_dict if isinstance(exchange_info_dict, list) else exchange_info_dict.get("data", [])
        for market in markets:
            try:
                trading_pair = await self.trading_pair_associated_to_exchange_symbol(market.get("name", ""))
                trading_rules.append(
                    TradingRule(
                        trading_pair=trading_pair,
                        min_order_size=Decimal(str(market.get("minOrderSize", "0.001"))),
                        max_order_size=Decimal(str(market.get("maxOrderSize", "1000000"))),
                        min_price_increment=Decimal(str(market.get("priceIncrement", "0.01"))),
                        min_base_amount_increment=Decimal(str(market.get("sizeIncrement", "0.001"))),
                        min_notional_size=Decimal(str(market.get("minNotional", "10"))),
                        buy_order_collateral_token=market.get("quoteCurrency", "USD"),
                        sell_order_collateral_token=market.get("quoteCurrency", "USD"),
                    )
                )
            except Exception:
                self.logger().exception(f"Error parsing trading rules for {market}")
        return trading_rules

    async def _status_polling_loop_fetch_updates(self):
        await asyncio.gather(
            self._update_order_fills_from_trades(),
            self._update_order_status(),
            self._update_positions(),
        )

    async def _update_trading_fees(self):
        pass  # Use static defaults from utils.py

    async def _user_stream_event_listener(self):
        async for event_message in self._iter_user_event_queue():
            try:
                channel = event_message.get("channel", "")
                data = event_message.get("data", {})
                if CONSTANTS.WS_ORDERS_CHANNEL in channel:
                    await self._process_order_event(data)
                elif CONSTANTS.WS_FILLS_CHANNEL in channel:
                    await self._process_fill_event(data)
                elif CONSTANTS.WS_POSITIONS_CHANNEL in channel:
                    await self._process_position_event(data)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger().error(f"Error in user stream event listener: {e}", exc_info=True)

    async def _process_order_event(self, data: Dict[str, Any]):
        client_order_id = data.get("clientId", "")
        exchange_order_id = str(data.get("id", ""))
        status_str = data.get("status", "").lower()
        status_map = {
            "open": OrderState.OPEN,
            "new": OrderState.OPEN,
            "partial": OrderState.PARTIALLY_FILLED,
            "filled": OrderState.FILLED,
            "cancelled": OrderState.CANCELLED,
            "canceled": OrderState.CANCELLED,
            "rejected": OrderState.FAILED,
        }
        order_state = status_map.get(status_str, OrderState.OPEN)
        tracked = self._order_tracker.fetch_order(client_order_id=client_order_id) or                   self._order_tracker.fetch_order(exchange_order_id=exchange_order_id)
        if tracked:
            update = OrderUpdate(
                trading_pair=tracked.trading_pair,
                update_timestamp=float(data.get("updatedAt", self._time_synchronizer.time() * 1000)) / 1000.0,
                new_state=order_state,
                client_order_id=client_order_id,
                exchange_order_id=exchange_order_id,
            )
            self._order_tracker.process_order_update(update)

    async def _process_fill_event(self, data: Dict[str, Any]):
        exchange_order_id = str(data.get("orderId", ""))
        tracked = self._order_tracker.fetch_order(exchange_order_id=exchange_order_id)
        if not tracked:
            return
        fee = TradeFeeBase.new_perpetual_fee(
            fee_schema=self._trade_fee_schema(),
            position_action=PositionAction.OPEN,
            percent_token=tracked.quote_asset,
            flat_fees=[TokenAmount(amount=Decimal(str(data.get("fee", 0))), token=tracked.quote_asset)],
        )
        update = TradeUpdate(
            trade_id=str(data.get("id", "")),
            client_order_id=tracked.client_order_id,
            exchange_order_id=exchange_order_id,
            trading_pair=tracked.trading_pair,
            fee=fee,
            fill_price=Decimal(str(data.get("price", 0))),
            fill_base_amount=Decimal(str(data.get("size", 0))),
            fill_quote_amount=Decimal(str(data.get("price", 0))) * Decimal(str(data.get("size", 0))),
            fill_timestamp=float(data.get("createdAt", self._time_synchronizer.time() * 1000)) / 1000.0,
        )
        self._order_tracker.process_trade_update(update)

    async def _process_position_event(self, data: Dict[str, Any]):
        pass  # Handled by polling _update_positions

    async def _all_trade_updates_for_order(self, order: InFlightOrder) -> List[TradeUpdate]:
        rest_assistant = await self._web_assistants_factory.get_rest_assistant()
        response = await rest_assistant.execute_request(
            url=private_rest_url(CONSTANTS.FILLS_PATH_URL),
            method=RESTMethod.GET,
            params={"orderId": await order.get_exchange_order_id()},
            is_auth_required=True,
            throttler_limit_id=CONSTANTS.FILLS_PATH_URL,
        )
        fills = response.get("data", response) if isinstance(response, dict) else response
        trades = []
        for fill in (fills if isinstance(fills, list) else []):
            fee = TradeFeeBase.new_perpetual_fee(
                fee_schema=self._trade_fee_schema(),
                position_action=PositionAction.OPEN,
                percent_token=order.quote_asset,
                flat_fees=[TokenAmount(amount=Decimal(str(fill.get("fee", 0))), token=order.quote_asset)],
            )
            trades.append(TradeUpdate(
                trade_id=str(fill.get("id", "")),
                client_order_id=order.client_order_id,
                exchange_order_id=str(fill.get("orderId", "")),
                trading_pair=order.trading_pair,
                fee=fee,
                fill_price=Decimal(str(fill.get("price", 0))),
                fill_base_amount=Decimal(str(fill.get("size", 0))),
                fill_quote_amount=Decimal(str(fill.get("price", 0))) * Decimal(str(fill.get("size", 0))),
                fill_timestamp=float(fill.get("createdAt", self._time_synchronizer.time() * 1000)) / 1000.0,
            ))
        return trades

    async def _request_order_status(self, tracked_order: InFlightOrder) -> OrderUpdate:
        exchange_order_id = await tracked_order.get_exchange_order_id()
        rest_assistant = await self._web_assistants_factory.get_rest_assistant()
        path = CONSTANTS.ORDER_STATUS_PATH_URL.format(order_id=exchange_order_id)
        response = await rest_assistant.execute_request(
            url=private_rest_url(path),
            method=RESTMethod.GET,
            is_auth_required=True,
            throttler_limit_id=CONSTANTS.OPEN_ORDERS_PATH_URL,
        )
        data = response.get("data", response)
        status_str = data.get("status", "").lower()
        status_map = {
            "open": OrderState.OPEN, "new": OrderState.OPEN,
            "partial": OrderState.PARTIALLY_FILLED,
            "filled": OrderState.FILLED,
            "cancelled": OrderState.CANCELLED, "canceled": OrderState.CANCELLED,
            "rejected": OrderState.FAILED,
        }
        return OrderUpdate(
            client_order_id=tracked_order.client_order_id,
            exchange_order_id=exchange_order_id,
            trading_pair=tracked_order.trading_pair,
            update_timestamp=float(data.get("updatedAt", self._time_synchronizer.time() * 1000)) / 1000.0,
            new_state=status_map.get(status_str, OrderState.OPEN),
        )

    async def _update_balances(self):
        rest_assistant = await self._web_assistants_factory.get_rest_assistant()
        response = await rest_assistant.execute_request(
            url=private_rest_url(CONSTANTS.ACCOUNT_OVERVIEW_PATH_URL),
            method=RESTMethod.GET,
            is_auth_required=True,
            throttler_limit_id=CONSTANTS.ACCOUNT_OVERVIEW_PATH_URL,
        )
        data = response.get("data", response)
        self._account_available_balances.clear()
        self._account_balances.clear()
        for asset, info in data.get("collateral", {}).items():
            total = Decimal(str(info.get("value", 0)))
            free = Decimal(str(info.get("freeCollateral", total)))
            self._account_balances[asset] = total
            self._account_available_balances[asset] = free
        # Also handle flat balance response
        for balance_entry in data.get("balances", []):
            asset = balance_entry.get("currency", balance_entry.get("asset", ""))
            total = Decimal(str(balance_entry.get("total", balance_entry.get("balance", 0))))
            free = Decimal(str(balance_entry.get("free", balance_entry.get("availableBalance", total))))
            self._account_balances[asset] = total
            self._account_available_balances[asset] = free

    async def _initialize_trading_pair_symbols_from_exchange_info(self, exchange_info: Dict[str, Any]):
        mapping = {}
        markets = exchange_info if isinstance(exchange_info, list) else exchange_info.get("data", [])
        for market in markets:
            symbol = market.get("name", "")
            base = market.get("baseCurrency", symbol.split("-")[0] if "-" in symbol else symbol)
            quote = market.get("quoteCurrency", "USD")
            trading_pair = f"{base}-{quote}"
            mapping[symbol] = trading_pair
        self._set_trading_pair_symbol_map(mapping)

    async def _get_last_traded_price(self, trading_pair: str) -> float:
        prices = await self._order_book_data_source.get_last_traded_prices([trading_pair])
        return prices.get(trading_pair, 0.0)

    async def _update_positions(self):
        rest_assistant = await self._web_assistants_factory.get_rest_assistant()
        response = await rest_assistant.execute_request(
            url=private_rest_url(CONSTANTS.ACCOUNT_POSITIONS_PATH_URL),
            method=RESTMethod.GET,
            is_auth_required=True,
            throttler_limit_id=CONSTANTS.ACCOUNT_POSITIONS_PATH_URL,
        )
        positions = response.get("data", response)
        if not isinstance(positions, list):
            positions = [positions]
        for pos_data in positions:
            trading_pair = await self.trading_pair_associated_to_exchange_symbol(pos_data.get("market", ""))
            size = Decimal(str(pos_data.get("netSize", pos_data.get("size", 0))))
            side = PositionSide.LONG if size >= 0 else PositionSide.SHORT
            entry_price = Decimal(str(pos_data.get("entryPrice", 0) or 0))
            unrealized_pnl = Decimal(str(pos_data.get("unrealizedPnl", 0) or 0))
            leverage = Decimal(str(pos_data.get("leverage", 1) or 1))
            if trading_pair:
                position_key = self._perpetual_trading.position_key(trading_pair, side)
                if abs(size) > Decimal("0"):
                    self._perpetual_trading.set_position(
                        position_key,
                        amount=abs(size),
                        entry_price=entry_price,
                        unrealized_pnl=unrealized_pnl,
                        leverage=leverage,
                        position_side=side,
                    )

    async def _set_trading_pair_leverage(self, trading_pair: str, leverage: int) -> Tuple[bool, str]:
        exchange_symbol = await self.exchange_symbol_associated_to_pair(trading_pair)
        rest_assistant = await self._web_assistants_factory.get_rest_assistant()
        try:
            await rest_assistant.execute_request(
                url=private_rest_url(CONSTANTS.SET_LEVERAGE_PATH_URL),
                method=RESTMethod.POST,
                data={"market": exchange_symbol, "leverage": leverage},
                is_auth_required=True,
                throttler_limit_id=CONSTANTS.ACCOUNT_OVERVIEW_PATH_URL,
            )
            return True, ""
        except Exception as e:
            return False, str(e)

    async def _fetch_last_fee_payment(self, trading_pair: str) -> Tuple[int, Decimal, Decimal]:
        exchange_symbol = await self.exchange_symbol_associated_to_pair(trading_pair)
        rest_assistant = await self._web_assistants_factory.get_rest_assistant()
        response = await rest_assistant.execute_request(
            url=private_rest_url(CONSTANTS.FUNDING_HISTORY_PATH_URL),
            method=RESTMethod.GET,
            params={"market": exchange_symbol, "limit": 1},
            is_auth_required=True,
            throttler_limit_id=CONSTANTS.FILLS_PATH_URL,
        )
        payments = response.get("data", [])
        if not payments:
            return 0, Decimal("0"), Decimal("0")
        latest = payments[0]
        ts = int(float(latest.get("time", 0)) * 1000 if float(latest.get("time", 0)) < 1e12 else latest.get("time", 0))
        rate = Decimal(str(latest.get("rate", 0)))
        payment = Decimal(str(latest.get("payment", 0)))
        return ts, rate, payment

    async def _update_order_fills_from_trades(self):
        pass  # Handled via WebSocket fills + REST fallback in _all_trade_updates_for_order

    async def _update_order_status(self):
        open_orders = list(self._order_tracker.active_orders.values())
        tasks = [self._request_order_status(order) for order in open_orders]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for update in results:
            if isinstance(update, OrderUpdate):
                self._order_tracker.process_order_update(update)
