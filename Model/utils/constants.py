from alpaca.trading.enums import OrderSide


class Constants:
    BULLISH_STR: str = "bullish"
    BALANCED_STR: str = "balanced"
    BEARISH_STR: str = "bearish"
    ALPACA_BULLISH_API_KEY: str = "ALPACA_BULLISH_API_KEY"
    ALPACA_BULLISH_API_KEY_SECRET: str = "ALPACA_BULLISH_API_KEY_SECRET"

    ALPACA_BALANCED_API_KEY: str = "ALPACA_BALANCED_API_KEY"
    ALPACA_BALANCED_API_KEY_SECRET: str = "ALPACA_BALANCED_API_KEY_SECRET"

    ALPACA_BEARISH_API_KEY: str = "ALPACA_BEARISH_API_KEY"
    ALPACA_BEARISH_API_KEY_SECRET: str = "ALPACA_BEARISH_API_KEY_SECRET"

    BACKEND_BASE_URL = "http://localhost:8080"
    ALPACA_ACCOUNT_URL: str = "https://paper-api.alpaca.markets/v2/account"

    ORDER_SIDE_ACTIONS_LIST: list[OrderSide] = [OrderSide.BUY, OrderSide.SELL]
    ACTIONS_LIST: list[OrderSide | str] = [OrderSide.BUY, OrderSide.SELL, "HOLD"]

    TICKER_FEATURES_LIST: list[str] = [
        "portfolio_weight",
        "cost_basis_to_portfolio_value",
        "unrealized_pl_to_portfolio_value",
        "change_today"
    ]

    TARGET_CASH_PERCENT: float = 0.50
    INITIAL_CASH_WEIGHT: float = 0.50
    INITIAL_EQUITY_WEIGHT_PER_SYMBOL: float = 0.05

    MAX_EQUITY_WEIGHT_PER_SYMBOL: float = 0.10
    MIN_EQUITY_WEIGHT_PER_SYMBOL: float = 0.025

    MOMENTUM_BUY_THRESHOLD: float = 0.05
    MOMENTUM_SELL_THRESHOLD: float = -0.05

    DAILY_TRADE_WEIGHT: float = 0.005

    TICKER_SYMBOL_BROAD_MARKET_INDEXES: list[str] = ["DIA", "QQQ", "SPY", "^VIX"]

    DATA_INGESTION_TICKER_SYMBOL_LIST: list[str] = ["DIA", "QQQ", "SPY", "^VIX", "BLK", "AAPL", "WMT", "NVDA", "KO",
                                                    "CRWV", "QQQ", "SPY", "JPM", "GS"]

    PORTFOLIO_TICKER_SYMBOL_LIST: list[str] = ["BLK", "AAPL", "WMT", "NVDA", "KO", "CRWV", "QQQ", "SPY", "JPM", "GS"]
