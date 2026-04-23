import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pandas_ta as ta

INDEX_PREFIXES = ["DIA", "QQQ", "SPY", "^VIX"]


def expected_spy_feature_columns() -> list[str]:
    cols: list[str] = []
    common = [
        "return_1d",
        "return_5d",
        "intraday_return",
        "log_return_1d",
        "SMA_5",
        "SMA_20",
        "price_to_SMA5",
        "volatility_5d",
        "volatility_20d",
    ]
    for p in INDEX_PREFIXES:
        cols.extend([f"{p}_{name}" for name in common])
        if p != "^VIX":
            cols.append(f"{p}_volume_SMA_20")
            cols.append(f"{p}_volume_ratio_20")
    return cols


def create_spy_features(spy_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates technical indicators for SPY index data and removes raw OHLCV columns.
    """
    prefixes = INDEX_PREFIXES
    
    for p in prefixes:
        close_col = f'{p}_Close'
        open_col = f'{p}_Open'
        high_col = f'{p}_High'
        low_col = f'{p}_Low'
        vol_col = f'{p}_Volume'
        
        if close_col not in spy_df.columns:
            continue
            
        # Returns
        spy_df[f'{p}_return_1d'] = spy_df[close_col].pct_change(1)
        spy_df[f'{p}_return_5d'] = spy_df[close_col].pct_change(5)
        spy_df[f'{p}_intraday_return'] = (spy_df[close_col] - spy_df[open_col]) / (spy_df[open_col] + 1e-9)
        spy_df[f'{p}_log_return_1d'] = np.log(spy_df[close_col] / spy_df[close_col].shift(1))
        
        # Moving Averages
        spy_df[f'{p}_SMA_5'] = ta.sma(spy_df[close_col], length=5)
        spy_df[f'{p}_SMA_20'] = ta.sma(spy_df[close_col], length=20)
        spy_df[f'{p}_price_to_SMA5'] = spy_df[close_col] / (spy_df[f'{p}_SMA_5'] + 1e-9)
        
        # Volatility
        spy_df[f'{p}_volatility_5d'] = spy_df[f'{p}_return_1d'].rolling(5).std()
        spy_df[f'{p}_volatility_20d'] = spy_df[f'{p}_return_1d'].rolling(20).std()
        
        # Volume (Skip VIX as it often lacks volume data)
        if p != '^VIX' and vol_col in spy_df.columns:
            spy_df[f'{p}_volume_SMA_20'] = ta.sma(spy_df[vol_col], length=20)
            spy_df[f'{p}_volume_ratio_20'] = spy_df[vol_col] / (spy_df[f'{p}_volume_SMA_20'] + 1e-9)
            
        # Drop raw columns
        spy_df.drop(columns=[open_col, high_col, low_col, close_col, vol_col], inplace=True, errors='ignore')
        
    return spy_df


def create_stock_features(stock_df: pd.DataFrame) -> pd.DataFrame:
    """
    Build per-ticker technical indicators and 5-day forward-return targets.
    """
    if stock_df.empty:
        return stock_df

    stock_df = stock_df.copy()
    stock_df["Date"] = pd.to_datetime(stock_df["Date"], errors="coerce")
    stock_df = stock_df.dropna(subset=["Date"]).sort_values(["ticker", "Date"])

    feature_dfs = []
    for ticker, group in stock_df.groupby("ticker"):
        g = group.copy().sort_values("Date")
        if len(g) < 60:
            continue

        g["return_1d"] = g["Close"].pct_change(1)
        g["return_5d"] = g["Close"].pct_change(5)
        g["return_10d"] = g["Close"].pct_change(10)
        g["return_20d"] = g["Close"].pct_change(20)
        g["log_return_1d"] = np.log(g["Close"] / g["Close"].shift(1))
        g["gap"] = g["Open"] - g["Close"].shift(1)
        g["intraday_return"] = (g["Close"] - g["Open"]) / (g["Open"] + 1e-9)

        g["SMA_5"] = ta.sma(g["Close"], length=5)
        g["SMA_10"] = ta.sma(g["Close"], length=10)
        g["SMA_20"] = ta.sma(g["Close"], length=20)
        g["SMA_50"] = ta.sma(g["Close"], length=50)
        g["EMA_12"] = ta.ema(g["Close"], length=12)
        g["EMA_26"] = ta.ema(g["Close"], length=26)
        g["price_to_SMA5"] = g["Close"] / (g["SMA_5"] + 1e-9)
        g["price_to_SMA20"] = g["Close"] / (g["SMA_20"] + 1e-9)
        g["volatility_5d"] = g["return_1d"].rolling(5).std()
        g["volatility_20d"] = g["return_1d"].rolling(20).std()
        g["ATR_14"] = ta.atr(g["High"], g["Low"], g["Close"], length=14)

        bbands = ta.bbands(g["Close"], length=20, std=2)
        if bbands is not None and not bbands.empty:
            bb_cols = bbands.columns.tolist()
            bb_upper = next((c for c in bb_cols if "BBU" in c), None)
            bb_middle = next((c for c in bb_cols if "BBM" in c), None)
            bb_lower = next((c for c in bb_cols if "BBL" in c), None)
            if bb_upper and bb_middle and bb_lower:
                g["BB_width"] = (bbands[bb_upper] - bbands[bb_lower]) / (bbands[bb_middle] + 1e-9)
                band_range = bbands[bb_upper] - bbands[bb_lower]
                g["BB_position"] = np.where(
                    band_range > 1e-9,
                    (g["Close"] - bbands[bb_lower]) / band_range,
                    0.5,
                )

        g["RSI_14"] = ta.rsi(g["Close"], length=14)
        macd = ta.macd(g["Close"])
        if macd is not None and not macd.empty:
            macd_cols = macd.columns.tolist()
            macd_line = next((c for c in macd_cols if "MACD_" in c and "MACDs" not in c and "MACDh" not in c), None)
            macd_signal = next((c for c in macd_cols if "MACDs" in c), None)
            macd_hist = next((c for c in macd_cols if "MACDh" in c), None)
            if macd_line:
                g["MACD"] = macd[macd_line]
            if macd_signal:
                g["MACD_signal"] = macd[macd_signal]
            if macd_hist:
                g["MACD_histogram"] = macd[macd_hist]

        g["ROC_10"] = ta.roc(g["Close"], length=10)
        stoch = ta.stoch(g["High"], g["Low"], g["Close"])
        if stoch is not None and not stoch.empty:
            stoch_col = next((c for c in stoch.columns if "STOCHk" in c), None)
            if stoch_col:
                g["stochastic_14"] = stoch[stoch_col]

        g["volume_SMA_20"] = ta.sma(g["Volume"], length=20)
        g["volume_ratio_20"] = g["Volume"] / (g["volume_SMA_20"] + 1e-9)
        g["volume_change"] = g["Volume"].pct_change(1)
        g["OBV"] = ta.obv(g["Close"], g["Volume"])
        g["MFI_14"] = ta.mfi(g["High"], g["Low"], g["Close"], g["Volume"], length=14)

        g["daily_range"] = (g["High"] - g["Low"]) / (g["Close"] + 1e-9)
        g["close_position"] = (g["Close"] - g["Low"]) / (g["High"] - g["Low"] + 1e-9)
        g["upper_wick"] = (g["High"] - np.maximum(g["Close"], g["Open"])) / (g["Close"] + 1e-9)
        g["lower_wick"] = (np.minimum(g["Close"], g["Open"]) - g["Low"]) / (g["Close"] + 1e-9)
        g["body_size"] = np.abs(g["Close"] - g["Open"]) / (g["Open"] + 1e-9)

        adx = ta.adx(g["High"], g["Low"], g["Close"], length=14)
        if adx is not None and not adx.empty:
            adx_col = next((c for c in adx.columns if c.startswith("ADX")), None)
            if adx_col:
                g["ADX_14"] = adx[adx_col]

        g["raw_return"] = g["Close"].shift(-5) / g["Close"] - 1
        g["momentum"] = g["raw_return"] * 100.0
        g = g.dropna(subset=["SMA_50", "momentum"])
        feature_dfs.append(g)

    if not feature_dfs:
        return pd.DataFrame(columns=stock_df.columns.tolist() + ["raw_return", "momentum"])
    return pd.concat(feature_dfs, ignore_index=True)


def _canonicalize_ohlcv_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize stock CSV schemas into Date/Open/High/Low/Close/Adj Close/Volume + ticker.
    """
    rename_map: dict[str, str] = {}
    for c in df.columns:
        key = c.strip().lower()
        if key in {"date", "datetime"}:
            rename_map[c] = "Date"
        elif key == "open":
            rename_map[c] = "Open"
        elif key == "high":
            rename_map[c] = "High"
        elif key == "low":
            rename_map[c] = "Low"
        elif key == "close":
            rename_map[c] = "Close"
        elif key in {"adj close", "adj_close", "adjusted close"}:
            rename_map[c] = "Adj Close"
        elif key == "volume":
            rename_map[c] = "Volume"
    out = df.rename(columns=rename_map).copy()

    required = {"Date", "Open", "High", "Low", "Close", "Volume"}
    missing = required - set(out.columns)
    if missing:
        raise ValueError(f"Missing OHLCV columns: {sorted(missing)}")

    if "Adj Close" not in out.columns:
        out["Adj Close"] = out["Close"]

    keep_cols = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
    out = out[keep_cols]
    for c in ["Open", "High", "Low", "Close", "Adj Close", "Volume"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out["Date"] = pd.to_datetime(out["Date"], errors="coerce")
    out = out.dropna(subset=["Date", "Open", "High", "Low", "Close", "Volume"])
    return out


def _load_news_groups_from_csv(news_csv_path: Path) -> tuple[pd.DataFrame, pd.Timestamp, pd.Timestamp]:
    """
    Convert article-level CSV rows into grouped `tweets` records by (ticker, date_key).
    """
    usecols = [
        "Unnamed: 0",
        "Date",
        "Stock_symbol",
        "Article_title",
        "Url",
        "Publisher",
        "Author",
        "Article",
        "Lsa_summary",
        "Luhn_summary",
        "Textrank_summary",
        "Lexrank_summary",
    ]

    grouped: dict[tuple[str, Any], list[dict[str, Any]]] = {}
    min_date: pd.Timestamp | None = None
    max_date: pd.Timestamp | None = None

    for chunk in pd.read_csv(
        news_csv_path,
        usecols=lambda c: c in set(usecols),
        chunksize=25_000,
        low_memory=False,
    ):
        chunk["parsed_dt"] = pd.to_datetime(chunk.get("Date"), errors="coerce", utc=True).dt.tz_convert(None)
        chunk["ticker"] = chunk.get("Stock_symbol").astype(str).str.strip().str.upper()
        chunk = chunk[chunk["parsed_dt"].notna() & chunk["ticker"].ne("")]
        if chunk.empty:
            continue

        this_min = chunk["parsed_dt"].min()
        this_max = chunk["parsed_dt"].max()
        min_date = this_min if min_date is None else min(min_date, this_min)
        max_date = this_max if max_date is None else max(max_date, this_max)

        text_candidates = [
            "Luhn_summary",
            "Textrank_summary",
            "Lexrank_summary",
            "Lsa_summary",
            "Article_title",
            "Article",
        ]

        for row in chunk.itertuples(index=False):
            row_dict = row._asdict()
            text = ""
            for c in text_candidates:
                v = row_dict.get(c)
                if isinstance(v, str) and v.strip():
                    text = v.strip()
                    break
            if not text:
                continue

            date_key = row_dict["parsed_dt"].date()
            ticker = row_dict["ticker"]
            rec = {
                "id": row_dict.get("Unnamed: 0"),
                "created_at": str(row_dict["parsed_dt"]),
                "text": text,
                "title": row_dict.get("Article_title"),
                "url": row_dict.get("Url"),
                "publisher": row_dict.get("Publisher"),
                "author": row_dict.get("Author"),
            }
            grouped.setdefault((ticker, date_key), []).append(rec)

    if not grouped:
        raise ValueError(f"No usable news rows found in {news_csv_path}")
    if min_date is None or max_date is None:
        raise ValueError("Unable to determine news date range")

    tweets_grouped = pd.DataFrame(
        [{"_ticker": k[0], "date_key": k[1], "tweets": v} for k, v in grouped.items()]
    )
    return tweets_grouped, min_date, max_date


def _load_stock_data_from_csvs(
    stock_dir: Path,
    tickers: set[str],
    min_date: pd.Timestamp,
    max_date: pd.Timestamp,
) -> pd.DataFrame:
    """
    Load selected ticker CSVs from `stock_dir` and normalize into a single OHLCV frame.
    """
    files = list(stock_dir.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No CSV files found under {stock_dir}")

    file_by_ticker: dict[str, Path] = {}
    for f in files:
        stem = f.stem.strip().upper()
        if stem and stem not in file_by_ticker:
            file_by_ticker[stem] = f

    # Always include index tickers for market features.
    needed = set(tickers) | {"SPY", "QQQ", "DIA", "^VIX", "VIX"}
    selected = sorted(t for t in needed if t in file_by_ticker)
    if not selected:
        raise ValueError("No stock CSV files matched the requested ticker universe.")

    lookback_start = (min_date - pd.Timedelta(days=120)).normalize()
    lookahead_end = (max_date + pd.Timedelta(days=10)).normalize()

    rows = []
    for ticker in selected:
        path = file_by_ticker[ticker]
        try:
            raw = pd.read_csv(path)
            g = _canonicalize_ohlcv_columns(raw)
        except Exception as e:
            print(f"WARN: skipping {path.name}: {e}")
            continue

        g = g[(g["Date"] >= lookback_start) & (g["Date"] <= lookahead_end)]
        if g.empty:
            continue
        g["ticker"] = "^VIX" if ticker == "VIX" else ticker
        rows.append(g)

    if not rows:
        raise ValueError("No stock rows remained after filtering by date range.")

    out = pd.concat(rows, ignore_index=True)
    out = out.sort_values(["ticker", "Date"]).reset_index(drop=True)
    return out


def _build_market_indices_from_stock(stock_df: pd.DataFrame) -> pd.DataFrame:
    """
    Build market index table with columns like SPY_Open, QQQ_Close, etc.
    """
    parts = []
    for ticker in ["DIA", "QQQ", "SPY", "^VIX"]:
        g = stock_df[stock_df["ticker"] == ticker].copy()
        if g.empty:
            continue
        g = g[["Date", "Open", "High", "Low", "Close", "Volume"]]
        g = g.rename(columns={c: f"{ticker}_{c}" for c in g.columns if c != "Date"})
        parts.append(g)

    if not parts:
        raise ValueError("Unable to build market indices; missing SPY/QQQ/DIA/^VIX CSV rows.")

    market = parts[0]
    for p in parts[1:]:
        market = market.merge(p, on="Date", how="outer")
    market = market.sort_values("Date")
    return market


def _run_legacy_jsonl_pipeline(paths: dict[str, str]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    stock = pd.read_json(paths["stock"], lines=True)
    news = pd.read_json(paths["tweets"], lines=True)
    market = pd.read_json(paths["market"], lines=True)
    return stock, news, market


def _run_csv_pipeline(base_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    news_csv = base_dir / "news_data.csv"
    stock_dir = base_dir / "stock_data"
    if not news_csv.exists():
        raise FileNotFoundError(f"Missing required file: {news_csv}")
    if not stock_dir.exists():
        raise FileNotFoundError(f"Missing required directory: {stock_dir}")

    tweets_grouped, min_date, max_date = _load_news_groups_from_csv(news_csv)
    ticker_universe = set(tweets_grouped["_ticker"].astype(str).str.upper().tolist())

    stock_raw = _load_stock_data_from_csvs(stock_dir, ticker_universe, min_date, max_date)
    stock = create_stock_features(stock_raw)
    stock = stock[
        (stock["Date"] >= min_date.normalize())
        & (stock["Date"] <= max_date.normalize())
        & (stock["ticker"].isin(ticker_universe))
    ].copy()

    market = _build_market_indices_from_stock(stock_raw)
    return stock, tweets_grouped, market


def _align_market_dates_to_stock_dates(market: pd.DataFrame, stock: pd.DataFrame) -> pd.DataFrame:
    """
    Reindex market features to the stock-date calendar so index data always
    has the same dates as stock rows.
    """
    stock_dates = pd.to_datetime(stock["Date"], errors="coerce").dropna().dt.normalize().drop_duplicates()
    stock_dates = stock_dates.sort_values()
    if stock_dates.empty:
        return market

    market = market.copy()
    market["Date"] = pd.to_datetime(market["Date"], errors="coerce").dt.normalize()
    market = market.dropna(subset=["Date"]).sort_values("Date").drop_duplicates(subset=["Date"], keep="last")
    market = market.set_index("Date").reindex(stock_dates)
    market = market.ffill().bfill().reset_index().rename(columns={"index": "Date"})
    return market

def main():
    # Configuration
    preprocess_start = pd.Timestamp(os.getenv("PREPROCESS_START_DATE", "2010-01-01")).normalize()
    paths = {
        "stock": "data/stock_data.jsonl",
        "tweets": "data/tweet_data.jsonl",
        "market": "data/market_indices.jsonl",
        "output_jsonl": "data/data.jsonl",
        "output_parquet": "data/data.parquet",
    }

    use_legacy = all(os.path.exists(paths[k]) for k in ["stock", "tweets", "market"])
    if use_legacy:
        stock, news_or_grouped, market = _run_legacy_jsonl_pipeline(paths)
    else:
        stock, news_or_grouped, market = _run_csv_pipeline(Path("data"))

    # Enforce training window at preprocessing time.
    stock["Date"] = pd.to_datetime(stock["Date"], errors="coerce")
    stock = stock.dropna(subset=["Date"])
    stock = stock[stock["Date"] >= preprocess_start].copy()

    # Sort market data chronologically before processing features
    market["Date"] = pd.to_datetime(market["Date"], errors="coerce")
    market = market.dropna(subset=["Date"]).sort_values("Date")
    market = create_spy_features(market)

    # Enforce a fixed 42-column index feature schema expected by IndexNetwork.
    spy_expected_cols = expected_spy_feature_columns()
    for c in spy_expected_cols:
        if c not in market.columns:
            market[c] = 0.0

    market[spy_expected_cols] = (
        market[spy_expected_cols]
        .replace([np.inf, -np.inf], np.nan)
        .ffill()
        .bfill()
        .fillna(0.0)
    )

    # Force index rows onto the same date calendar as stock rows.
    market = _align_market_dates_to_stock_dates(market, stock)

    # Normalize Dates to date-only objects.
    stock["Date"] = pd.to_datetime(stock["Date"]).dt.date
    market["Date"] = market["Date"].dt.date

    # 1. Process and group tweet/article records
    if {"_ticker", "date_key", "tweets"}.issubset(news_or_grouped.columns):
        tweets_grouped = news_or_grouped.copy()
        tweets_grouped["date_key"] = pd.to_datetime(tweets_grouped["date_key"], errors="coerce").dt.date
        tweets_grouped = tweets_grouped[
            pd.to_datetime(tweets_grouped["date_key"], errors="coerce") >= preprocess_start
        ].copy()
    else:
        news = news_or_grouped
        news["date_key"] = pd.to_datetime(news["created_at"]).dt.date
        tweet_fields = ["id", "created_at", "text", "user.screen_name", "retweet_count", "favorite_count"]
        keep = [c for c in tweet_fields if c in news.columns]
        tweets_grouped = (
            news[keep + ["_ticker", "date_key"]]
            .copy()
            .loc[lambda x: pd.to_datetime(x["date_key"], errors="coerce") >= preprocess_start]
            .groupby(["_ticker", "date_key"])
            .apply(lambda x: x[keep].to_dict(orient="records"), include_groups=False)
            .reset_index(name="tweets")
        )

    # 2. Nest Stock Technicals (Exclude raw OHLCV)
    cols_to_drop = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
    stock_value_cols = [c for c in stock.columns if c not in ["ticker", "Date"] + cols_to_drop]
    stock["stock"] = stock[stock_value_cols].to_dict(orient="records")
    stock_nested = stock[["ticker", "Date", "stock"]]

    # 3. Nest All Market Indices (SPY, QQQ, DIA, VIX)
    market_cols = spy_expected_cols
    market["spy"] = market[market_cols].to_dict(orient="records")
    market_nested = market[["Date", "spy"]]

    # 4. Perform triple merge
    combined = stock_nested.merge(
        tweets_grouped,
        left_on=["ticker", "Date"],
        right_on=["_ticker", "date_key"],
        how="left"
    )
    
    combined = combined.merge(market_nested, on="Date", how="left")
    
    # 5. Final cleanup and safety checks
    combined.drop(columns=["_ticker", "date_key"], inplace=True)

    # Ensure tweets is always a list and spy is always a dict
    combined["tweets"] = combined["tweets"].apply(lambda x: x if isinstance(x, list) else [])
    combined["spy"] = combined["spy"].apply(lambda x: x if isinstance(x, dict) else {})

    # Convert Date back to string for JSON serialization
    combined["Date"] = combined["Date"].astype(str)

    # Export to Parquet (preferred for pipeline consumption)
    combined.to_parquet(paths["output_parquet"], index=False)

    # Export to JSONL
    with open(paths["output_jsonl"], "w") as f:
        for rec in combined.to_dict(orient="records"):
            f.write(json.dumps(rec, default=str) + "\n")
            
    print(
        f"Successfully combined {len(combined)} rows into "
        f"{paths['output_parquet']} (and {paths['output_jsonl']})"
    )

if __name__ == "__main__":
    main()
