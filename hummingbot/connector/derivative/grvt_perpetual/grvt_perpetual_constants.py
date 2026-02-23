"""
Constants for the GRVT Perpetual connector.
GRVT API docs: https://api-docs.grvt.io
"""
from hummingbot.core.api_throttler.data_types import RateLimit, LinkedLimitWeightPair

EXCHANGE_NAME = "grvt_perpetual"
DEFAULT_DOMAIN = "prod"

# ── REST base URLs ─────────────────────────────────────────────────────────────
REST_URLS = {
    "prod": "https://edge.grvt.io",
    "testnet": "https://edge.testnet.grvt.io",
}

# Market data REST (public)
MARKET_DATA_REST_URLS = {
    "prod": "https://trades.grvt.io",
    "testnet": "https://trades.testnet.grvt.io",
}

# ── WebSocket base URLs ────────────────────────────────────────────────────────
WS_URLS = {
    "prod": "wss://trades.grvt.io/ws/full",
    "testnet": "wss://trades.testnet.grvt.io/ws/full",
}

# Private WS (requires auth cookie)
PRIVATE_WS_URLS = {
    "prod": "wss://stream.grvt.io/ws/full",
    "testnet": "wss://stream.testnet.grvt.io/ws/full",
}

# ── Auth endpoint ──────────────────────────────────────────────────────────────
AUTH_PATH = "/auth/api_key/login"

# ── REST endpoints ─────────────────────────────────────────────────────────────
# Public — market data (on trades subdomain)
INSTRUMENTS_PATH = "/full/v1/instruments"
GET_INSTRUMENT_PATH = "/full/v1/instrument"
TICKER_PATH = "/full/v1/ticker"
ORDERBOOK_LEVELS_PATH = "/full/v1/book"
ALL_TRADES_PATH = "/full/v1/all_trades"
FUNDING_RATE_PATH = "/full/v1/funding"
KLINES_PATH = "/full/v1/klines"

# Private — trading (on edge subdomain)
CREATE_ORDER_PATH = "/full/v1/create_order"
CANCEL_ORDER_PATH = "/full/v1/cancel_order"
CANCEL_ALL_ORDERS_PATH = "/full/v1/cancel_all_orders"
GET_ORDER_PATH = "/full/v1/order"
OPEN_ORDERS_PATH = "/full/v1/open_orders"
ORDER_HISTORY_PATH = "/full/v1/order_history"
TRADE_HISTORY_PATH = "/full/v1/trade_history"
POSITIONS_PATH = "/full/v1/positions"
SUB_ACCOUNTS_PATH = "/full/v1/sub_account"
FUNDING_HISTORY_PATH = "/full/v1/account_history"

# ── WebSocket stream names ─────────────────────────────────────────────────────
WS_ORDER_BOOK_CHANNEL = "v1.book.s"       # snapshot + delta, format: INSTRUMENT@numLevels-aggregate-numPrecisions
WS_TRADES_CHANNEL = "v1.trade"
WS_TICKER_CHANNEL = "v1.ticker.s"
WS_MINI_TICKER_CHANNEL = "v1.mini.s"
WS_FUNDING_CHANNEL = "v1.funding"

# Private streams
WS_ORDERS_CHANNEL = "v1.order"
WS_FILLS_CHANNEL = "v1.fill"
WS_POSITIONS_CHANNEL = "v1.position"

# ── Rate limits ────────────────────────────────────────────────────────────────
RATE_LIMITS = [
    RateLimit(limit_id="public", limit=100, time_interval=1),
    RateLimit(limit_id="private", limit=30, time_interval=1),
    RateLimit(
        limit_id=INSTRUMENTS_PATH, limit=100, time_interval=1,
        linked_limits=[LinkedLimitWeightPair("public", 1)]
    ),
    RateLimit(
        limit_id=ORDERBOOK_LEVELS_PATH, limit=100, time_interval=1,
        linked_limits=[LinkedLimitWeightPair("public", 1)]
    ),
    RateLimit(
        limit_id=FUNDING_RATE_PATH, limit=100, time_interval=1,
        linked_limits=[LinkedLimitWeightPair("public", 1)]
    ),
    RateLimit(
        limit_id=CREATE_ORDER_PATH, limit=30, time_interval=1,
        linked_limits=[LinkedLimitWeightPair("private", 1)]
    ),
    RateLimit(
        limit_id=CANCEL_ORDER_PATH, limit=30, time_interval=1,
        linked_limits=[LinkedLimitWeightPair("private", 1)]
    ),
    RateLimit(
        limit_id=OPEN_ORDERS_PATH, limit=30, time_interval=1,
        linked_limits=[LinkedLimitWeightPair("private", 1)]
    ),
    RateLimit(
        limit_id=POSITIONS_PATH, limit=30, time_interval=1,
        linked_limits=[LinkedLimitWeightPair("private", 1)]
    ),
]

# ── Misc ───────────────────────────────────────────────────────────────────────
# GRVT uses EIP-712 signing for orders (ZK L2 chain ID 325 mainnet)
GRVT_L2_CHAIN_ID = 325
GRVT_L2_CHAIN_ID_TESTNET = 326

# Trading pair delimiter
TRADING_PAIR_SPLITTER = "_"
# GRVT instrument format: BTC_USDT_Perp
PERP_SUFFIX = "Perp"

# Cookie name
GRVT_COOKIE_NAME = "gravity"
