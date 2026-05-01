import asyncio
import math
import os
import queue
import random
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

from Model.trading_account.alpaca_trading_portfolio import AlpacaTradingPortfolio
from Model.utils.constants import Constants


# TODO: The portfolio will be equally weighted, remove 'random' logic from below
class AlpacaAlgoTradingImplementation:

    def __init__(self) -> None:
        self._bar_queue: queue.Queue[dict] = queue.Queue()
        self._bar_history: deque[dict] = deque(maxlen=5000)
        self._alpaca_api_key = os.getenv("ALPACA_API_KEY", "")
        self._alpaca_api_key_secret = os.getenv("ALPACA_API_KEY_SECRET", "")
        self._close_of_market_time: time = time(16, 0)

        self._trading_client: TradingClient = TradingClient(api_key=self._alpaca_api_key,
                                                            secret_key=self._alpaca_api_key_secret, paper=True)
        self._alpaca_trading_portfolio: AlpacaTradingPortfolio = AlpacaTradingPortfolio(
            trading_client=self._trading_client)

    async def _handle_bar(self, data) -> None:
        bar_dict: dict = data.model_dump()

        self._latest_bar_dict = bar_dict
        self._bar_history.append(bar_dict)

        self._bar_queue.put(bar_dict)

    async def execute_trading_algorithm(self) -> None:

        data_stream: StockDataStream = StockDataStream(api_key=self._alpaca_api_key,
                                                       secret_key=self._alpaca_api_key_secret)
        print("=" * 100)
        print("Initializing Trading Environment")

        try:

            data_stream.subscribe_bars(self._handle_bar, *Constants.TICKER_SYMBOL_LIST)
            stream_task: Task = asyncio.create_task(asyncio.to_thread(data_stream.run))

            current_time_step: int = 1

            while True:

                account_dict: dict[str, Any] = self._alpaca_trading_portfolio.get_account_dict()
                all_positions_list: list[Position] = self._trading_client.get_all_positions()

                all_positions_list = self._trading_client.get_all_positions()

                state_data_dict: dict = await asyncio.to_thread(self._bar_queue.get)

                random_action: OrderSide | str = self._get_random_order_side_action()

                if random_action != "HOLD":
                    portfolio_cash: float = account_dict.get("cash", 0.0)
                    portfolio_equity: float = account_dict.get("equity", 0.0)
                    current_datetime: datetime = datetime.now().astimezone(ZoneInfo("America/New_York"))

                    print(
                        f"Timestep: {current_time_step} -> Timestamp: {current_datetime.time()} -> Portfolio Equity: {portfolio_equity:,.2f} -> Portfolio Cash Available: ${portfolio_cash:,.2f}")
                    print("=" * 150)

                else:
                    print(f"Action Selected -> {random_action}")
                    continue

                portfolio_dict: dict[
                    str, tuple[int, float, OrderSide]] = self._get_random_quantity_per_symbol_dict(
                    account_dict=account_dict,
                    all_positions_list=all_positions_list)

                self.execute_market_orders(portfolio_dict=portfolio_dict)

                current_time_est: time = datetime.now().astimezone(ZoneInfo("America/New_York")).time()

                if current_time_est >= self._close_of_market_time:
                    print(f"Broken at timestep: {current_time_step}")
                    print("=" * 200)
                    break

                current_time_step += 1

            await stream_task

        except Exception as e:
            print(f"Exception Thrown: {e}")

    def execute_market_orders(self, portfolio_dict: dict[str, tuple[int, float, OrderSide]]) -> None:

        try:

            for ticker_symbol_str, ticker_symbol_tuple in portfolio_dict.items():

                stock_quantity: int = ticker_symbol_tuple[0]
                stock_price: float = float(ticker_symbol_tuple[1])
                stock_action: OrderSide = ticker_symbol_tuple[2]

                if stock_quantity <= 0 and stock_action == OrderSide.SELL:
                    continue

                market_order_request: MarketOrderRequest = MarketOrderRequest(
                    symbol=ticker_symbol_str,
                    qty=stock_quantity,
                    side=stock_action,
                    order_type=OrderType.MARKET,
                    time_in_force=TimeInForce.DAY
                )

                market_order: Order = self._trading_client.submit_order(
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
