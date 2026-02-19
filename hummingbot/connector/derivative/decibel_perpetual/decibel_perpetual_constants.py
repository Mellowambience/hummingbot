from hummingbot.core.api_throttler.data_types import LinkedLimitWeightPair, RateLimit

DEFAULT_DOMAIN = "decibel_perpetual"

DECIBEL_REST_URL = "https://api.decibel.trade"
DECIBEL_WSS_URL = "wss://stream.decibel.trade/ws"

# Public REST endpoints
MARKETS_PATH_URL = "/v1/markets"
MARKET_PRICES_PATH_URL = "/v1/market-prices"
ORDER_BOOK_PATH_URL = "/v1/markets/{market_name}/orderbook"
FUNDING_INFO_PATH_URL = "/v1/markets/{market_name}/funding"
TRADES_PATH_URL = "/v1/trades"
SERVER_TIME_PATH_URL = "/v1/time"

# Private REST endpoints
ACCOUNT_OVERVIEW_PATH_URL = "/v1/account/overview"
ACCOUNT_POSITIONS_PATH_URL = "/v1/account/positions"
OPEN_ORDERS_PATH_URL = "/v1/account/orders"
CREATE_ORDER_PATH_URL = "/v1/orders"
CANCEL_ORDER_PATH_URL = "/v1/orders/{order_id}"
ORDER_STATUS_PATH_URL = "/v1/orders/{order_id}"
FILLS_PATH_URL = "/v1/account/fills"
FUNDING_HISTORY_PATH_URL = "/v1/account/funding-history"
SET_LEVERAGE_PATH_URL = "/v1/account/leverage"

# WebSocket channels
WS_ORDERBOOK_CHANNEL = "orderbook"
WS_TRADES_CHANNEL = "trades"
WS_ORDERS_CHANNEL = "orders"
WS_FILLS_CHANNEL = "fills"
WS_POSITIONS_CHANNEL = "positions"
WS_FUNDING_CHANNEL = "funding"

HEARTBEAT_TIME_INTERVAL = 30.0

# Rate limits
MAX_REQUEST_WEIGHT = 1200
NO_LIMIT_ID = "NO_LIMIT"
REQUEST_WEIGHT_ID = "REQUEST_WEIGHT"

RATE_LIMITS = [
    RateLimit(limit_id=NO_LIMIT_ID, limit=MAX_REQUEST_WEIGHT, time_interval=60),
    RateLimit(
        limit_id=REQUEST_WEIGHT_ID,
        limit=MAX_REQUEST_WEIGHT,
        time_interval=60,
        linked_limits=[LinkedLimitWeightPair(NO_LIMIT_ID)],
    ),
    # Public endpoints
    RateLimit(limit_id=MARKETS_PATH_URL, limit=MAX_REQUEST_WEIGHT, time_interval=60,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT_ID, 1)]),
    RateLimit(limit_id=MARKET_PRICES_PATH_URL, limit=MAX_REQUEST_WEIGHT, time_interval=60,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT_ID, 1)]),
    RateLimit(limit_id=ORDER_BOOK_PATH_URL, limit=MAX_REQUEST_WEIGHT, time_interval=60,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT_ID, 1)]),
    RateLimit(limit_id=FUNDING_INFO_PATH_URL, limit=MAX_REQUEST_WEIGHT, time_interval=60,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT_ID, 1)]),
    RateLimit(limit_id=TRADES_PATH_URL, limit=MAX_REQUEST_WEIGHT, time_interval=60,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT_ID, 1)]),
    # Private endpoints
    RateLimit(limit_id=ACCOUNT_OVERVIEW_PATH_URL, limit=MAX_REQUEST_WEIGHT, time_interval=60,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT_ID, 5)]),
    RateLimit(limit_id=ACCOUNT_POSITIONS_PATH_URL, limit=MAX_REQUEST_WEIGHT, time_interval=60,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT_ID, 5)]),
    RateLimit(limit_id=OPEN_ORDERS_PATH_URL, limit=MAX_REQUEST_WEIGHT, time_interval=60,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT_ID, 5)]),
    RateLimit(limit_id=CREATE_ORDER_PATH_URL, limit=MAX_REQUEST_WEIGHT, time_interval=60,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT_ID, 10)]),
    RateLimit(limit_id=CANCEL_ORDER_PATH_URL, limit=MAX_REQUEST_WEIGHT, time_interval=60,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT_ID, 5)]),
    RateLimit(limit_id=FILLS_PATH_URL, limit=MAX_REQUEST_WEIGHT, time_interval=60,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT_ID, 5)]),
]
