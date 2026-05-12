import asyncio

import dotenv

from Model.trading_account.alpaca_algo_trading import AlpacaAlgoTrading
from Model.trading_account.alpaca_algo_trading_implementation import AlpacaAlgoTradingImplementation

dotenv.load_dotenv()


async def main() -> int:
    try:

        alpaca_algo_trading: AlpacaAlgoTrading = AlpacaAlgoTrading()

        alpaca_algo_trading_credentials_dict: dict[
            str, tuple[str, str]] = alpaca_algo_trading.get_alpaca_algo_trading_credentials_dict()

        alpaca_algo_trading_implementation: AlpacaAlgoTradingImplementation = AlpacaAlgoTradingImplementation(
            alpaca_algo_trading_credentials_dict=alpaca_algo_trading_credentials_dict)

        await alpaca_algo_trading_implementation.execute_trading_algorithm()

        return 0

    except Exception as e:
        print(f"Exception Thrown: {e}")
        return -1


if __name__ == "__main__":
    asyncio.run(main())
