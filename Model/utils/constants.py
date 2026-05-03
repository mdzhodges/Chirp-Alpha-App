from alpaca.trading.enums import OrderSide


class Constants:

    BULLISH_STR:str = "BULLISH"
    BALANCED_STR:str = "BALANCED"
    BEARISH_STR:str = "BEARISH"
    ALPACA_BULLISH_API_KEY:str = "ALPACA_BULLISH_API_KEY"
    ALPACA_BULLISH_API_KEY_SECRET: str = "ALPACA_BULLISH_API_KEY_SECRET"

    ALPACA_BALANCED_API_KEY:str = "ALPACA_BALANCED_API_KEY"
    ALPACA_BALANCED_API_KEY_SECRET: str = "ALPACA_BALANCED_API_KEY_SECRET"

    ALPACA_BEARISH_API_KEY:str = "ALPACA_BEARISH_API_KEY"
    ALPACA_BEARISH_API_KEY_SECRET: str = "ALPACA_BEARISH_API_KEY_SECRET"

    ALPACA_ACCOUNT_URL: str = "https://paper-api.alpaca.markets/v2/account"

    ORDER_SIDE_ACTIONS_LIST: list[OrderSide] = [OrderSide.BUY, OrderSide.SELL]
    ACTIONS_LIST: list[OrderSide | str] = [OrderSide.BUY, OrderSide.SELL, "HOLD"]

    TICKER_FEATURES_LIST: list[str] = [
        "portfolio_weight",
        "cost_basis_to_portfolio_value",
        "unrealized_pl_to_portfolio_value",
        "change_today"
    ]

    TICKER_SYMBOL_LIST: list[str] = ["BLK", "AAPL", "WMT", "NVDA", "KO", "CRWV", "QQQ", "SPY", "JPM", "GS"]
