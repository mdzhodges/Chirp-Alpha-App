import asyncio
import json
import math
import os as _os
import queue
import random
import sys
import urllib.request
from asyncio import Task
from collections import deque
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from alpaca.data.live import StockDataStream
from alpaca.trading import Position
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce, OrderType
from alpaca.trading.models import Order
from alpaca.trading.requests import MarketOrderRequest

import grpc as _grpc  # must be imported before sys.path is modified
sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '../../grpc')))
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

            print("=" * 100)
            print(f"Executing Trading Algorithm: {algorithmic_strategy_str}")
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

                data_stream.subscribe_bars(self._handle_bar, *Constants.TICKER_SYMBOL_LIST)
                stream_task: Task = asyncio.create_task(asyncio.to_thread(data_stream.run))

                if self._current_time_est < self._close_of_market_time:
                    account_dict: dict[str, Any] = alpaca_trading_portfolio.get_account_dict()
                    all_positions_list: list[Position] = trading_client.get_all_positions()

                    all_positions_list = trading_client.get_all_positions()

                    state_data_dict: dict = await asyncio.to_thread(self._bar_queue.get)

                    portfolio_cash: float = account_dict.get("cash", 0.0)
                    portfolio_equity: float = account_dict.get("equity", 0.0)
                    current_datetime: datetime = datetime.now().astimezone(ZoneInfo("America/New_York"))

                    print(
                        f"Timestamp: {current_datetime.time()} -> Portfolio Equity: {portfolio_equity:,.2f} -> Portfolio Cash Available: ${portfolio_cash:,.2f}")
                    print(f"state_data_dict = {state_data_dict}")
                    print("=" * 150)

                    model_predictions_dict: dict = self._get_model_predictions_dict()

                    # self.execute_market_orders(trading_client=trading_client,
                    #                            model_predictions_dict=model_predictions_dict)

                await stream_task

            except Exception as e:
                print(f"Exception Thrown: {e}")

    def _execute_bullish_trading_algorithm(self) -> None:
        pass

    def _execute_balanced_trading_algorithm(self) -> None:
        pass

    def _execute_bearish_trading_algorithm(self) -> None:
        pass

    def _get_model_predictions_dict(self) -> dict:
        """
        Returns { ticker: { "bullish": float, "bearish": float, "balanced": float, "signals": list } }
        """
        model_predictions_dict: dict = {}

        for ticker in Constants.TICKER_SYMBOL_LIST:
            outputs = self._fetch_ticker_model_outputs(ticker)
            if outputs:
                model_predictions_dict[ticker] = outputs

        return model_predictions_dict

    def _fetch_ticker_model_outputs(self, ticker: str) -> dict:
        """
        Calls GET /api/ticker/momentum?symbol={ticker}&modelType={model} for each of
        bullish, bearish, and balanced, returning:
            { "bullish": float, "bearish": float, "balanced": float, "signals": list }
        """
        results = {}
        for model_type in ("bullish", "bearish", "balanced"):
            url = f"{Constants.BACKEND_BASE_URL}/api/ticker/momentum?symbol={ticker}&modelType={model_type}"
            try:
                with urllib.request.urlopen(url, timeout=30) as resp:
                    data = json.loads(resp.read())
                results[model_type] = float(data.get("current", 0.0))
                if model_type == "balanced":
                    results["signals"] = data.get("signals", [])
            except Exception as e:
                print(f"Backend error [{model_type}] for {ticker}: {e}")
                results[model_type] = 0.0

        results.setdefault("signals", [])
        return results

    def execute_market_orders(self, trading_client: TradingClient, model_predictions_dict: dict) -> None:

        try:

            for ticker_symbol_str, ticker_symbol_tuple in model_predictions_dict.items():

                stock_quantity: int = ticker_symbol_tuple[0]
                stock_price: float = float(ticker_symbol_tuple[1])
                stock_action: OrderSide = ticker_symbol_tuple[2]

                if stock_quantity <= 0 and stock_action == OrderSide.SELL:
                    # TODO: Add logger statement for this occurrence
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

    # TODO: Change this from 'random' to the weights of the model predictions
    def _get_random_quantity_per_symbol_dict(self, account_dict: dict[str, Any], all_positions_list: list, ) -> dict[
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

    def _is_sell_side_order(self, order_side: OrderSide, random_quantity_dict: dict[str, tuple[int, float, OrderSide]],
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

    def _is_buy_side_order(self, order_side: OrderSide, random_quantity_dict: dict[str, tuple[int, float, OrderSide]],
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
