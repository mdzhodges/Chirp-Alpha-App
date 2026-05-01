import gc
import os
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
    if s is None:
        return ""
    s = str(s).strip().upper()
    if s.startswith("$"):
        s = s[1:]
    s = s.split()[0] if s else s
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

    df = df[df["Date"] >= pd.Timestamp(START_DATE) - pd.Timedelta(days=100)].copy()
    if len(df) < 60:
        return pd.DataFrame()

    df["return_1d"] = df["Close"].pct_change(1)
    df["return_5d"] = df["Close"].pct_change(5)
    df["return_10d"] = df["Close"].pct_change(10)
    df["return_20d"] = df["Close"].pct_change(20)
    df["log_return_1d"] = np.log(df["Close"] / df["Close"].shift(1))
    df["gap"] = (df["Open"] - df["Close"].shift(1)) / (df["Close"].shift(1) + 1e-9)
    df["intraday_return"] = (df["Close"] - df["Open"]) / (df["Open"] + 1e-9)

    df["SMA_5"] = ta.sma(df["Close"], length=5) / (df["Close"] + 1e-9)
    df["SMA_10"] = ta.sma(df["Close"], length=10) / (df["Close"] + 1e-9)
    df["SMA_20"] = ta.sma(df["Close"], length=20) / (df["Close"] + 1e-9)
    df["SMA_50"] = ta.sma(df["Close"], length=50) / (df["Close"] + 1e-9)
    df["EMA_12"] = ta.ema(df["Close"], length=12) / (df["Close"] + 1e-9)
    df["EMA_26"] = ta.ema(df["Close"], length=26) / (df["Close"] + 1e-9)
    df["price_to_SMA5"] = df["Close"] / (ta.sma(df["Close"], length=5) + 1e-9)
    df["price_to_SMA20"] = df["Close"] / (ta.sma(df["Close"], length=20) + 1e-9)

    df["volatility_5d"] = df["return_1d"].rolling(5).std()
    df["volatility_20d"] = df["return_1d"].rolling(20).std()
    df["ATR_14"] = ta.atr(df["High"], df["Low"], df["Close"], length=14) / (df["Close"] + 1e-9)

    bbands = ta.bbands(df["Close"], length=20, std=2)
    if bbands is not None and not bbands.empty:
        df["BB_width"] = (bbands.iloc[:, 0] - bbands.iloc[:, 2]) / (bbands.iloc[:, 1] + 1e-9)
        df["BB_position"] = (df["Close"] - bbands.iloc[:, 2]) / (bbands.iloc[:, 0] - bbands.iloc[:, 2] + 1e-9)

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

    v_sma = ta.sma(df["Volume"], length=20)
    df["volume_SMA_20"] = v_sma / (df["Volume"] + 1e-9)
    df["volume_ratio_20"] = df["Volume"] / (v_sma + 1e-9)
    df["volume_change"] = df["Volume"].pct_change(1)
    df["OBV"] = ta.obv(df["Close"], df["Volume"]) / (df["Volume"].rolling(20).mean() + 1e-9)
    df["MFI_14"] = ta.mfi(df["High"], df["Low"], df["Close"], df["Volume"], length=14)

    df["daily_range"] = (df["High"] - df["Low"]) / (df["Close"] + 1e-9)
    df["close_position"] = (df["Close"] - df["Low"]) / (df["High"] - df["Low"] + 1e-9)
    df["upper_wick"] = (df["High"] - np.maximum(df["Close"], df["Open"])) / (df["Close"] + 1e-9)
    df["lower_wick"] = (np.minimum(df["Close"], df["Open"]) - df["Low"]) / (df["Close"] + 1e-9)
    df["body_size"] = np.abs(df["Close"] - df["Open"]) / (df["Open"] + 1e-9)

    adx = ta.adx(df["High"], df["Low"], df["Close"], length=14)
    if adx is not None and not adx.empty:
        df["ADX_14"] = adx.iloc[:, 0]

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


def write_news_to_parquet(csv_path: Path, out_path: Path) -> tuple[int, int]:
    """Stream news CSV through polars, aggregate per (ticker, date), write
    directly to parquet. Returns (n_rows, n_unique_tickers).

    Output schema: ticker (str), Date (date), tweets (List[Struct{text}])
    Stays as polars throughout — never materializes to pandas, never builds
    Python list-of-dicts per row in memory."""
    print(f"Scanning news data (starting from {START_DATE})...")

    cols = [
        "Date", "Stock_symbol",
        "Luhn_summary", "Textrank_summary", "Lexrank_summary", "Lsa_summary",
        "Article_title", "Article",
    ]

    q = (
        pl.scan_csv(csv_path, infer_schema_length=10000, ignore_errors=True)
        .select(cols)
        .with_columns(pl.col("Date").str.slice(0, 10).str.to_date(strict=False))
        .filter(pl.col("Date") >= pl.date(2010, 1, 1))
        .drop_nulls(["Date", "Stock_symbol"])
        .with_columns([
            pl.col("Stock_symbol")
              .str.strip_chars()
              .str.to_uppercase()
              .str.replace_all(r"^\$", "")
              .str.split(" ")
              .list.first()
              .alias("ticker"),
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
        .select(["ticker", "Date", "text"])
    )

    print("Aggregating news by ticker and date and writing to parquet...")
    news_agg = (
        q.group_by(["ticker", "Date"])
        .agg(pl.col("text").alias("texts"))
        .with_columns(
            # Convert each text to {"text": ...} struct so it matches what
            # the rest of the pipeline expects (list[struct{text}]).
            tweets=pl.col("texts").list.eval(pl.struct(text=pl.element()))
        )
        .select(["ticker", "Date", "tweets"])
        .sort(["ticker", "Date"])
    )

    news_agg.sink_parquet(out_path, compression="zstd")

    # Quick stats by re-scanning the parquet (cheap, lazy)
    stats = (
        pl.scan_parquet(out_path)
        .select([pl.len().alias("n_rows"), pl.col("ticker").n_unique().alias("n_tickers")])
        .collect()
    )
    return int(stats["n_rows"][0]), int(stats["n_tickers"][0])


def write_stock_feats_to_parquet(stock_feats: pd.DataFrame, out_path: Path) -> None:
    """Pack per-row stock features into a struct column and write to parquet."""
    stock_val_cols = [c for c in stock_feats.columns if c not in ["ticker", "Date", "momentum", "raw_return"]]
    stock_feats["stock"] = stock_feats[stock_val_cols].to_dict(orient="records")
    out = stock_feats[["ticker", "Date", "stock", "momentum"]]
    out.to_parquet(out_path, index=False)


def main():
    base_dir = Path(os.getenv("DATA_PATH", "data"))
    tmp_dir = base_dir / "_tmp"
    tmp_dir.mkdir(exist_ok=True)

    news_parquet = tmp_dir / "news.parquet"
    stock_parquet = tmp_dir / "stock_feats.parquet"
    market_parquet = tmp_dir / "market_feats.parquet"

    # 1. News -> parquet (streaming, low memory)
    t0 = time.time()
    n_rows, n_tickers = write_news_to_parquet(base_dir / "news_data.csv", news_parquet)
    print(f"News processed in {(time.time() - t0) / 60:.2f} minutes.")
    print(f"  News rows: {n_rows:,}")
    print(f"  News unique tickers: {n_tickers:,}")

    # Read the small ticker-set into memory only (for filtering stock files).
    news_tickers = set(
        pl.scan_parquet(news_parquet)
        .select(pl.col("ticker").unique())
        .collect()["ticker"]
        .to_list()
    )
    wanted_tickers = news_tickers | {"DIA", "QQQ", "SPY", "^VIX", "VIX"}

    # 2. Stocks
    print("\nProcessing stocks...")
    stock_dir = base_dir / "stock_data"
    stock_files = list(stock_dir.glob("*.csv"))
    print(f"  Found {len(stock_files):,} stock files")

    file_stems = {f.stem.upper() for f in stock_files}
    overlap = news_tickers & file_stems
    print(f"  News/file ticker overlap: {len(overlap):,} of {len(news_tickers):,} news tickers")

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
            sdf = sdf.sort_values("Date").reset_index(drop=True)

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
    stock_feats["Date"] = pd.to_datetime(stock_feats["Date"]).dt.date
    print(f"  Stock feature rows: {len(stock_feats):,}, unique tickers: {stock_feats['ticker'].nunique():,}")

    # Pack and write stock feats to parquet, then drop from memory
    write_stock_feats_to_parquet(stock_feats, stock_parquet)
    del processed_stocks, stock_feats
    gc.collect()
    print(f"  Wrote {stock_parquet}")

    # 3. Market features
    print("\nFinalizing market features...")
    market_list = []
    for t in ["DIA", "QQQ", "SPY", "^VIX"]:
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
        m_df = m_df.dropna(subset=["Date"])
        m_df = m_df.sort_values("Date").set_index("Date")
        m_df.columns = [f"{t}_{c}" for c in m_df.columns]
        market_list.append(m_df)

    if not market_list:
        raise RuntimeError("No market index files found.")

    market_df = pd.concat(market_list, axis=1, sort=True).reset_index()
    market_df["Date"] = pd.to_datetime(market_df["Date"])
    market_df = market_df.sort_values("Date").reset_index(drop=True)

    market_feats = create_spy_features(market_df)

    spy_expected = expected_spy_feature_columns()
    for c in spy_expected:
        if c not in market_feats.columns:
            market_feats[c] = 0.0
    market_feats["spy"] = market_feats[spy_expected].to_dict(orient="records")
    market_feats["Date"] = pd.to_datetime(market_feats["Date"]).dt.date
    market_feats[["Date", "spy"]].to_parquet(market_parquet, index=False)
    del market_list, market_df, market_feats
    gc.collect()
    print(f"  Wrote {market_parquet}")

    # 4. Final merge using polars streaming. This is the part that was OOMing.
    print("\nMerging everything (polars streaming)...")
    out_path = base_dir / "data.parquet"

    stock_lf = pl.scan_parquet(stock_parquet)
    news_lf = pl.scan_parquet(news_parquet)
    market_lf = pl.scan_parquet(market_parquet)

    # Cast Date columns to a consistent type for joining.
    stock_lf = stock_lf.with_columns(pl.col("Date").cast(pl.Date))
    news_lf = news_lf.with_columns(pl.col("Date").cast(pl.Date))
    market_lf = market_lf.with_columns(pl.col("Date").cast(pl.Date))

    combined_lf = (
        stock_lf
        .join(news_lf, on=["ticker", "Date"], how="left")
        .join(market_lf, on=["Date"], how="left")
        # Convert Date to string for downstream code that expects strings.
        .with_columns(pl.col("Date").cast(pl.Utf8))
    )

    combined_lf.sink_parquet(out_path, compression="zstd")

    # Final report (cheap re-scan)
    stats = (
        pl.scan_parquet(out_path)
        .select([
            pl.len().alias("n_rows"),
            pl.col("ticker").n_unique().alias("n_tickers"),
            pl.col("Date").min().alias("min_date"),
            pl.col("Date").max().alias("max_date"),
            pl.col("tweets").is_not_null().sum().alias("rows_with_tweets"),
        ])
        .collect()
    )
    print("\n=== Preprocessing Complete ===")
    print(f"  Output: {out_path}")
    print(f"  Total rows: {int(stats['n_rows'][0]):,}")
    print(f"  Date range: {stats['min_date'][0]} to {stats['max_date'][0]}")
    print(f"  Unique tickers: {int(stats['n_tickers'][0]):,}")
    print(f"  Rows with tweets: {int(stats['rows_with_tweets'][0]):,}")

    # Cleanup intermediates (optional — comment out to keep them for debugging)
    for p in [news_parquet, stock_parquet, market_parquet]:
        try:
            p.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    main()