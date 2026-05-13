"""
Momentum prediction gRPC service.

This file is intentionally self-contained for feature engineering: the
functions that build stock and market features at inference time are
duplicated here so this service can be deployed independently of the
training-side `preprocessing/` package.

If you change feature engineering during training, you MUST mirror the
change in the FEATURE ENGINEERING section below, otherwise inference
features won't match training features and predictions will be wrong.
"""

from __future__ import annotations

import os
import sys
import traceback
from concurrent import futures
from logging import Logger
from typing import Optional

import numpy as np
import pandas as pd
import pandas_ta as ta
import torch
import torch.nn.functional as F

import grpc

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from Model.logger.logger import AppLogger

import momentum_pb2
import momentum_pb2_grpc

from model_final.stock_nn import StockNetwork
from model_final.index_nn import IndexNetwork
from model_final.final_output import OutputNN

# ---------------------------------------------------------------------------
# FEATURE ENGINEERING
# ---------------------------------------------------------------------------

INDEX_PREFIXES = ["DIA", "QQQ", "SPY", "^VIX"]


def _create_spy_features(spy_df: pd.DataFrame) -> pd.DataFrame:
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


def _create_stock_features(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if len(df) < 60:
        return pd.DataFrame()

    df = df.copy()

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

    df["ticker"] = ticker
    df = df.dropna(subset=["SMA_50"])

    drop_cols = {
        "Open", "High", "Low", "Close", "Adj Close", "Volume",
        "ticker", "Date", "momentum", "raw_return", "parsed_dt",
    }
    keep_cols = ["ticker", "Date"] + [c for c in df.columns if c not in drop_cols]
    return df[keep_cols]


# ---------------------------------------------------------------------------
# SENTIMENT CLASSIFIER
# ---------------------------------------------------------------------------

def _load_sentiment_classifier(model_name: str, device: torch.device):
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    try:
        tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=False)
    except (ValueError, OSError):
        from transformers import BertTokenizer
        tokenizer = BertTokenizer.from_pretrained(model_name)

    try:
        model = AutoModelForSequenceClassification.from_pretrained(model_name)
    except (ValueError, OSError):
        from transformers import BertForSequenceClassification
        model = BertForSequenceClassification.from_pretrained(model_name, num_labels=3)

    model.eval().to(device)

    cfg = getattr(model.config, "id2label", None) or {}
    print(f"DEBUG: Sentiment model {model_name} id2label: {cfg}")
    label_map: dict[int, str] = {}
    for idx, name in cfg.items():
        idx = int(idx)
        n = str(name).lower()
        if "pos" in n or "bull" in n:
            label_map[idx] = "bullish"
        elif "neg" in n or "bear" in n:
            label_map[idx] = "bearish"
        elif "neu" in n:
            label_map[idx] = "neutral"
        else:
            label_map[idx] = n

    if not label_map or any(v.startswith("label_") for v in label_map.values()):
        if "finbert-tone" in model_name.lower():
            label_map = {0: "neutral", 1: "bullish", 2: "bearish"}
        elif "prosus" in model_name.lower():
            label_map = {0: "bullish", 1: "bearish", 2: "neutral"}
    
    print(f"DEBUG: Resolved label_map: {label_map}")

    canonical_col_for: dict[int, int] = {}
    for idx, lbl in label_map.items():
        col = {"bullish": 0, "bearish": 1, "neutral": 2}.get(lbl)
        if col is not None:
            canonical_col_for[idx] = col
    
    print(f"DEBUG: canonical_col_for: {canonical_col_for}")

    if len(canonical_col_for) != 3:
        raise RuntimeError(f"Could not resolve all 3 sentiment classes for {model_name}. Map: {canonical_col_for}")

    return tokenizer, model, canonical_col_for


@torch.no_grad()
def _texts_to_sentiment_features(
        texts: list[str],
        tokenizer,
        model,
        canonical_col_for: dict[int, int],
        *,
        device: torch.device,
        max_length: int = 128,
        batch_size: int = 64,
) -> Optional[torch.Tensor]:
    """Returns a (1, 5) CPU tensor: [mean_bull, mean_bear, mean_neu, count, std_bull]."""
    cleaned = [t.strip() for t in texts if isinstance(t, str) and t.strip()]
    if not cleaned:
        return None

    # Log mapping once
    print(f"DEBUG: Sentiment Mapping - {canonical_col_for}")

    all_probs: list[torch.Tensor] = []
    for i in range(0, len(cleaned), batch_size):
        chunk = cleaned[i: i + batch_size]
        inputs = tokenizer(
            chunk,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=max_length,
        ).to(device)
        out = model(**inputs)
        probs = F.softmax(out.logits.float(), dim=-1).cpu()
        
        # Log raw probs for the first few tweets of the first batch
        if i == 0:
            for idx, text in enumerate(chunk[:3]):
                print(f"DEBUG Tweet {idx}: '{text[:50]}...'")
                print(f"  Raw Probs: {probs[idx].tolist()}")

        canonical = torch.zeros_like(probs)
        for idx, col in canonical_col_for.items():
            canonical[:, col] = probs[:, idx]
        all_probs.append(canonical)

    p = torch.cat(all_probs, dim=0)
    n = p.shape[0]
    mean_bull = p[:, 0].mean().item()
    mean_bear = p[:, 1].mean().item()
    mean_neu = p[:, 2].mean().item()
    std_bull = p[:, 0].std(unbiased=False).item() if n > 1 else 0.0
    
    print(f"DEBUG Final Sentiment Vector: Bull={mean_bull:.4f}, Bear={mean_bear:.4f}, Neu={mean_neu:.4f}, Count={n}")

    return torch.tensor(
        [[mean_bull, mean_bear, mean_neu, float(n), std_bull]],
        dtype=torch.float32,
    )


# ---------------------------------------------------------------------------
# SERVICE
# ---------------------------------------------------------------------------

class MomentumService(momentum_pb2_grpc.MomentumServiceServicer):

    def __init__(self, models_dir: Optional[str] = None):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._logger = AppLogger.get_logger(self.__class__.__name__)
        self._logger.info(f"Using device: {self.device}")

        if models_dir is None:
            models_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "models"))

        self.models = {}
        model_files = {
            "balanced": "balanced.pt",
            "bullish": "bullish.pt",
            "bearish": "bearish.pt",
            "high_ic": "high_ic.pt"
        }

        # Historical accuracy stats for weighting the ensemble
        self.model_stats = {
            "balanced": {"up": 0.5102, "down": 0.5247},
            "bullish":  {"up": 0.6960, "down": 0.3432},
            "bearish":  {"up": 0.3842, "down": 0.6335},
            "high_ic":  {"up": 0.5796, "down": 0.4721}
        }

        for model_id, filename in model_files.items():
            path = os.path.join(models_dir, filename)
            if not os.path.exists(path):
                self._logger.warning(f"Model {model_id} not found at {path}. Skipping.")
                continue

            self._logger.info(f"Loading model {model_id} from {path}...")
            weights = torch.load(path, map_location=self.device, weights_only=False)

            scalers = weights.get("scalers")
            feature_cols = weights.get("feature_cols")
            pca_models = weights.get("pca_models", {})
            target_stats = weights.get("target_stats", {"mean": 0.0, "std": 1.0})

            stock_in_dim = weights["stock_network"]["input_layer.0.weight"].shape[1]
            spy_in_dim = weights["index_network"]["input_layer.0.weight"].shape[1]

            stock_net = StockNetwork(input_dim=stock_in_dim).to(self.device)
            index_net = IndexNetwork(input_dim=spy_in_dim).to(self.device)
            output_net = OutputNN(numeric_dim=48, text_dim=5).to(self.device)

            stock_net.load_state_dict(self._extract_state(weights, "stock_network"), strict=False)
            index_net.load_state_dict(self._extract_state(weights, "index_network"), strict=False)
            output_net.load_state_dict(self._extract_state(weights, "output_network"), strict=False)

            stock_net.eval()
            index_net.eval()
            output_net.eval()

            self.models[model_id] = {
                "stock_network": stock_net,
                "index_network": index_net,
                "output_network": output_net,
                "stock_scaler": scalers["stock_scaler"],
                "spy_scaler": scalers["spy_scaler"],
                "stock_cols": list(feature_cols["stock"]),
                "spy_cols": list(feature_cols["spy"]),
                "pca_stock": pca_models.get("pca_stock"),
                "pca_spy": pca_models.get("pca_spy"),
                "target_mean": target_stats["mean"],
                "target_std": target_stats["std"]
            }

        if not self.models:
            raise RuntimeError(f"No models found in {models_dir}")

        # Shared sentiment classifier (using config from the first model or default)
        weights_ref = torch.load(os.path.join(models_dir, list(model_files.values())[0]), map_location="cpu",
                                 weights_only=False)
        sentiment_model_name = weights_ref.get("sentiment_model", "yiyanghkust/finbert-tone")
        self._logger.info(f"Loading shared sentiment classifier: {sentiment_model_name}")

        # Shared attributes for feature building logic
        ref = self.models.get("balanced") or list(self.models.values())[0]
        self.stock_cols = ref["stock_cols"]
        self.spy_cols = ref["spy_cols"]
        self.stock_scaler = ref["stock_scaler"]
        self.spy_scaler = ref["spy_scaler"]
        self.pca_stock = ref["pca_stock"]
        self.pca_spy = ref["pca_spy"]
        self.target_mean = ref["target_mean"]
        self.target_std = ref["target_std"]
        self.output_network = ref["output_network"]
        
        self.tokenizer, self.sentiment_model, self.canonical_col_for = (
            _load_sentiment_classifier(sentiment_model_name, self.device)
        )

        self._logger.info(f"Successfully loaded {len(self.models)} models.")

    # -----------------------------------------------------------------------
    # Loading helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _extract_state(weights: dict, key: str) -> dict:
        if key not in weights:
            raise KeyError(
                f"Checkpoint missing key '{key}'. Available top-level keys: "
                f"{[k for k in weights.keys() if not k.startswith('_')]}"
            )
        val = weights[key]
        # Handle {"state_dict": {...}} vs {...}
        if isinstance(val, dict) and "state_dict" in val and all(
                isinstance(k, str) for k in val.keys()
        ) and len(val) <= 3:
            return val["state_dict"]
        return val

    # -----------------------------------------------------------------------
    # Feature builders
    # -----------------------------------------------------------------------

    def _build_stock_features(self, stock_history, ticker: str) -> pd.DataFrame:
        rows = [
            {
                "Date": p.date,
                "Open": p.open,
                "High": p.high,
                "Low": p.low,
                "Close": p.close,
                "Volume": p.volume,
                "Adj Close": p.adj_close,
            }
            for p in stock_history
        ]
        if not rows:
            return pd.DataFrame()
        stock_df = pd.DataFrame(rows)
        stock_df["Date"] = pd.to_datetime(stock_df["Date"], errors="coerce")
        stock_df = stock_df.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
        
        # Create features, which drops the 'Close' column
        features_df = _create_stock_features(stock_df.copy(), ticker)
        
        # Re-join 'Close' so it's available for debug signals later
        if not features_df.empty:
            features_df = features_df.merge(stock_df[['Date', 'Close']], on='Date', how='left')
            
        return features_df

    def _build_market_features(self, market_history) -> pd.DataFrame:
        market_parts: list[pd.DataFrame] = []
        for ticker, history in market_history.items():
            part = pd.DataFrame([
                {
                    "Date": p.date,
                    f"{ticker}_Open": p.open,
                    f"{ticker}_High": p.high,
                    f"{ticker}_Low": p.low,
                    f"{ticker}_Close": p.close,
                    f"{ticker}_Volume": p.volume,
                }
                for p in history.points
            ])
            if not part.empty:
                market_parts.append(part)

        if not market_parts:
            return pd.DataFrame()

        market_df = market_parts[0]
        for p in market_parts[1:]:
            market_df = market_df.merge(p, on="Date", how="outer")
        market_df["Date"] = pd.to_datetime(market_df["Date"], errors="coerce")
        market_df = market_df.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)

        # Forward-fill OHLCV across indices so a missing day for one index
        # doesn't poison the feature row for the others.
        ohlcv_cols = [c for c in market_df.columns if c != "Date"]
        market_df[ohlcv_cols] = market_df[ohlcv_cols].ffill()

        # Drop any leading rows that are still NaN (couldn't be ffilled).
        market_df = market_df.dropna(subset=ohlcv_cols, how="all").reset_index(drop=True)

        market_feats = _create_spy_features(market_df)

        # Sanity check
        if not market_feats.empty:
            latest = market_feats.iloc[-1]
            nan_cols = [c for c in self.spy_cols if c in latest.index and pd.isna(latest[c])]
            if nan_cols:
                self._logger.warning(
                    f"Market_feats latest row has {len(nan_cols)} NaN columns. "
                    f"Got {len(market_df)} rows. First NaN cols: {nan_cols[:5]}"
                )

        return market_feats

    def _slice_one_row(
            self,
            feats: pd.DataFrame,
            offset: int,
            expected_cols: list[str],
            *,
            kind: str,
    ) -> Optional[pd.DataFrame]:
        """Pick one row at -1-offset (offset=0 means the latest row).
        Returns None if the offset is out of bounds. Hard-fails on column
        mismatch instead of silent zero-fill."""
        idx = -1 - offset
        if abs(idx) > len(feats):
            return None
        sub = feats.iloc[idx: idx + 1] if idx != -1 else feats.iloc[-1:]

        missing = [c for c in expected_cols if c not in sub.columns]
        if missing:
            raise RuntimeError(
                f"{kind} feature mismatch: missing {len(missing)} columns "
                f"that were present at training. First few: {missing[:5]}"
                f"{'...' if len(missing) > 5 else ''}"
            )

        sub = sub[expected_cols]
        sub = sub.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        return sub

    def _scale(self, df: pd.DataFrame, scaler, pca_model=None) -> torch.Tensor:
        scaled = scaler.transform(df.to_numpy())
        if pca_model:
            scaled = pca_model.transform(scaled)
        scaled = np.nan_to_num(scaled, nan=0.0, posinf=0.0, neginf=0.0)
        return torch.tensor(scaled, device=self.device, dtype=torch.float32)

    def _text_feature(self, tweets) -> torch.Tensor:
        """Returns (1, text_dim) on self.device."""
        text_list = list(tweets) if tweets else []
        feat = _texts_to_sentiment_features(
            text_list,
            self.tokenizer,
            self.sentiment_model,
            self.canonical_col_for,
            device=self.device,
        )
        if feat is None:
            return self.output_network.no_tweet_embedding.detach().unsqueeze(0).to(self.device)
        return feat.to(self.device)

    # -----------------------------------------------------------------------
    # Single forward pass
    # -----------------------------------------------------------------------

    def _predict_single_model(self, model_id, combined_feats, offset, text_feat):
        m = self.models.get(model_id)
        if not m:
            return None

        # Slice one row from the combined dataframe
        idx = -1 - offset
        if abs(idx) > len(combined_feats):
            return None
        
        row_df = combined_feats.iloc[idx: idx + 1] if idx != -1 else combined_feats.iloc[-1:]
        prediction_date = row_df["Date"].iloc[0]
        self._logger.info(f"Model {model_id} using data for Date: {prediction_date} (offset: {offset})")

        # Validate and scale stock features
        missing_stock = [c for c in m["stock_cols"] if c not in row_df.columns]
        if missing_stock:
            raise RuntimeError(f"Stock feature mismatch for {model_id}: missing {len(missing_stock)} columns.")
        
        s_row = row_df[m["stock_cols"]].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        s_tensor = self._scale(s_row, m["stock_scaler"], pca_model=m["pca_stock"])

        # Validate and scale spy features
        missing_spy = [c for c in m["spy_cols"] if c not in row_df.columns]
        if missing_spy:
            raise RuntimeError(f"SPY feature mismatch for {model_id}: missing {len(missing_spy)} columns.")

        i_row = row_df[m["spy_cols"]].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        i_tensor = self._scale(i_row, m["spy_scaler"], pca_model=m["pca_spy"])

        with torch.no_grad():
            s_feat = m["stock_network"](s_tensor)
            i_feat = m["index_network"](i_tensor)

            if s_feat.dim() == 3 and text_feat.dim() == 2:
                text_feat = text_feat.unsqueeze(1).expand(-1, s_feat.size(1), -1)

            combined = torch.cat((s_feat, i_feat, text_feat), dim=-1)
            raw_output = m["output_network"](combined)

            if raw_output.dim() == 3:
                raw_output = raw_output[:, -1, :]

            standardized_val = raw_output.squeeze().item()
            unstandardized_val = (standardized_val * m["target_std"]) + m["target_mean"]

        return float(unstandardized_val)

    def _predict_at_offset(self, model_id, combined_feats, offset, text_feat):
        if model_id == "ensemble":
            weighted_sum = 0.0
            total_weight = 0.0
            for m_id in self.models.keys():
                p = self._predict_single_model(m_id, combined_feats, offset, text_feat)
                if p is not None:
                    # Determine weight based on prediction direction and model accuracy
                    stats = self.model_stats.get(m_id, {"up": 0.5, "down": 0.5})
                    weight = stats["up"] if p > 0 else stats["down"]

                    weighted_sum += p * weight
                    total_weight += weight

            if total_weight == 0:
                return 0.0
            return weighted_sum / total_weight

        pred = self._predict_single_model(model_id, combined_feats, offset, text_feat)
        if pred is None and model_id != "balanced":
            # Fallback to balanced if requested model fails
            pred = self._predict_single_model("balanced", combined_feats, offset, text_feat)

        return pred

    # -----------------------------------------------------------------------
    # RPC handlers
    # -----------------------------------------------------------------------

    def PredictMomentum(self, request, context):
        try:
            self._logger.info("=" * 100)
            self._logger.info(f"PredictMomentum REQUEST: ticker={request.ticker}, model={request.model_type}, offset={request.offset}")
            self._logger.info(f"Input Data: stock_rows={len(request.stock_history)}, market_tickers={list(request.market_history.keys())}, tweets={len(request.tweets)}")

            stock_feats = self._build_stock_features(request.stock_history, request.ticker)
            if stock_feats.empty:
                self._logger.warning(f"Stock features empty for {request.ticker}")
                return momentum_pb2.MomentumResponse(momentum=0.0)

            market_feats = self._build_market_features(request.market_history)
            if market_feats.empty:
                self._logger.warning(f"Market features empty for {request.ticker}")
                return momentum_pb2.MomentumResponse(momentum=0.0)

            # Align features by Date
            combined_feats = pd.merge(stock_feats, market_feats, on="Date", how="inner")
            
            self._logger.info(f"DATA DIAGNOSTIC: stock_rows={len(stock_feats)}, market_rows={len(market_feats)}, merged_rows={len(combined_feats)}")
            if not combined_feats.empty:
                self._logger.info(f"DATE RANGE: start={combined_feats['Date'].min()}, end={combined_feats['Date'].max()}")
            
            if combined_feats.empty:
                self._logger.warning(f"No overlapping dates for {request.ticker} and market indices.")
                self._logger.info(f"Stock Range: {stock_feats['Date'].min()} to {stock_feats['Date'].max()}")
                self._logger.info(f"Market Range: {market_feats['Date'].min()} to {market_feats['Date'].max()}")
                return momentum_pb2.MomentumResponse(momentum=0.0)
            
            combined_feats = combined_feats.sort_values("Date").reset_index(drop=True)
            
            offset = request.offset
            idx = -1 - offset
            if abs(idx) <= len(combined_feats):
                pred_row = combined_feats.iloc[idx]
                self._logger.info(f"Prediction Target Row: Date={pred_row['Date']}, Price={pred_row.get('Close', 'N/A')}")
            else:
                self._logger.warning(f"Offset {offset} (idx {idx}) out of bounds for merged data size {len(combined_feats)}")
            text_feat = self._text_feature(request.tweets)

            # Calculate individual predictions for signal detection
            model_preds = {}
            for m_id in self.models.keys():
                p = self._predict_single_model(m_id, combined_feats, offset, text_feat)
                if p is not None:
                    model_preds[m_id] = p
            
            self._logger.info(f"Individual model predictions: {model_preds}")

            # --- Flash Signal Detection ---
            signals = []
            
            # Leak metadata for debugging
            if abs(idx) <= len(combined_feats):
                p_date = pred_row["Date"]
                p_close = pred_row.get("Close", 0.0)

            # Extract sentiment stats from text_feat
            s_feats = text_feat.view(-1, 5)[0].tolist()

            # Calculate the primary prediction
            model_id = request.model_type or "ensemble"
            if model_id == "ensemble":
                weighted_sum = 0.0
                total_weight = 0.0
                for m_id, p in model_preds.items():
                    stats = self.model_stats.get(m_id, {"up": 0.5, "down": 0.5})
                    weight = stats["up"] if p > 0 else stats["down"]
                    weighted_sum += p * weight
                    total_weight += weight
                pred = weighted_sum / total_weight if total_weight > 0 else 0.0
            else:
                pred = model_preds.get(model_id, 0.0)

            self._logger.info(f"FINAL PREDICTION ({model_id}): {pred:.4f}")
            self._logger.info("=" * 100)

            bearish_p = model_preds.get("bearish")
            bullish_p = model_preds.get("bullish")

            # 1. Bias Flips
            if bearish_p is not None and bearish_p > 0.25:
                signals.append("SIGNAL: Bearish Persona has flipped Bullish")

            if bullish_p is not None and bullish_p < -0.25:
                signals.append("SIGNAL: Bullish Persona has flipped Bearish")

            return momentum_pb2.MomentumResponse(
                momentum=pred,
                model_outputs=model_preds,
                signals=signals
            )


        except Exception as e:
            traceback.print_exc()
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return momentum_pb2.MomentumResponse()

    def BatchPredictMomentum(self, request, context):
        try:
            model_id = request.model_type or "ensemble"

            stock_feats = self._build_stock_features(request.stock_history, request.ticker)
            if stock_feats.empty:
                return momentum_pb2.BatchMomentumResponse(momentums=[0.0] * len(request.offsets))

            market_feats = self._build_market_features(request.market_history)
            if market_feats.empty:
                return momentum_pb2.BatchMomentumResponse(momentums=[0.0] * len(request.offsets))

            # Align features by Date
            combined_feats = pd.merge(stock_feats, market_feats, on="Date", how="inner")
            if combined_feats.empty:
                return momentum_pb2.BatchMomentumResponse(momentums=[0.0] * len(request.offsets))
            
            combined_feats = combined_feats.sort_values("Date").reset_index(drop=True)

            text_feat = self._text_feature(request.tweets)

            results: list[float] = []
            for offset in request.offsets:
                off = max(0, offset)
                pred = self._predict_at_offset(model_id, combined_feats, off, text_feat)
                results.append(pred if pred is not None else 0.0)

            return momentum_pb2.BatchMomentumResponse(momentums=results)

        except Exception as e:
            traceback.print_exc()
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return momentum_pb2.BatchMomentumResponse()


def serve():
    logger: Logger = AppLogger().get_logger(__name__)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    momentum_pb2_grpc.add_MomentumServiceServicer_to_server(MomentumService(), server)
    server.add_insecure_port('[::]:50051')
    logger.info("Starting gRPC server on port 50051...")
    server.start()
    server.wait_for_termination()


if __name__ == '__main__':
    serve()
