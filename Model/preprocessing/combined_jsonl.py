import os
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pandas_ta as ta
import polars as pl
from tqdm import tqdm

# Constants
INDEX_PREFIXES = ["DIA", "QQQ", "SPY", "^VIX"]
START_DATE = "2010-01-01"


def normalize_ticker(s: str) -> str:
    """Normalize a ticker symbol so news + filenames line up.

    Strips whitespace, uppercases, removes a leading '$', and drops anything
    after the first space (e.g. 'AAPL US Equity' -> 'AAPL').
    """
    if s is None:
        return ""
    s = str(s).strip().upper()
    if s.startswith("$"):
        s = s[1:]
    s = s.split()[0] if s else s
    # Replace common share-class separators so e.g. 'BRK.B' stays 'BRK.B'
    # but 'AAPL/' becomes 'AAPL'
    s = s.rstrip("/.,;:")
    return s


def expected_spy_feature_columns() -> list[str]:
    cols = []
    common = [
        "return_1d", "return_5d", "intraday_return", "log_return_1d",
        "SMA_5", "SMA_20", "price_to_SMA5",
        "volatility_5d", "volatility_20d",
    ]
    for p in INDEX_PREFIXES:
        cols.extend([f"{p}_{name}" for name in common])
        if p != "^VIX":
            cols.append(f"{p}_volume_SMA_20")
            cols.append(f"{p}_volume_ratio_20")
    return cols


def create_spy_features(spy_df: pd.DataFrame) -> pd.DataFrame:
    spy_df = spy_df.copy()
    for p in INDEX_PREFIXES:
        close_col, open_col, vol_col = f"{p}_Close", f"{p}_Open", f"{p}_Volume"
        if close_col not in spy_df.columns:
            continue

        spy_df[f"{p}_return_1d"] = spy_df[close_col].pct_change(1)
        spy_df[f"{p}_return_5d"] = spy_df[close_col].pct_change(5)
        spy_df[f"{p}_intraday_return"] = (spy_df[close_col] - spy_df[open_col]) / (spy_df[open_col] + 1e-9)
        spy_df[f"{p}_log_return_1d"] = np.log(spy_df[close_col] / spy_df[close_col].shift(1))

        spy_df[f"{p}_SMA_5"] = ta.sma(spy_df[close_col], length=5) / (spy_df[close_col] + 1e-9)
        spy_df[f"{p}_SMA_20"] = ta.sma(spy_df[close_col], length=20) / (spy_df[close_col] + 1e-9)
        spy_df[f"{p}_price_to_SMA5"] = spy_df[close_col] / (ta.sma(spy_df[close_col], length=5) + 1e-9)
        spy_df[f"{p}_volatility_5d"] = spy_df[f"{p}_return_1d"].rolling(5).std()
        spy_df[f"{p}_volatility_20d"] = spy_df[f"{p}_return_1d"].rolling(20).std()

        if p != "^VIX" and vol_col in spy_df.columns:
            v_sma = ta.sma(spy_df[vol_col], length=20)
            spy_df[f"{p}_volume_SMA_20"] = v_sma / (spy_df[vol_col] + 1e-9)
            spy_df[f"{p}_volume_ratio_20"] = spy_df[vol_col] / (v_sma + 1e-9)

        spy_df.drop(
            columns=[f"{p}_Open", f"{p}_High", f"{p}_Low", f"{p}_Close", f"{p}_Volume"],
            inplace=True, errors="ignore",
        )
    return spy_df


def create_stock_features_single(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if len(df) < 60:
        return pd.DataFrame()

    # Pre-filter by date to save computation (keep a buffer for rolling windows)
    df = df[df["Date"] >= pd.Timestamp(START_DATE) - pd.Timedelta(days=100)].copy()
    if len(df) < 60:
        return pd.DataFrame()

    # Returns
    df["return_1d"] = df["Close"].pct_change(1)
    df["return_5d"] = df["Close"].pct_change(5)
    df["return_10d"] = df["Close"].pct_change(10)
    df["return_20d"] = df["Close"].pct_change(20)
    df["log_return_1d"] = np.log(df["Close"] / df["Close"].shift(1))
    df["gap"] = (df["Open"] - df["Close"].shift(1)) / (df["Close"].shift(1) + 1e-9)
    df["intraday_return"] = (df["Close"] - df["Open"]) / (df["Open"] + 1e-9)

    # Moving averages
    df["SMA_5"] = ta.sma(df["Close"], length=5) / (df["Close"] + 1e-9)
    df["SMA_10"] = ta.sma(df["Close"], length=10) / (df["Close"] + 1e-9)
    df["SMA_20"] = ta.sma(df["Close"], length=20) / (df["Close"] + 1e-9)
    df["SMA_50"] = ta.sma(df["Close"], length=50) / (df["Close"] + 1e-9)
    df["EMA_12"] = ta.ema(df["Close"], length=12) / (df["Close"] + 1e-9)
    df["EMA_26"] = ta.ema(df["Close"], length=26) / (df["Close"] + 1e-9)
    df["price_to_SMA5"] = df["Close"] / (ta.sma(df["Close"], length=5) + 1e-9)
    df["price_to_SMA20"] = df["Close"] / (ta.sma(df["Close"], length=20) + 1e-9)

    # Volatility
    df["volatility_5d"] = df["return_1d"].rolling(5).std()
    df["volatility_20d"] = df["return_1d"].rolling(20).std()
    df["ATR_14"] = ta.atr(df["High"], df["Low"], df["Close"], length=14) / (df["Close"] + 1e-9)

    # Bollinger Bands
    bbands = ta.bbands(df["Close"], length=20, std=2)
    if bbands is not None and not bbands.empty:
        df["BB_width"] = (bbands.iloc[:, 0] - bbands.iloc[:, 2]) / (bbands.iloc[:, 1] + 1e-9)
        df["BB_position"] = (df["Close"] - bbands.iloc[:, 2]) / (bbands.iloc[:, 0] - bbands.iloc[:, 2] + 1e-9)

    # Momentum oscillators
    df["RSI_14"] = ta.rsi(df["Close"], length=14)
    macd = ta.macd(df["Close"])
    if macd is not None and not macd.empty:
        df["MACD"] = macd.iloc[:, 0] / (df["Close"] + 1e-9)
        df["MACD_signal"] = macd.iloc[:, 1] / (df["Close"] + 1e-9)
        df["MACD_histogram"] = macd.iloc[:, 2] / (df["Close"] + 1e-9)

    df["ROC_10"] = ta.roc(df["Close"], length=10)
    stoch = ta.stoch(df["High"], df["Low"], df["Close"])
    if stoch is not None and not stoch.empty:
        df["stochastic_14"] = stoch.iloc[:, 0]

    # Volume
    v_sma = ta.sma(df["Volume"], length=20)
    df["volume_SMA_20"] = v_sma / (df["Volume"] + 1e-9)
    df["volume_ratio_20"] = df["Volume"] / (v_sma + 1e-9)
    df["volume_change"] = df["Volume"].pct_change(1)
    df["OBV"] = ta.obv(df["Close"], df["Volume"]) / (df["Volume"].rolling(20).mean() + 1e-9)
    df["MFI_14"] = ta.mfi(df["High"], df["Low"], df["Close"], df["Volume"], length=14)

    # Candle shape
    df["daily_range"] = (df["High"] - df["Low"]) / (df["Close"] + 1e-9)
    df["close_position"] = (df["Close"] - df["Low"]) / (df["High"] - df["Low"] + 1e-9)
    df["upper_wick"] = (df["High"] - np.maximum(df["Close"], df["Open"])) / (df["Close"] + 1e-9)
    df["lower_wick"] = (np.minimum(df["Close"], df["Open"]) - df["Low"]) / (df["Close"] + 1e-9)
    df["body_size"] = np.abs(df["Close"] - df["Open"]) / (df["Open"] + 1e-9)

    adx = ta.adx(df["High"], df["Low"], df["Close"], length=14)
    if adx is not None and not adx.empty:
        df["ADX_14"] = adx.iloc[:, 0]

    # Target
    df["raw_return"] = df["Close"].shift(-5) / df["Close"] - 1
    df["momentum"] = df["raw_return"] * 100.0

    df["ticker"] = ticker
    df = df[df["Date"] >= pd.Timestamp(START_DATE)]
    df = df.dropna(subset=["SMA_50", "momentum"])

    drop_cols = {
        "Open", "High", "Low", "Close", "Adj Close", "Volume",
        "ticker", "Date", "momentum", "raw_return", "parsed_dt",
    }
    keep_cols = ["ticker", "Date", "momentum", "raw_return"] + [
        c for c in df.columns if c not in drop_cols
    ]
    return df[keep_cols]


def process_news_polars(csv_path: Path) -> pd.DataFrame:
    """Lightning fast news processing using Polars."""
    print(f"Scanning news data (starting from {START_DATE})...")

    cols = [
        "Date", "Stock_symbol",
        "Luhn_summary", "Textrank_summary", "Lexrank_summary", "Lsa_summary",
        "Article_title", "Article",
    ]

    # Lazy scan, filter, and pick the best text column per row.
    # Note: avoid pl.Object / map_elements inside group_by; that path
    # triggers a Rust panic in extension/drop.rs on cleanup.
    q = (
        pl.scan_csv(csv_path, infer_schema_length=10000, ignore_errors=True)
        .select(cols)
        # Parse Date without timezone so date_key matches local stock dates.
        .with_columns(pl.col("Date").str.slice(0, 10).str.to_date(strict=False))
        .filter(pl.col("Date") >= pl.date(2010, 1, 1))
        .drop_nulls(["Date", "Stock_symbol"])
        .with_columns([
            # Normalize ticker: trim, uppercase, drop leading '$', take first token.
            pl.col("Stock_symbol")
              .str.strip_chars()
              .str.to_uppercase()
              .str.replace_all(r"^\$", "")
              .str.split(" ")
              .list.first()
              .alias("ticker"),
            pl.col("Date").alias("date_key"),
        ])
        .with_columns(
            text=pl.coalesce([
                pl.col("Luhn_summary"),
                pl.col("Textrank_summary"),
                pl.col("Lexrank_summary"),
                pl.col("Lsa_summary"),
                pl.col("Article_title"),
                pl.col("Article"),
            ])
        )
        .filter(pl.col("text").is_not_null())
        .filter(pl.col("ticker").str.len_chars() > 0)
        .select(["ticker", "date_key", "text"])
    )

    print("Aggregating news by ticker and date...")
    news_agg = (
        q.group_by(["ticker", "date_key"])
        .agg(pl.col("text"))
        .collect(engine="streaming")
    )

    df = news_agg.to_pandas()
    df["tweets"] = df["text"].apply(lambda lst: [{"text": t} for t in lst])
    df = df.drop(columns=["text"])
    # Force date_key to plain python date for clean merging later.
    df["date_key"] = pd.to_datetime(df["date_key"]).dt.date
    return df


def main():
    base_dir = Path(os.getenv("DATA_PATH", "data"))

    # 1. News
    t0 = time.time()
    news_df = process_news_polars(base_dir / "news_data.csv")
    print(f"News processed in {(time.time() - t0) / 60:.2f} minutes.")
    print(f"  News rows: {len(news_df):,}")
    print(f"  News unique tickers: {news_df['ticker'].nunique():,}")
    print(f"  Top news tickers: {news_df['ticker'].value_counts().head(10).to_dict()}")

    news_tickers = set(news_df["ticker"].unique())
    wanted_tickers = news_tickers | {"DIA", "QQQ", "SPY", "^VIX", "VIX"}

    # 2. Stocks
    print("\nProcessing stocks...")
    stock_dir = base_dir / "stock_data"
    stock_files = list(stock_dir.glob("*.csv"))
    print(f"  Found {len(stock_files):,} stock files")

    file_stems = {f.stem.upper() for f in stock_files}
    overlap = news_tickers & file_stems
    print(f"  News/file ticker overlap: {len(overlap):,} of {len(news_tickers):,} news tickers")
    if len(overlap) < 10:
        sample_news = sorted(list(news_tickers))[:20]
        sample_files = sorted(list(file_stems))[:20]
        print(f"  WARN: low overlap. Sample news tickers: {sample_news}")
        print(f"  WARN: sample file stems: {sample_files}")

    processed_stocks = []
    fail_count = 0
    fail_examples = []

    for f in tqdm(stock_files):
        ticker = normalize_ticker(f.stem)
        if ticker not in wanted_tickers:
            continue
        try:
            sdf = pd.read_csv(f)
            sdf.columns = [c.capitalize() for c in sdf.columns]
            if "Date" not in sdf.columns:
                fail_count += 1
                if len(fail_examples) < 5:
                    fail_examples.append(f"{ticker}: no Date column ({list(sdf.columns)})")
                continue
            sdf["Date"] = pd.to_datetime(sdf["Date"], errors="coerce")
            sdf = sdf.dropna(subset=["Date"])

            fdf = create_stock_features_single(sdf, ticker)
            if not fdf.empty:
                processed_stocks.append(fdf)
            else:
                fail_count += 1
                if len(fail_examples) < 5:
                    fail_examples.append(f"{ticker}: empty after feature creation")
        except Exception as e:
            fail_count += 1
            if len(fail_examples) < 5:
                fail_examples.append(f"{ticker}: {type(e).__name__}: {e}")
            continue

    print(f"  Processed {len(processed_stocks):,} stocks, failed {fail_count:,}")
    if fail_examples:
        print(f"  Sample failures:")
        for ex in fail_examples:
            print(f"    - {ex}")

    if not processed_stocks:
        raise RuntimeError("No stocks processed; aborting.")

    stock_feats = pd.concat(processed_stocks, ignore_index=True)
    print(f"  Stock feature rows: {len(stock_feats):,}, unique tickers: {stock_feats['ticker'].nunique():,}")

    # 3. Market features
    print("\nFinalizing market features...")
    market_list = []
    for t in ["DIA", "QQQ", "SPY", "^VIX"]:
        # Try a few naming conventions for the index file.
        candidates = [
            stock_dir / f"{t}.csv",
            stock_dir / f"{t.replace('^', '')}.csv",
            stock_dir / f"{t.lower()}.csv",
            stock_dir / f"{t.replace('^', '').lower()}.csv",
        ]
        path = next((p for p in candidates if p.exists()), None)
        if path is None:
            print(f"  WARN: no file for {t}")
            continue
        m_df = pd.read_csv(path)
        m_df.columns = [c.capitalize() for c in m_df.columns]
        m_df = m_df[["Date", "Open", "High", "Low", "Close", "Volume"]].copy()
        m_df["Date"] = pd.to_datetime(m_df["Date"], errors="coerce")
        m_df = m_df.dropna(subset=["Date"]).set_index("Date")
        m_df.columns = [f"{t}_{c}" for c in m_df.columns]
        market_list.append(m_df)

    market_df = pd.concat(market_list, axis=1).sort_index().reset_index()
    market_df["Date"] = pd.to_datetime(market_df["Date"])
    market_feats = create_spy_features(market_df)

    # 4. Final merge
    print("\nMerging everything...")
    stock_feats["Date"] = pd.to_datetime(stock_feats["Date"]).dt.date
    market_feats["Date"] = pd.to_datetime(market_feats["Date"]).dt.date

    stock_val_cols = [c for c in stock_feats.columns if c not in ["ticker", "Date", "momentum", "raw_return"]]
    stock_feats["stock"] = stock_feats[stock_val_cols].to_dict(orient="records")

    spy_expected = expected_spy_feature_columns()
    for c in spy_expected:
        if c not in market_feats.columns:
            market_feats[c] = 0.0
    market_feats["spy"] = market_feats[spy_expected].to_dict(orient="records")

    # Diagnostics on join keys.
    sample_stock_keys = set(zip(stock_feats["ticker"].head(100), stock_feats["Date"].head(100)))
    sample_news_keys = set(zip(news_df["ticker"].head(100), news_df["date_key"].head(100)))
    print(f"  Stock key sample: {list(sample_stock_keys)[:3]}")
    print(f"  News key sample: {list(sample_news_keys)[:3]}")

    combined = stock_feats[["ticker", "Date", "stock", "momentum"]].merge(
        news_df, left_on=["ticker", "Date"], right_on=["ticker", "date_key"], how="left",
    )
    combined = combined.drop(columns=["date_key"], errors="ignore")
    combined = combined.merge(market_feats[["Date", "spy"]], on="Date", how="left")

    combined["tweets"] = combined["tweets"].apply(lambda x: x if isinstance(x, list) else [])
    combined["spy"] = combined["spy"].apply(lambda x: x if isinstance(x, dict) else {})
    combined["Date"] = combined["Date"].astype(str)

    out_path = base_dir / "data.parquet"
    combined.to_parquet(out_path, index=False)

    # Final report
    print("\n=== Preprocessing Complete ===")
    print(f"  Output: {out_path}")
    print(f"  Total rows: {len(combined):,}")
    print(f"  Date range: {combined['Date'].min()} to {combined['Date'].max()}")
    print(f"  Unique tickers: {combined['ticker'].nunique():,}")
    print(f"  Rows with tweets: {combined['tweets'].apply(len).gt(0).sum():,}")
    total_tweets = combined["tweets"].apply(len).sum()
    print(f"  Total tweets/articles: {total_tweets:,}")


if __name__ == "__main__":
    main()