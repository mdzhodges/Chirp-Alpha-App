import asyncio
import importlib
import json
import math
import os as _os
import queue
import random
import sys
import urllib.parse
import urllib.request
from asyncio import Task
from collections import deque
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from alpaca.data.live import StockDataStream
from alpaca.trading import Position, MarketOrderRequest, Order
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce

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

        model_predictions_dict: dict = self._get_model_predictions_dict()

        for key, value in model_predictions_dict.items():
            print(f"key = {key} -> value = {value}")

        for algorithmic_strategy_str, api_key_tuple in self._algorithmic_trading_credentials_dict.items():
            alpaca_api_key: str = api_key_tuple[0]
            alpaca_api_key_secret: str = api_key_tuple[1]

            print("=" * 100)
            print(f"Executing Trading Algorithm: {algorithmic_strategy_str.upper()}")
            print("=" * 100)

            alpaca_api_key = alpaca_api_key
            alpaca_api_key_secret = alpaca_api_key_secret

            trading_client: TradingClient = TradingClient(api_key=alpaca_api_key,
                                                          secret_key=alpaca_api_key_secret,
                                                          paper=True)

            alpaca_trading_portfolio: AlpacaTradingPortfolio = AlpacaTradingPortfolio(trading_client=trading_client)

            data_stream: StockDataStream = StockDataStream(api_key=alpaca_api_key,
                                                           secret_key=alpaca_api_key_secret)

            try:

                data_stream.subscribe_bars(self._handle_bar, *Constants.PORTFOLIO_TICKER_SYMBOL_LIST)
                stream_task: Task = asyncio.create_task(asyncio.to_thread(data_stream.run))

                if self._current_time_est < self._close_of_market_time:
                    account_dict: dict[str, Any] = alpaca_trading_portfolio.get_account_dict()
                    all_positions_list: list[Position] = trading_client.get_all_positions()

                    self._initialize_portfolio_holdings(trading_client=trading_client,
                                                        account_dict=account_dict,
                                                        all_positions_list=all_positions_list)

                    all_positions_list = trading_client.get_all_positions()

                    state_data_dict: dict = await asyncio.to_thread(self._bar_queue.get)

                    portfolio_cash: float = account_dict.get("cash", 0.0)
                    portfolio_equity: float = account_dict.get("equity", 0.0)
                    current_datetime: datetime = datetime.now().astimezone(ZoneInfo("America/New_York"))

                    print(
                        f"Timestamp: {current_datetime.time()} -> Portfolio Equity: {portfolio_equity:,.2f} -> Portfolio Cash Available: ${portfolio_cash:,.2f}")
                    print("=" * 150)

                    quantity_by_ticker_dict: dict[
                        str, tuple[int, float, OrderSide]] = self._get_quantity_by_ticker_dict(
                        account_dict=account_dict, all_positions_list=all_positions_list)

                    for key, value in quantity_by_ticker_dict.items():
                        print(f"key = {key} -> value = {value}")

                    # TODO: Stopped here, keep implementing

                    exit()
                    # self.execute_market_orders(trading_client=trading_client,
                    #                            model_predictions_dict=model_predictions_dict,
                    #                            algorithmic_strategy_str=algorithmic_strategy_str)

                await stream_task

            except Exception as e:
                print(f"Exception Thrown: {e}")

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
            print("No market history returned from backend.")
            return model_predictions_dict

        for ticker in Constants.DATA_INGESTION_TICKER_SYMBOL_LIST:
            try:
                stock_history_list: list = self._get_backend_stock_history_proto_list(ticker=ticker)
                tweets_list: list[str] = self._get_backend_tweets_list(ticker=ticker)

                if len(stock_history_list) < 60:
                    print(
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
                    offset=0,
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
                print(f"gRPC error for {ticker}: {e.code()} - {e.details()}")
                model_predictions_dict[ticker] = self._empty_prediction_dict()

            except Exception as e:
                print(f"Prediction error for {ticker}: {e}")
                model_predictions_dict[ticker] = self._empty_prediction_dict()

        return model_predictions_dict

    def _get_quantity_by_ticker_dict(self, account_dict: dict[str, Any], all_positions_list: list, ) -> \
            dict[
                str, tuple[int, float, OrderSide]]:

        current_cash_t: float = float(account_dict.get("cash", 0.0))
        random_quantity_dict: dict[str, tuple[int, float, OrderSide]] = {}

        for stock_position in all_positions_list:
            order_side: OrderSide = random.choice(Constants.ORDER_SIDE_ACTIONS_LIST)
            is_buy_side: bool = order_side == OrderSide.BUY
            is_sell_side: bool = order_side == OrderSide.SELL

            if is_sell_side:
                self._is_sell_side_order(order_side=order_side, random_quantity_dict=random_quantity_dict,
                                         stock_position=stock_position)
            elif is_buy_side:
                self._is_buy_side_order(order_side=order_side, random_quantity_dict=random_quantity_dict,
                                        stock_position=stock_position, current_cash_t=current_cash_t)

        return random_quantity_dict

    def _is_sell_side_order(self, order_side: OrderSide,
                            random_quantity_dict: dict[str, tuple[int, float, OrderSide]],
                            stock_position: Position) -> None:

        ticker_symbol_str: str = stock_position.symbol
        stock_quantity: int = int(stock_position.qty_available)
        stock_price: float = float(stock_position.current_price)

        max_valid_quantity: int = stock_quantity

        if max_valid_quantity <= 0:
            random_quantity_dict[ticker_symbol_str] = (0, stock_price, order_side)
            return

        random_quantity: int = math.ceil(random.randint(1, max_valid_quantity) / 2)
        random_quantity_dict[ticker_symbol_str] = (random_quantity, stock_price, order_side)
        return

    def _is_buy_side_order(self, order_side: OrderSide,
                           random_quantity_dict: dict[str, tuple[int, float, OrderSide]],
                           stock_position: Position, current_cash_t: float) -> None:

        ticker_symbol_str: str = stock_position.symbol
        stock_price: float = float(stock_position.current_price)

        max_valid_quantity = int(current_cash_t // stock_price)

        if self._is_max_quantity_less_or_equal_to_zero(order_side=order_side,
                                                       random_quantity_dict=random_quantity_dict,
                                                       stock_position=stock_position,
                                                       current_cash_t=current_cash_t,
                                                       max_valid_quantity=max_valid_quantity):
            return

        random_quantity = math.ceil(random.randint(1, max_valid_quantity) / 2)

        if self._is_transaction_cost_greater_than_cash_available(order_side=order_side,
                                                                 random_quantity_dict=random_quantity_dict,
                                                                 stock_position=stock_position,
                                                                 current_cash_t=current_cash_t,
                                                                 random_quantity=random_quantity):
            return

        random_quantity_dict[ticker_symbol_str] = (random_quantity, stock_price, order_side)

    def _is_transaction_cost_greater_than_cash_available(self, order_side: OrderSide, random_quantity_dict: dict[
        str, tuple[int, float, OrderSide]], stock_position: Position, current_cash_t: float,
                                                         random_quantity: int) -> bool:

        ticker_symbol_str: str = stock_position.symbol
        stock_price: float = float(stock_position.current_price)

        transaction_cost: float = stock_price * random_quantity
        if transaction_cost > current_cash_t:
            random_quantity_dict[ticker_symbol_str] = (0, stock_price, order_side)
            print(
                f"Invalid {order_side.name} of {random_quantity:,} share(s) of {ticker_symbol_str}:"
            )
            print(
                f"Quantity -> {random_quantity}, Transaction Cost ->${transaction_cost:,.2f} exceeds Cash On Hand ->${current_cash_t:,.2f}")
            return True

        return False

    def _is_max_quantity_less_or_equal_to_zero(self, order_side: OrderSide, random_quantity_dict: dict[
        str, tuple[int, float, OrderSide]], stock_position: Position, current_cash_t: float,
                                               max_valid_quantity: int) -> bool:

        ticker_symbol_str: str = stock_position.symbol
        stock_quantity: int = int(stock_position.qty_available)
        stock_price: float = float(stock_position.current_price)

        if max_valid_quantity <= 0:
            random_quantity_dict[ticker_symbol_str] = (0, stock_price, order_side)
            transaction_cost: float = stock_price * max_valid_quantity
            print(
                f"Invalid {order_side.name} of {stock_quantity:,} share(s) of {ticker_symbol_str}:"
            )
            print(
                f"Cash On Hand -> ${current_cash_t:,.2f}, Current Stock Price -> ${stock_price:,.2f}, Transaction Cost -> ${transaction_cost:,.2f}")
            return True

        return False

    def _get_stock_quantity(self, dollars_to_invest: float, stock_price: float) -> float:
        """
        Returns the number of shares to buy for one ticker.

        Example:
            dollars_to_invest = 5000
            stock_price = 250

            quantity = 20 shares
        """

        if dollars_to_invest <= 0:
            return 0.0

        if stock_price <= 0:
            return 0.0

        return dollars_to_invest / stock_price

    def _initialize_portfolio_holdings(
            self,
            trading_client: TradingClient,
            account_dict: dict[str, Any],
            all_positions_list: list[Position],
    ) -> None:
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
            print("No portfolio tickers configured. Skipping portfolio initialization.")
            return

        if self._is_portfolio_already_initialized(
                account_dict=account_dict,
                all_positions_list=all_positions_list,
                portfolio_tickers=portfolio_tickers,
        ):
            print("Portfolio already appears initialized. Skipping initial buys.")
            return

        portfolio_value: float = float(
            account_dict.get("portfolio_value")
            or account_dict.get("equity")
            or 0.0
        )

        cash_available: float = float(account_dict.get("cash", 0.0))

        if portfolio_value <= 0:
            print("Invalid portfolio value. Skipping portfolio initialization.")
            return

        if cash_available <= 0:
            print("No cash available. Skipping portfolio initialization.")
            return

        target_cash_amount: float = portfolio_value * Constants.TARGET_CASH_PERCENT
        target_equity_amount: float = portfolio_value * Constants.TARGET_EQUITY_PERCENT

        cash_to_invest: float = cash_available - target_cash_amount

        if cash_to_invest <= 0:
            print(
                f"Cash available ${cash_available:,.2f} is already at or below "
                f"target cash amount ${target_cash_amount:,.2f}. Skipping initialization."
            )
            return

        dollars_per_ticker: float = cash_to_invest / len(portfolio_tickers)

        print("=" * 100)
        print("Initializing Portfolio Holdings")
        print(f"Portfolio Value: ${portfolio_value:,.2f}")
        print(f"Cash Available: ${cash_available:,.2f}")
        print(f"Target Cash: ${target_cash_amount:,.2f}")
        print(f"Cash To Invest: ${cash_to_invest:,.2f}")
        print(f"Dollars Per Ticker: ${dollars_per_ticker:,.2f}")
        print("=" * 100)

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

                print(
                    f"Submitted BUY order for approximately "
                    f"${dollars_per_ticker:,.2f} of {ticker_symbol_str}."
                )

            except Exception as e:
                print(f"Failed to initialize {ticker_symbol_str}: {e}")

        print("=" * 100)
        print("Portfolio initialization orders submitted.")
        print("=" * 100)

    def _is_portfolio_already_initialized(
            self,
            account_dict: dict[str, Any],
            all_positions_list: list[Position],
            portfolio_tickers: list[str],
    ) -> bool:
        """
        Returns True if the live portfolio already looks like the intended
        initialized portfolio.

        Checks:
            1. Cash is approximately 50% of portfolio value.
            2. Every target ticker has an open position.
            3. No target position has a zero or negative market value.
        """

        portfolio_value: float = float(
            account_dict.get("portfolio_value")
            or account_dict.get("equity")
            or 0.0
        )

        cash: float = float(account_dict.get("cash", 0.0))

        if portfolio_value <= 0:
            return False

        current_cash_percent: float = cash / portfolio_value
        target_cash_percent: float = Constants.TARGET_CASH_PERCENT
        tolerance_percent: float = Constants.PORTFOLIO_INITIALIZATION_TOLERANCE_PERCENT

        lower_cash_bound: float = target_cash_percent - tolerance_percent
        upper_cash_bound: float = target_cash_percent + tolerance_percent

        is_cash_balanced: bool = (
                lower_cash_bound <= current_cash_percent <= upper_cash_bound
        )

        position_by_symbol_dict: dict[str, Position] = {
            position.symbol: position
            for position in all_positions_list
        }

        missing_tickers: list[str] = [
            ticker
            for ticker in portfolio_tickers
            if ticker not in position_by_symbol_dict
        ]

        if missing_tickers:
            print(f"Portfolio is not initialized. Missing positions: {missing_tickers}")
            return False

        for ticker in portfolio_tickers:
            position: Position = position_by_symbol_dict[ticker]

            market_value: float = float(getattr(position, "market_value", 0.0) or 0.0)
            quantity: float = float(getattr(position, "qty", 0.0) or 0.0)

            if market_value <= 0 or quantity <= 0:
                print(
                    f"Portfolio is not initialized. Invalid position for {ticker}: "
                    f"qty={quantity}, market_value={market_value}"
                )
                return False

        if not is_cash_balanced:
            print(
                "Portfolio has all target holdings, but cash is not near target. "
                f"Current cash percent: {current_cash_percent:.2%}, "
                f"target: {target_cash_percent:.2%}"
            )
            return False

        return True

    def _get_latest_stock_price(self, ticker: str) -> float:
        """
        Gets the latest stock price from the Java backend.
        """

        url: str = self._build_backend_url(
            path="/api/ticker",
            query_params={
                "symbol": ticker,
                "modelType": "balanced",
                "skipMomentum": "true",
            },
        )

        ticker_json: dict = self._get_json_from_backend(url=url)

        stock_price: float = float(
            ticker_json.get("price")
            or ticker_json.get("regularMarketPrice")
            or ticker_json.get("currentPrice")
            or 0.0
        )

        return stock_price

    def execute_market_orders(self, trading_client: TradingClient, model_predictions_dict: dict,
                              algorithmic_strategy_str: str) -> None:

        try:

            for ticker_symbol_str, model_output_dict in model_predictions_dict.items():

                #
                # if algorithmic_strategy_str.lower() == model_output_dict.get(algorithmic_strategy_str_lower_case):
                #     momentum_value: float = model_output_dict.get(algorithmic_strategy_str_lower_case)

                # TODO: Change all these values 3 values
                stock_quantity: float = 0.0
                stock_action: OrderSide = OrderSide.BUY
                stock_price: float = 0.0

                if stock_quantity <= 0 and stock_action == OrderSide.SELL:
                    print(f"Stock Quantity: {stock_quantity} and Action: {stock_action}")
                    continue

                market_order_request: MarketOrderRequest = MarketOrderRequest(
                    symbol=ticker_symbol_str,
                    qty=stock_quantity,
                    side=stock_action,
                    order_type=OrderType.MARKET,
                    time_in_force=TimeInForce.DAY
                )

                market_order: Order = trading_client.submit_order(
                    order_data=market_order_request
                )

                market_order_qty_int: int = int(market_order.qty)

                print(
                    f"Successfully {market_order.side.name} {market_order_qty_int} share(s) of {market_order.symbol} @ ${stock_price:,.2f} for ${stock_price * market_order_qty_int:,.2f}")

            print("=" * 100)

        except Exception as e:
            print(f"Exception Thrown: {e}")

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
                    print(
                        f"Skipping market ticker {market_ticker}: backend returned only "
                        f"{len(market_points)} history rows."
                    )
                    continue

                market_history_dict[market_ticker] = momentum_pb2.OHLCVList(
                    points=market_points
                )

            except Exception as e:
                print(f"Backend market history error for {market_ticker}: {e}")

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
            print(f"Tweet feed error for {ticker}: {e}")
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

        print(
            "Could not find OHLCV rows in backend response keys: "
            f"{ticker_response_json.keys()}"
        )

        print("graphData type:", type(ticker_response_json.get("graphData")))
        print("graphData value:", ticker_response_json.get("graphData"))

        print("momentumHistory type:", type(ticker_response_json.get("momentumHistory")))
        print("momentumHistory value:", ticker_response_json.get("momentumHistory"))

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

    def _build_market_history_proto_dict(self) -> dict:
        """
        Converts stored market/index bars into:
            {
                "SPY": momentum_pb2.OHLCVList(...),
                "QQQ": momentum_pb2.OHLCVList(...),
                ...
            }

        Your gRPC service expects market_history to be a map<string, OHLCVList>.
        """

        market_history_dict: dict = {}

        for market_ticker in Constants.DATA_INGESTION_TICKER_SYMBOL_LIST:
            points: list = []

            for bar_dict in self._bar_history:
                bar_symbol = bar_dict.get("symbol") or bar_dict.get("ticker") or bar_dict.get("S")

                if bar_symbol != market_ticker:
                    continue

                points.append(self._bar_dict_to_ohlcv_proto(bar_dict))

            if points:
                market_history_dict[market_ticker] = momentum_pb2.OHLCVList(points=points)

        return market_history_dict

    def _bar_dict_to_ohlcv_proto(self, bar_dict: dict) -> momentum_pb2.OHLCV:
        """
        Converts one Alpaca bar dictionary into the OHLCV protobuf message.
        """

        raw_timestamp = (
                bar_dict.get("timestamp")
                or bar_dict.get("time")
                or bar_dict.get("t")
                or ""
        )

        return momentum_pb2.OHLCV(
            date=str(raw_timestamp),
            open=float(bar_dict.get("open", bar_dict.get("o", 0.0))),
            high=float(bar_dict.get("high", bar_dict.get("h", 0.0))),
            low=float(bar_dict.get("low", bar_dict.get("l", 0.0))),
            close=float(bar_dict.get("close", bar_dict.get("c", 0.0))),
            volume=float(bar_dict.get("volume", bar_dict.get("v", 0.0))),
            adj_close=float(
                bar_dict.get(
                    "adj_close",
                    bar_dict.get("close", bar_dict.get("c", 0.0)),
                )
            ),
        )
