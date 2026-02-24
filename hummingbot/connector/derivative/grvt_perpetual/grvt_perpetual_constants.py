from hummingbot.core.api_throttler.data_types import LinkedLimitWeightPair, RateLimit
from hummingbot.core.data_type.in_flight_order import OrderState

EXCHANGE_NAME = "grvt_perpetual"
BROKER_ID = "HBOT"
MAX_ORDER_ID_LEN = None

DOMAIN = EXCHANGE_NAME
TESTNET_DOMAIN = "grvt_perpetual_testnet"

# REST endpoints
REST_URL = "https://edge.grvt.io"
TESTNET_REST_URL = "https://edge.testnet.grvt.io"

# WebSocket endpoints (market data)
WS_URL = "wss://market-data.grvt.io/ws/full"
TESTNET_WS_URL = "wss://market-data.testnet.grvt.io/ws/full"

# WebSocket endpoints (trading — authenticated)
TRADES_WS_URL = "wss://trades.grvt.io/ws/full"
TESTNET_TRADES_WS_URL = "wss://trades.testnet.grvt.io/ws/full"

# Auth endpoint
AUTH_PATH = "/auth/api_key/login"

# REST API paths
INSTRUMENTS_PATH = "/full/v1/instruments"
TICKER_PATH = "/full/v1/ticker"
ORDER_BOOK_PATH = "/full/v1/book"
MARKET_TRADES_PATH = "/full/v1/trades"
FUNDING_RATE_PATH = "/full/v1/funding"

# Private REST paths
CREATE_ORDER_PATH = "/full/v1/order"
CANCEL_ORDER_PATH = "/full/v1/order/cancel"
GET_ORDER_PATH = "/full/v1/order"
GET_OPEN_ORDERS_PATH = "/full/v1/orders"
GET_POSITIONS_PATH = "/full/v1/positions"
GET_BALANCES_PATH = "/full/v1/account_summary"
GET_FUNDING_PAYMENTS_PATH = "/full/v1/funding_history"
GET_TRADE_HISTORY_PATH = "/full/v1/trade_history"

# WebSocket stream names
WS_ORDER_BOOK_STREAM = "v1.book.s"
WS_TRADES_STREAM = "v1.trade"
WS_TICKER_STREAM = "v1.mini.s"
WS_ORDER_STREAM = "v1.order"
WS_POSITION_STREAM = "v1.position"
WS_FILLS_STREAM = "v1.fill"

# GRVT uses "full" encoding variant for field names
ENCODING = "full"

# GRVT Chain IDs (for EIP-712 order signing)
MAINNET_CHAIN_ID = 325
TESTNET_CHAIN_ID = 326

# Instrument kind for perpetuals
INSTRUMENT_KIND_PERPETUAL = "PERPETUAL"

# Order types
ORDER_TYPE_LIMIT = "LIMIT"
ORDER_TYPE_MARKET = "MARKET"

# Order sides
SIDE_BUY = "BUY"
SIDE_SELL = "SELL"

# Time in force
TIME_IN_FORCE_GTC = "GOOD_TILL_CANCEL"
TIME_IN_FORCE_IOC = "IMMEDIATE_OR_CANCEL"
TIME_IN_FORCE_FOK = "FILL_OR_KILL"

# Order states
ORDER_STATE_MAP = {
    "OPEN": OrderState.OPEN,
    "FILLED": OrderState.FILLED,
    "CANCELLED": OrderState.CANCELED,
    "PARTIALLY_FILLED": OrderState.PARTIALLY_FILLED,
    "REJECTED": OrderState.FAILED,
    "EXPIRED": OrderState.CANCELED,
}

# Rate limits
ALL_ENDPOINTS_LIMIT_ID = "AllEndpoints"
ALL_ENDPOINTS_RATE_LIMIT = 1200  # per minute
NO_LIMIT_ID = "NoLimit"
PING_ID = "PING"

RATE_LIMITS = [
    RateLimit(limit_id=ALL_ENDPOINTS_LIMIT_ID, limit=ALL_ENDPOINTS_RATE_LIMIT, time_interval=60),
    RateLimit(limit_id=NO_LIMIT_ID, limit=4000, time_interval=60),
    RateLimit(
        limit_id=INSTRUMENTS_PATH,
        limit=ALL_ENDPOINTS_RATE_LIMIT,
        time_interval=60,
        linked_limits=[LinkedLimitWeightPair(ALL_ENDPOINTS_LIMIT_ID)],
    ),
    RateLimit(
        limit_id=TICKER_PATH,
        limit=ALL_ENDPOINTS_RATE_LIMIT,
        time_interval=60,
        linked_limits=[LinkedLimitWeightPair(ALL_ENDPOINTS_LIMIT_ID)],
    ),
    RateLimit(
        limit_id=ORDER_BOOK_PATH,
        limit=ALL_ENDPOINTS_RATE_LIMIT,
        time_interval=60,
        linked_limits=[LinkedLimitWeightPair(ALL_ENDPOINTS_LIMIT_ID)],
    ),
    RateLimit(
        limit_id=CREATE_ORDER_PATH,
        limit=ALL_ENDPOINTS_RATE_LIMIT,
        time_interval=60,
        linked_limits=[LinkedLimitWeightPair(ALL_ENDPOINTS_LIMIT_ID)],
    ),
    RateLimit(
        limit_id=CANCEL_ORDER_PATH,
        limit=ALL_ENDPOINTS_RATE_LIMIT,
        time_interval=60,
        linked_limits=[LinkedLimitWeightPair(ALL_ENDPOINTS_LIMIT_ID)],
    ),
    RateLimit(
        limit_id=GET_OPEN_ORDERS_PATH,
        limit=ALL_ENDPOINTS_RATE_LIMIT,
        time_interval=60,
        linked_limits=[LinkedLimitWeightPair(ALL_ENDPOINTS_LIMIT_ID)],
    ),
    RateLimit(
        limit_id=GET_POSITIONS_PATH,
        limit=ALL_ENDPOINTS_RATE_LIMIT,
        time_interval=60,
        linked_limits=[LinkedLimitWeightPair(ALL_ENDPOINTS_LIMIT_ID)],
    ),
    RateLimit(
        limit_id=GET_BALANCES_PATH,
        limit=ALL_ENDPOINTS_RATE_LIMIT,
        time_interval=60,
        linked_limits=[LinkedLimitWeightPair(ALL_ENDPOINTS_LIMIT_ID)],
    ),
]
