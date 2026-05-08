import os
from typing import Any

import dotenv
from alpaca.trading import Position
from alpaca.trading.client import TradingClient

from Model.utils.constants import Constants

dotenv.load_dotenv()


class AlpacaTradingPortfolio:

    def __init__(self, trading_client: TradingClient) -> None:
        self._trading_client: TradingClient = trading_client


    def get_account_dict(self) -> dict[str, Any]:

        account_dict: dict[str, Any] = self._trading_client.get_account().model_dump()

        result_dict: dict[str, Any] = {

            "cash": float(account_dict.get("cash", 0.0)),
            "equity": float(account_dict.get("equity", 0.0)),
            "buying_power": float(account_dict.get("buying_power", 0.0)),
            "portfolio_value": float(account_dict.get("portfolio_value", 0.0)),
            "daytrading_buying_power": float(account_dict.get("daytrading_buying_power", 0.0))

        }

        return result_dict

    def _get_positions_dict(self, all_positions_list: list[Position], account_dict: dict[str, float]) -> dict[
        str, dict[str, float]]:

        positions_dict: dict[str, dict[str, float]] = {}

        self._populate_missing_ticker_entries(all_positions_list=all_positions_list, account_dict=account_dict,
                                              positions_dict=positions_dict)

        for position_obj in all_positions_list:
            ticker_symbol_str: str = position_obj.symbol

            cash: float = account_dict.get("cash", 0.0)
            buying_power: float = account_dict.get("buying_power", 0.0)
            portfolio_value: float = account_dict.get("portfolio_value", 0.0)

            market_value: float = float(position_obj.market_value)
            qty_available: float = float(position_obj.qty_available)

            cash_to_portfolio_value: float = cash / portfolio_value
            portfolio_weight: float = market_value / portfolio_value
            buying_power_to_portfolio_value: float = buying_power / portfolio_value
            cost_basis_to_portfolio_value: float = float(position_obj.cost_basis) / portfolio_value
            unrealized_pl_to_portfolio_value: float = float(position_obj.unrealized_pl) / portfolio_value

            ticker_dict: dict[str, float] = {
                "qty_available": qty_available,
                "portfolio_value": portfolio_value,
                "portfolio_weight": portfolio_weight,
                "cash_to_portfolio_value": cash_to_portfolio_value,
                "cost_basis_to_portfolio_value": cost_basis_to_portfolio_value,
                "buying_power_to_portfolio_value": buying_power_to_portfolio_value,
                "unrealized_pl_to_portfolio_value": unrealized_pl_to_portfolio_value,
                "change_today": float(position_obj.change_today),
            }

            positions_dict[ticker_symbol_str] = ticker_dict

        return positions_dict

    def _populate_missing_ticker_entries(self, all_positions_list: list[Position], account_dict: dict[str, float],
                                         positions_dict: dict[str, dict[str, float]]) -> None:

        full_ticker_symbol_list: list[str] = Constants.DATA_INGESTION_TICKER_SYMBOL_LIST
        positions_str_list: list[str] = self._get_positions_str_list(all_positions_list=all_positions_list)

        for ticker_symbol_str in full_ticker_symbol_list:

            if ticker_symbol_str not in positions_str_list:
                cash: float = account_dict.get("cash", 0.0)
                buying_power: float = account_dict.get("buying_power", 0.0)
                portfolio_value: float = account_dict.get("portfolio_value", 0.0)

                cash_to_portfolio_value: float = cash / portfolio_value
                buying_power_to_portfolio_value: float = buying_power / portfolio_value

                ticker_dict: dict[str, float] = {
                    "qty_available": 0.0,
                    "position_value": 0.0,
                    "portfolio_weight": 0.0,
                    "portfolio_value": portfolio_value,
                    "cost_basis_to_portfolio_value": 0.0,
                    "unrealized_pl_to_portfolio_value": 0.0,
                    "cash_to_portfolio_value": cash_to_portfolio_value,
                    "buying_power_to_portfolio_value": buying_power_to_portfolio_value,
                    "change_today": 0.0,
                }

                positions_dict[ticker_symbol_str] = ticker_dict

    def _get_positions_str_list(self, all_positions_list: list[Position]) -> list[str]:
        positions_str_list: list[str] = [x.symbol for x in all_positions_list]
        return positions_str_list
