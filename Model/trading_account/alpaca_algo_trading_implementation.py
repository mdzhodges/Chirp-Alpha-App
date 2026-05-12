import importlib
import json
import os as _os
import queue
import sys
import urllib.parse
import urllib.request
from collections import deque
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from alpaca.trading import Position, MarketOrderRequest, Order
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce

from Model.logger.logger import AppLogger

_PROJECT_ROOT = _os.path.abspath(
    _os.path.join(_os.path.dirname(__file__), "../..")
)

_LOCAL_GRPC_DIR = _os.path.join(_PROJECT_ROOT, "grpc")


def _import_real_grpc_package():
    """
    Import the real grpcio package, not this project's local ./grpc folder.
    """

    original_sys_path = list(sys.path)

    try:
        # Remove paths that make Python see ./grpc as the grpc package.
        sys.path = [
            path for path in sys.path
            if _os.path.abspath(path or ".") != _PROJECT_ROOT
               and _os.path.abspath(path or ".") != _LOCAL_GRPC_DIR
        ]

        # If Python already imported the wrong local grpc package, remove it.
        existing_grpc = sys.modules.get("grpc")
        if existing_grpc is not None:
            grpc_file = getattr(existing_grpc, "__file__", "") or ""

            if _os.path.abspath(grpc_file).startswith(_LOCAL_GRPC_DIR):
                del sys.modules["grpc"]

        real_grpc = importlib.import_module("grpc")

        return real_grpc

    finally:
        sys.path = original_sys_path


_grpc = _import_real_grpc_package()

if _LOCAL_GRPC_DIR not in sys.path:
    sys.path.insert(0, _LOCAL_GRPC_DIR)

import momentum_pb2
import momentum_pb2_grpc
from Model.trading_account.alpaca_trading_portfolio import AlpacaTradingPortfolio
from Model.utils.constants import Constants


# TODO: The portfolio will be equally weighted, remove 'random' logic from below
class AlpacaAlgoTradingImplementation:

    def __init__(self, alpaca_algo_trading_credentials_dict: dict[str, tuple[str, str]]) -> None:
        self._algorithmic_trading_credentials_dict: dict[str, tuple[str, str]] = alpaca_algo_trading_credentials_dict
        self._logger = AppLogger.get_logger(self.__class__.__name__)

        self._bar_queue: queue.Queue[dict] = queue.Queue()
        self._bar_history: deque[dict] = deque(maxlen=5000)

        self._channel = _grpc.insecure_channel('localhost:50051')
        self._stub = momentum_pb2_grpc.MomentumServiceStub(channel=self._channel)

        self._has_initialized_portfolio: bool = False

        self._close_of_market_time: time = time(16, 0)
        self._current_time_est: time = datetime.now().astimezone(ZoneInfo("America/New_York")).time()

    async def _handle_bar(self, data) -> None:
        bar_dict: dict = data.model_dump()

        self._latest_bar_dict = bar_dict
        self._bar_history.append(bar_dict)

        self._bar_queue.put(bar_dict)

    async def execute_trading_algorithm(self) -> None:

        for algorithmic_strategy_str, api_key_tuple in self._algorithmic_trading_credentials_dict.items():
            alpaca_api_key: str = api_key_tuple[0]
            alpaca_api_key_secret: str = api_key_tuple[1]

            self._logger.info("=" * 100)
            self._logger.info(f"Executing Trading Algorithm: {algorithmic_strategy_str.upper()}")
            self._logger.info("=" * 100)

            trading_client: TradingClient = TradingClient(
                api_key=alpaca_api_key,
                secret_key=alpaca_api_key_secret,
                paper=True,
            )

            alpaca_trading_portfolio: AlpacaTradingPortfolio = AlpacaTradingPortfolio(
                trading_client=trading_client
            )

            try:
                account_dict: dict[str, Any] = alpaca_trading_portfolio.get_account_dict()
                all_positions_list: list[Position] = trading_client.get_all_positions()

                # self._initialize_portfolio_holdings(trading_client=trading_client, account_dict=account_dict)

                model_predictions_dict: dict = self._get_model_predictions_dict()

                self._execute_daily_momentum_policy(
                    trading_client=trading_client,
                    model_predictions_dict=model_predictions_dict,
                    algorithmic_strategy_str=algorithmic_strategy_str,
                    account_dict=account_dict,
                    all_positions_list=all_positions_list,
                )

                current_datetime: datetime = datetime.now().astimezone(
                    ZoneInfo("America/New_York")
                )

                portfolio_cash: float = account_dict.get("cash", 0.0)
                portfolio_equity: float = account_dict.get("equity", 0.0)

                self._logger.info(
                    f"Timestamp: {current_datetime.time()} -> "
                    f"Portfolio Equity: {portfolio_equity:,.2f} -> "
                    f"Portfolio Cash Available: ${portfolio_cash:,.2f}"
                )
                self._logger.info("=" * 150)

            except Exception as e:
                self._logger.error(f"Exception Thrown: {e}")


    def _get_model_predictions_dict(self) -> dict[str, float]:
        """
        Calls the Java backend for stock history, market history, and tweets.
        Then sends that data into the Python gRPC momentum model.

        Returns:
            {
                "AAPL": {
                    "ensemble": float,
                    "balanced": float,
                    "bullish": float,
                    "bearish": float,
                    "high_ic": float,
                    "signals": list[str]
                }
            }
        """

        model_predictions_dict: dict = {}

        market_history_dict: dict = self._get_backend_market_history_proto_dict()

        if not market_history_dict:
            self._logger.warning("No market history returned from backend.")
            return model_predictions_dict

        for ticker in Constants.DATA_INGESTION_TICKER_SYMBOL_LIST:
            try:
                stock_history_list: list = self._get_backend_stock_history_proto_list(ticker=ticker)
                tweets_list: list[str] = self._get_backend_tweets_list(ticker=ticker)

                if len(stock_history_list) < 60:
                    self._logger.warning(
                        f"Skipping {ticker}: backend returned only "
                        f"{len(stock_history_list)} stock history rows."
                    )
                    continue

                request = momentum_pb2.MomentumRequest(
                    ticker=ticker,
                    stock_history=stock_history_list,
                    market_history=market_history_dict,
                    tweets=tweets_list,
                    model_type="ensemble",
                    offset=1,
                )

                response = self._stub.PredictMomentum(request, timeout=30)

                ticker_outputs: dict = {
                    "ensemble": float(response.momentum),
                    "signals": list(response.signals),
                }

                for model_name, model_value in response.model_outputs.items():
                    ticker_outputs[model_name] = float(model_value)

                ticker_outputs.setdefault("balanced", 0.0)
                ticker_outputs.setdefault("bullish", 0.0)
                ticker_outputs.setdefault("bearish", 0.0)
                ticker_outputs.setdefault("high_ic", 0.0)

                model_predictions_dict[ticker] = ticker_outputs

            except _grpc.RpcError as e:
                self._logger.error(f"gRPC error for {ticker}: {e.code()} - {e.details()}")
                model_predictions_dict[ticker] = self._empty_prediction_dict()

            except Exception as e:
                self._logger.error(f"Prediction error for {ticker}: {e}")
                model_predictions_dict[ticker] = self._empty_prediction_dict()

        return model_predictions_dict

    def _initialize_portfolio_holdings(self, trading_client: TradingClient, account_dict: dict[str, Any]) -> None:
        """
        Initializes the portfolio only if it has not already been initialized.

        Target lifecycle state:
            - 50% portfolio value remains cash
            - 50% portfolio value is invested
            - invested portion is equally split across PORTFOLIO_TICKER_SYMBOL_LIST

        This does not rely on an in-memory flag, because this bot may run daily.
        Instead, it checks the real Alpaca account state.
        """

        portfolio_tickers: list[str] = Constants.PORTFOLIO_TICKER_SYMBOL_LIST

        if not portfolio_tickers:
            self._logger.warning("No portfolio tickers configured. Skipping portfolio initialization.")
            return

        portfolio_value: float = float(
            account_dict.get("portfolio_value")
            or account_dict.get("equity")
            or 0.0
        )

        cash_available: float = float(account_dict.get("cash", 0.0))

        if portfolio_value <= 0:
            self._logger.warning("Invalid portfolio value. Skipping portfolio initialization.")
            return

        if cash_available <= 0:
            self._logger.info("No cash available. Skipping portfolio initialization.")
            return

        target_cash_amount: float = portfolio_value * Constants.TARGET_CASH_PERCENT

        cash_to_invest: float = cash_available - target_cash_amount

        if cash_to_invest <= 0:
            self._logger.warning(
                f"Cash available ${cash_available:,.2f} is already at or below "
                f"target cash amount ${target_cash_amount:,.2f}. Skipping initialization."
            )
            return

        dollars_per_ticker: float = cash_to_invest / len(portfolio_tickers)

        self._logger.info("Initializing Portfolio Holdings:")
        self._logger.info(f"Portfolio Value: ${portfolio_value:,.2f}")
        self._logger.info(f"Cash Available: ${cash_available:,.2f}")
        self._logger.info(f"Target Cash: ${target_cash_amount:,.2f}")
        self._logger.info(f"Cash To Invest: ${cash_to_invest:,.2f}")
        self._logger.info(f"Dollars Per Ticker: ${dollars_per_ticker:,.2f}")
        self._logger.info("=" * 100)

        for ticker_symbol_str in portfolio_tickers:
            try:
                market_order_request: MarketOrderRequest = MarketOrderRequest(
                    symbol=ticker_symbol_str,
                    notional=dollars_per_ticker,
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    time_in_force=TimeInForce.DAY,
                )

                market_order: Order = trading_client.submit_order(
                    order_data=market_order_request
                )

                self._logger.info(
                    f"Submitted BUY order for approximately "
                    f"${dollars_per_ticker:,.2f} of {ticker_symbol_str}."
                )

            except Exception as e:
                self._logger.error(f"Failed to initialize {ticker_symbol_str}: {e}")

        self._logger.info("=" * 100)
        self._logger.info("Portfolio initialization orders submitted.")
        self._logger.info("=" * 100)

    def _execute_daily_momentum_policy(self, trading_client: TradingClient, model_predictions_dict: dict,
                                       algorithmic_strategy_str: str, account_dict: dict[str, Any],
                                       all_positions_list: list[Position]) -> None:
        """
        Applies the daily momentum policy.

        Buy:
            if momentum > 0.05

        Sell:
            if momentum < -0.05

        Trade size:
            0.5% of total portfolio value

        Position bounds:
            minimum 2.5%
            maximum 10%
        """

        self._logger.info(f"Executing Daily Momentum Policy for: {algorithmic_strategy_str.upper()}")
        self._logger.info("=" * 100)

        portfolio_tickers: list[str] = Constants.PORTFOLIO_TICKER_SYMBOL_LIST

        portfolio_value: float = float(account_dict.get("portfolio_value") or account_dict.get("equity") or 0.0)

        cash_available: float = float(account_dict.get("cash", 0.0))

        if portfolio_value <= 0:
            self._logger.warning("Invalid portfolio value. Skipping daily momentum policy.")
            return

        trade_notional: float = portfolio_value * Constants.DAILY_TRADE_WEIGHT

        position_by_symbol_dict: dict[str, Position] = {
            position.symbol: position
            for position in all_positions_list
        }

        self._logger.info("=" * 100)
        self._logger.info("Executing Daily Momentum Policy")
        self._logger.info(f"Portfolio Value: ${portfolio_value:,.2f}")
        self._logger.info(f"Cash Available: ${cash_available:,.2f}")
        self._logger.info(f"Trade Size: ${trade_notional:,.2f}")
        self._logger.info("=" * 100)

        for ticker_symbol_str in portfolio_tickers:
            model_output_dict: dict = model_predictions_dict.get(ticker_symbol_str, {})

            if not model_output_dict:
                self._logger.warning(f"Skipping {ticker_symbol_str}: no model output found.")
                continue

            momentum_value: float = self._get_strategy_momentum_value(
                model_output_dict=model_output_dict,
                algorithmic_strategy_str=algorithmic_strategy_str,
            )

            position: Position | None = position_by_symbol_dict.get(ticker_symbol_str)

            if position is None:
                self._logger.warning(f"Skipping {ticker_symbol_str}: no current position found.")
                continue

            current_market_value: float = float(
                getattr(position, "market_value", 0.0) or 0.0
            )

            current_quantity: float = float(
                getattr(position, "qty", 0.0) or 0.0
            )

            current_price: float = float(
                getattr(position, "current_price", 0.0) or 0.0
            )

            current_weight: float = current_market_value / portfolio_value

            if momentum_value > Constants.MOMENTUM_BUY_THRESHOLD:
                self._try_submit_momentum_buy_order(
                    trading_client=trading_client,
                    ticker_symbol_str=ticker_symbol_str,
                    momentum_value=momentum_value,
                    current_weight=current_weight,
                    current_market_value=current_market_value,
                    portfolio_value=portfolio_value,
                    trade_notional=trade_notional,
                    cash_available=cash_available,
                )

            elif momentum_value < Constants.MOMENTUM_SELL_THRESHOLD:
                self._try_submit_momentum_sell_order(
                    trading_client=trading_client,
                    ticker_symbol_str=ticker_symbol_str,
                    momentum_value=momentum_value,
                    current_weight=current_weight,
                    current_market_value=current_market_value,
                    current_quantity=current_quantity,
                    current_price=current_price,
                    portfolio_value=portfolio_value,
                    trade_notional=trade_notional,
                )

            else:
                self._logger.info(
                    f"HOLD {ticker_symbol_str}: momentum={momentum_value:.4f}, "
                    f"weight={current_weight:.2%}"
                )

        self._logger.info("=" * 100)

    def _try_submit_momentum_buy_order(
            self,
            trading_client: TradingClient,
            ticker_symbol_str: str,
            momentum_value: float,
            current_weight: float,
            current_market_value: float,
            portfolio_value: float,
            trade_notional: float,
            cash_available: float,
    ) -> None:
        """
        Buys 0.5% of portfolio value if doing so will not exceed the 10% max.
        """

        max_market_value: float = (
                portfolio_value * Constants.MAX_EQUITY_WEIGHT_PER_SYMBOL
        )

        available_room_to_buy: float = max_market_value - current_market_value

        if available_room_to_buy <= 0:
            self._logger.warning(
                f"BUY BLOCKED {ticker_symbol_str}: already at or above max weight. "
                f"momentum={momentum_value:.4f}, weight={current_weight:.2%}"
            )
            return

        buy_notional: float = min(
            trade_notional,
            available_room_to_buy,
            cash_available,
        )

        if buy_notional <= 0:
            self._logger.warning(
                f"BUY BLOCKED {ticker_symbol_str}: no cash or room available. "
                f"momentum={momentum_value:.4f}"
            )
            return

        market_order_request: MarketOrderRequest = MarketOrderRequest(
            symbol=ticker_symbol_str,
            notional=buy_notional,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
        )

        trading_client.submit_order(order_data=market_order_request)

        self._logger.info(
            f"BUY {ticker_symbol_str}: ${buy_notional:,.2f}, "
            f"momentum={momentum_value:.4f}, current_weight={current_weight:.2%}"
        )

    def _try_submit_momentum_sell_order(
            self,
            trading_client: TradingClient,
            ticker_symbol_str: str,
            momentum_value: float,
            current_weight: float,
            current_market_value: float,
            current_quantity: float,
            current_price: float,
            portfolio_value: float,
            trade_notional: float,
    ) -> None:
        """
        Sells 0.5% of portfolio value if doing so will not fall below the 2.5% min.
        """

        if current_quantity <= 0:
            self._logger.warning(f"SELL BLOCKED {ticker_symbol_str}: no shares owned.")
            return

        if current_price <= 0:
            self._logger.warning(f"SELL BLOCKED {ticker_symbol_str}: invalid current price.")
            return

        min_market_value: float = (
                portfolio_value * Constants.MIN_EQUITY_WEIGHT_PER_SYMBOL
        )

        available_room_to_sell: float = current_market_value - min_market_value

        if available_room_to_sell <= 0:
            self._logger.warning(
                f"SELL BLOCKED {ticker_symbol_str}: already at or below min weight. "
                f"momentum={momentum_value:.4f}, weight={current_weight:.2%}"
            )
            return

        sell_notional: float = min(
            trade_notional,
            available_room_to_sell,
            current_market_value,
        )

        quantity_to_sell: float = sell_notional / current_price

        if quantity_to_sell <= 0:
            self._logger.warning(f"SELL BLOCKED {ticker_symbol_str}: calculated sell quantity is 0.")
            return

        if quantity_to_sell > current_quantity:
            quantity_to_sell = current_quantity

        market_order_request: MarketOrderRequest = MarketOrderRequest(
            symbol=ticker_symbol_str,
            qty=quantity_to_sell,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
        )

        trading_client.submit_order(order_data=market_order_request)

        self._logger.info(
            f"SELL {ticker_symbol_str}: {quantity_to_sell:.6f} share(s), "
            f"approx ${sell_notional:,.2f}, "
            f"momentum={momentum_value:.4f}, current_weight={current_weight:.2%}"
        )

    def _get_strategy_momentum_value(self, model_output_dict: dict, algorithmic_strategy_str: str) -> float:
        """
        Chooses which model output to trade from.

        Examples:
            BULLISH  -> bullish
            BEARISH  -> bearish
            ENSEMBLE -> ensemble

        Falls back to balanced.
        """

        strategy_key: str = algorithmic_strategy_str.lower()

        if strategy_key in model_output_dict:
            return float(model_output_dict.get(strategy_key, 0.0))

        return float(model_output_dict.get("balanced", 0.0))

    def _get_backend_market_history_proto_dict(self) -> dict:
        """
        Calls the same backend ticker endpoint for each market ticker.

        """

        market_history_dict: dict = {}

        for market_ticker in Constants.DATA_INGESTION_TICKER_SYMBOL_LIST:
            try:
                market_points: list = self._get_backend_stock_history_proto_list(
                    ticker=market_ticker
                )

                if len(market_points) < 60:
                    self._logger.warning(
                        f"Skipping market ticker {market_ticker}: backend returned only "
                        f"{len(market_points)} history rows."
                    )
                    continue

                market_history_dict[market_ticker] = momentum_pb2.OHLCVList(
                    points=market_points
                )

            except Exception as e:
                self._logger.error(f"Backend market history error for {market_ticker}: {e}")

        return market_history_dict

    def _get_backend_stock_history_proto_list(self, ticker: str) -> list:
        """
        Calls:

            GET /api/ticker?symbol={ticker}&modelType=balanced&skipMomentum=true

        Then extracts OHLCV rows from the backend TickerResponse.
        """

        url: str = self._build_backend_url(
            path="/api/ticker",
            query_params={
                "symbol": ticker,
                "modelType": "balanced",
                "skipMomentum": "true",
            },
        )

        ticker_response_json: dict = self._get_json_from_backend(url=url)
        ohlcv_rows: list[dict] = self._extract_ohlcv_rows_from_ticker_response(
            ticker_response_json=ticker_response_json
        )

        return [
            self._history_dict_to_ohlcv_proto(row)
            for row in ohlcv_rows
        ]

    def _history_dict_to_ohlcv_proto(self, row: dict) -> momentum_pb2.OHLCV:
        """
        Converts one backend history row into protobuf OHLCV.

        Supports full OHLCV rows and chart-style rows.
        """

        date_value = (
                row.get("date")
                or row.get("timestamp")
                or row.get("time")
                or row.get("datetime")
                or row.get("x")
                or row.get("label")
                or row.get("t")
                or ""
        )

        fallback_price = (
                row.get("close")
                or row.get("price")
                or row.get("value")
                or row.get("y")
                or row.get("adjClose")
                or row.get("adj_close")
                or row.get("current")
                or 0.0
        )

        open_value = row.get("open", row.get("o", fallback_price))
        high_value = row.get("high", row.get("h", fallback_price))
        low_value = row.get("low", row.get("l", fallback_price))
        close_value = row.get("close", row.get("c", fallback_price))
        volume_value = row.get("volume", row.get("v", 0.0))

        adj_close_value = (
                row.get("adj_close")
                or row.get("adjClose")
                or row.get("adjusted_close")
                or row.get("adjustedClose")
                or close_value
        )

        return momentum_pb2.OHLCV(
            date=str(date_value),
            open=float(open_value),
            high=float(high_value),
            low=float(low_value),
            close=float(close_value),
            volume=float(volume_value),
            adj_close=float(adj_close_value),
        )

    def _empty_prediction_dict(self) -> dict:
        return {
            "ensemble": 0.0,
            "balanced": 0.0,
            "bullish": 0.0,
            "bearish": 0.0,
            "high_ic": 0.0,
            "signals": [],
        }

    def _get_backend_tweets_list(self, ticker: str) -> list[str]:
        """
        Calls:

            GET /api/momentum/feed/{ticker}

        Your Java controller returns a raw JSON string from StockTwitsService,
        so this method handles either:
            - a JSON string
            - a JSON object
            - a list of messages
        """

        safe_ticker: str = urllib.parse.quote(ticker)
        url: str = f"{Constants.BACKEND_BASE_URL}/api/momentum/feed/{safe_ticker}"

        try:
            feed_json: Any = self._get_json_from_backend(url=url)
        except Exception as e:
            self._logger.error(f"Tweet feed error for {ticker}: {e}")
            return []

        return self._extract_tweet_texts(feed_json=feed_json)

    def _build_backend_url(self, path: str, query_params: dict[str, str]) -> str:
        base_url: str = Constants.BACKEND_BASE_URL.rstrip("/")
        encoded_query: str = urllib.parse.urlencode(query_params)

        return f"{base_url}{path}?{encoded_query}"

    def _get_json_from_backend(self, url: str) -> Any:
        with urllib.request.urlopen(url, timeout=30) as response:
            raw_body: str = response.read().decode("utf-8")

        return json.loads(raw_body)

    def _extract_ohlcv_rows_from_ticker_response(
            self,
            ticker_response_json: dict,
    ) -> list[dict]:
        """
        Extracts historical rows from the Java backend TickerResponse.

        Handles:
            graphData: [...]
            graphData: {"points": [...]}
            graphData: {"data": [...]}
            momentumHistory: [...]
            momentumHistory: {"points": [...]}
        """

        for top_level_key in ["graphData", "momentumHistory"]:
            value = ticker_response_json.get(top_level_key)

            rows = self._extract_rows_from_any_history_shape(value)

            if rows:
                return rows

        possible_history_keys: list[str] = [
            "history",
            "stockHistory",
            "stock_history",
            "ohlcv",
            "ohlcvHistory",
            "prices",
            "priceHistory",
            "data",
        ]

        for key in possible_history_keys:
            value = ticker_response_json.get(key)

            rows = self._extract_rows_from_any_history_shape(value)

            if rows:
                return rows

        self._logger.info(
            "Could not find OHLCV rows in backend response keys: "
            f"{ticker_response_json.keys()}"
        )

        self._logger.info("graphData type:", type(ticker_response_json.get("graphData")))
        self._logger.info("graphData value:", ticker_response_json.get("graphData"))

        self._logger.info("momentumHistory type:", type(ticker_response_json.get("momentumHistory")))
        self._logger.info("momentumHistory value:", ticker_response_json.get("momentumHistory"))

        return []

    def _extract_rows_from_any_history_shape(self, value) -> list[dict]:
        """
        Recursively extracts a list[dict] from common backend response shapes.
        """

        if value is None:
            return []

        if isinstance(value, list):
            if not value:
                return []

            if all(isinstance(item, dict) for item in value):
                return value

            return []

        if isinstance(value, dict):
            for nested_key in [
                "points",
                "rows",
                "items",
                "values",
                "data",
                "history",
                "prices",
                "graphData",
                "momentumHistory",
            ]:
                nested_value = value.get(nested_key)

                rows = self._extract_rows_from_any_history_shape(nested_value)

                if rows:
                    return rows

        return []

    def _extract_tweet_texts(self, feed_json: Any) -> list[str]:
        """
        Extracts text bodies from common StockTwits-style JSON shapes.
        """

        tweets: list[str] = []

        if isinstance(feed_json, list):
            candidate_messages = feed_json

        elif isinstance(feed_json, dict):
            candidate_messages = (
                    feed_json.get("messages")
                    or feed_json.get("data")
                    or feed_json.get("feed")
                    or feed_json.get("items")
                    or []
            )

        else:
            return []

        if not isinstance(candidate_messages, list):
            return []

        for message in candidate_messages:
            if isinstance(message, str):
                text = message.strip()

            elif isinstance(message, dict):
                text = str(
                    message.get("body")
                    or message.get("text")
                    or message.get("message")
                    or ""
                ).strip()

            else:
                text = ""

            if text:
                tweets.append(text)

        return tweets
