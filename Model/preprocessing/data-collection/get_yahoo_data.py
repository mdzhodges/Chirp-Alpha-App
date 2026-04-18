import os
from pathlib import Path

import pandas as pd
import yfinance as yf


def infer_stock_date_range(stock_dir: str = "data/stock_data") -> tuple[str, str]:
    """
    Infer min/max date bounds from local stock CSV files.
    """
    root = Path(stock_dir)
    files = sorted(root.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No stock CSV files found in {stock_dir}")

    min_date = None
    max_date = None

    for path in files:
        try:
            d = pd.read_csv(path, usecols=["date"])
        except Exception:
            continue
        if d.empty:
            continue

        dt = pd.to_datetime(d["date"], errors="coerce").dropna()
        if dt.empty:
            continue

        lo = dt.min().date()
        hi = dt.max().date()
        min_date = lo if min_date is None else min(min_date, lo)
        max_date = hi if max_date is None else max(max_date, hi)

    if min_date is None or max_date is None:
        raise ValueError("Could not infer date range from stock CSVs.")

    return min_date.isoformat(), max_date.isoformat()


def download_market_indices() -> None:
    # Broad, Tech, Blue Chip, and Volatility index proxies.
    tickers = ["SPY", "QQQ", "DIA", "^VIX"]

    start_date, end_date = infer_stock_date_range("data/stock_data")
    # yfinance end date is exclusive; add one day to include end_date.
    end_exclusive = (pd.to_datetime(end_date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    output_path = "data/market_indices.jsonl"
    os.makedirs("data", exist_ok=True)

    print(f"Downloading {tickers} from {start_date} to {end_date}...")
    data = yf.download(tickers, start=start_date, end=end_exclusive, auto_adjust=False)

    # Handle yfinance multi-index columns (Price Type, Ticker) -> (Ticker_PriceType)
    data.columns = [f"{t}_{p}" for p, t in data.columns]
    df = data.reset_index()
    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")

    df.to_json(output_path, orient="records", lines=True)
    print(f"Market data saved to {output_path} ({len(df):,} rows)")


if __name__ == "__main__":
    download_market_indices()
