import os

import dotenv

from Model.utils.constants import Constants

dotenv.load_dotenv()


class AlpacaAlgoTrading:

    def __init__(self) -> None:
        pass

    def get_alpaca_algo_trading_credentials_dict(self) -> dict[str, tuple[str, str]]:
        alpaca_bullish_api_key: str = os.getenv(Constants.ALPACA_BULLISH_API_KEY, "")
        alpaca_bullish_api_key_secret: str = os.getenv(Constants.ALPACA_BULLISH_API_KEY_SECRET, "")

        alpaca_ensemble_api_key: str = os.getenv(Constants.ALPACA_ENSEMBLE_API_KEY, "")
        alpaca_ensemble_api_key_secret: str = os.getenv(Constants.ALPACA_ENSEMBLE_API_KEY_SECRET, "")

        alpaca_bearish_api_key: str = os.getenv(Constants.ALPACA_BEARISH_API_KEY, "")
        alpaca_bearish_api_key_secret: str = os.getenv(Constants.ALPACA_BEARISH_API_KEY_SECRET, "")

        alpaca_algo_trading_strategy_dict: dict[str, tuple[str, str]] = {
            Constants.BULLISH_STR: (alpaca_bullish_api_key, alpaca_bullish_api_key_secret),
            Constants.ENSEMBLE_STR: (alpaca_ensemble_api_key, alpaca_ensemble_api_key_secret),
            Constants.BEARISH_STR: (alpaca_bearish_api_key, alpaca_bearish_api_key_secret),
        }

        return alpaca_algo_trading_strategy_dict
