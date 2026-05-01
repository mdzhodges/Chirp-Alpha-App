"""
Precompute per-(ticker, Date) sentiment features from `data/data.parquet`
using a financial-text sentiment classifier (default: yiyanghkust/finbert-tone).

For each text in a row's `tweets`/news list, the classifier produces softmax
probabilities (P_bullish, P_bearish, P_neutral). We aggregate across all
texts for that (ticker, Date) row into 5 features:

  [0] mean P(bullish)
  [1] mean P(bearish)
  [2] mean P(neutral)
  [3] count of texts
  [4] std of P(bullish)    -- dispersion: high std = mixed signal day

Memory architecture mirrors the embedding precompute:
  * `sums.f32.bin`         — running sums per row, shape (n_rows, 4)
                             columns: [sum_bull, sum_bear, sum_neu, sum_bull_sq]
  * `counts.i32.bin`       — text count per row, shape (n_rows,)
  * `_progress.json`       — completed row groups, for resume

The saved .pt artifact contains a (n_rows, 5) float32 tensor of features,
plus a separate .subset.pt with a balanced 5k-row sample (50% with text,
50% without) for fast iteration.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import torch
import torch.nn.functional as F
from tqdm import tqdm
from transformers import AutoModelForSequenceClassification, AutoTokenizer
from transformers import logging as transformers_logging

transformers_logging.set_verbosity_error()


# Layout constants for the sums memmap.
N_FEATURES_OUT = 5         # bull, bear, neu, count, std_bull
N_SUM_COLUMNS = 4          # sum_bull, sum_bear, sum_neu, sum_bull_sq


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def _extract_texts_from_arrow(tweets_col: pa.ChunkedArray | pa.Array) -> list[list[str]]:
    if isinstance(tweets_col, pa.ChunkedArray):
        if tweets_col.num_chunks == 0:
            return []
        arr = tweets_col.combine_chunks()
    else:
        arr = tweets_col

    if not (pa.types.is_list(arr.type) or pa.types.is_large_list(arr.type)):
        return [_clean(row) for row in arr.to_pylist()]

    values = arr.values
    if pa.types.is_struct(values.type):
        try:
            text_arr = values.field("text")
        except KeyError:
            return [[] for _ in range(len(arr))]
    else:
        text_arr = values

    texts_flat: list[Any] = text_arr.to_pylist()
    offsets = arr.offsets.to_numpy(zero_copy_only=False)
    if arr.null_count == 0:
        valid_mask = None
    else:
        valid_mask = arr.is_valid().to_numpy(zero_copy_only=False)

    n = len(arr)
    out: list[list[str]] = []
    for i in range(n):
        if valid_mask is not None and not valid_mask[i]:
            out.append([])
            continue
        start = int(offsets[i])
        end = int(offsets[i + 1])
        row_texts: list[str] = []
        for j in range(start, end):
            t = texts_flat[j]
            if isinstance(t, str):
                s = t.strip()
                if s:
                    row_texts.append(s)
        out.append(row_texts)
    return out


def _clean(row: Any) -> list[str]:
    if not isinstance(row, list):
        return []
    out: list[str] = []
    for t in row:
        if isinstance(t, dict):
            t = t.get("text")
        if isinstance(t, str) and t.strip():
            out.append(t.strip())
    return out


# ---------------------------------------------------------------------------
# Classifier loading with fallbacks
# ---------------------------------------------------------------------------

def _load_classifier(model_name: str, device: torch.device) -> tuple[Any, Any, dict]:
    print(f"Loading {model_name}...")

    try:
        tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=False)
    except (ValueError, OSError):
        from transformers import BertTokenizer
        print("  (AutoTokenizer failed; falling back to BertTokenizer)")
        tokenizer = BertTokenizer.from_pretrained(model_name)

    model_kwargs: dict[str, Any] = {}
    if device.type == "cuda":
        model_kwargs["torch_dtype"] = torch.float16

    try:
        model = AutoModelForSequenceClassification.from_pretrained(model_name, **model_kwargs)
    except (ValueError, OSError):
        from transformers import BertForSequenceClassification
        print("  (AutoModelForSequenceClassification failed; falling back to BertForSequenceClassification)")
        model = BertForSequenceClassification.from_pretrained(model_name, num_labels=3, **model_kwargs)

    model.eval()
    model.to(device)

    # Build a label map normalized to {0:bullish, 1:bearish, 2:neutral} (canonical order).
    cfg_id2label = getattr(model.config, "id2label", None) or {}
    label_map: dict[int, str] = {}
    for idx, name in cfg_id2label.items():
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
        # Hardcoded fallback for known model names.
        if "finbert-tone" in model_name.lower():
            label_map = {0: "neutral", 1: "bullish", 2: "bearish"}
        elif "prosus" in model_name.lower():
            label_map = {0: "bullish", 1: "bearish", 2: "neutral"}
        elif "fintwitbert-sentiment" in model_name.lower():
            label_map = {0: "neutral", 1: "bullish", 2: "bearish"}

    # Build canonical column index: for each model output index, where does
    # it map in [bullish, bearish, neutral]?
    canonical_col_for: dict[int, int] = {}
    for idx, lbl in label_map.items():
        col = {"bullish": 0, "bearish": 1, "neutral": 2}.get(lbl)
        if col is not None:
            canonical_col_for[idx] = col

    print(f"  label_map: {label_map}")
    print(f"  canonical_col_for: {canonical_col_for}")
    if len(canonical_col_for) != 3:
        raise RuntimeError(
            f"Could not resolve all 3 sentiment classes for {model_name}. "
            f"Got {label_map}. Edit the hardcoded fallback in _load_classifier."
        )

    return tokenizer, model, canonical_col_for


@torch.inference_mode()
def _classify_batch(
    tokenizer: Any,
    model: Any,
    canonical_col_for: dict[int, int],
    texts: list[str],
    *,
    device: torch.device,
    max_length: int,
) -> torch.Tensor:
    """Returns canonical probabilities, shape (n, 3) in
    [bullish, bearish, neutral] order, fp32 on CPU."""
    inputs = tokenizer(
        texts,
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=max_length,
    )
    inputs = {k: v.to(device, non_blocking=True) for k, v in inputs.items()}
    out = model(**inputs)
    logits = out.logits  # (n, 3) on device, possibly fp16
    probs = F.softmax(logits.float(), dim=-1).to("cpu")  # (n, 3) fp32

    # Permute to canonical [bullish, bearish, neutral].
    canonical = torch.zeros_like(probs)
    for idx, col in canonical_col_for.items():
        canonical[:, col] = probs[:, idx]
    return canonical


# ---------------------------------------------------------------------------
# Streaming buffered classifier. Writes to memmap-backed sums/counts.
# ---------------------------------------------------------------------------

class StreamingClassifier:
    def __init__(
        self,
        tokenizer: Any,
        model: Any,
        canonical_col_for: dict[int, int],
        sums: torch.Tensor,         # memmap-backed (n_rows, 4) fp32
        counts: torch.Tensor,       # memmap-backed (n_rows,)   int32
        *,
        device: torch.device,
        max_length: int,
        batch_size: int,
        flush_every: int,
        pbar: tqdm,
    ) -> None:
        self.tokenizer = tokenizer
        self.model = model
        self.canonical_col_for = canonical_col_for
        self.sums = sums
        self.counts = counts
        self.device = device
        self.max_length = max_length
        self.batch_size = batch_size
        self.flush_every = flush_every
        self.pbar = pbar
        self._texts: list[str] = []
        self._row_ids: list[int] = []

    def add(self, text: str, final_row_id: int) -> None:
        self._texts.append(text)
        self._row_ids.append(final_row_id)
        if len(self._texts) >= self.flush_every:
            self.flush()

    def flush(self) -> None:
        if not self._texts:
            return
        texts = self._texts
        row_ids_np = np.asarray(self._row_ids, dtype=np.int64)
        self._texts = []
        self._row_ids = []

        order = np.argsort([len(t) for t in texts], kind="stable")
        for i in range(0, len(order), self.batch_size):
            sl = order[i : i + self.batch_size]
            batch_texts = [texts[k] for k in sl]
            batch_rows = torch.from_numpy(row_ids_np[sl])
            probs = _classify_batch(
                self.tokenizer,
                self.model,
                self.canonical_col_for,
                batch_texts,
                device=self.device,
                max_length=self.max_length,
            )  # (b, 3) -> [bull, bear, neu]

            # Build the 4-column update: bull, bear, neu, bull**2
            update = torch.empty((probs.shape[0], 4), dtype=torch.float32)
            update[:, 0] = probs[:, 0]
            update[:, 1] = probs[:, 1]
            update[:, 2] = probs[:, 2]
            update[:, 3] = probs[:, 0] ** 2

            self.sums.index_add_(0, batch_rows, update)
            self.counts.index_add_(
                0, batch_rows, torch.ones(len(batch_rows), dtype=self.counts.dtype)
            )
            self.pbar.update(len(batch_texts))


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------

def _check_disk(spill_dir: Path, need_gb: float) -> str:
    fs_type = ""
    try:
        resolved = str(spill_dir.resolve())
        best = ""
        with open("/proc/mounts") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 3:
                    mp, this_fs = parts[1], parts[2]
                    if resolved.startswith(mp) and len(mp) > len(best):
                        best = mp
                        fs_type = this_fs
    except FileNotFoundError:
        pass

    if fs_type in {"tmpfs", "ramfs"}:
        raise RuntimeError(
            f"Checkpoint dir {spill_dir} is on {fs_type} (RAM-backed). "
            f"Use --checkpoint-dir to point at a real disk."
        )

    free_gb = shutil.disk_usage(spill_dir).free / 1e9
    if free_gb < need_gb * 1.1:
        raise RuntimeError(
            f"Checkpoint dir {spill_dir} has only {free_gb:.1f} GB free; "
            f"need ~{need_gb:.1f} GB."
        )
    return fs_type


def _open_checkpoint(
    ckpt_dir: Path,
    *,
    n_rows: int,
    sort_signature: dict,
) -> tuple[torch.Tensor, torch.Tensor, np.memmap, np.memmap, dict, Path]:
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    sums_path = ckpt_dir / "sums.f32.bin"
    counts_path = ckpt_dir / "counts.i32.bin"
    progress_path = ckpt_dir / "_progress.json"

    expected_sums = n_rows * N_SUM_COLUMNS * 4
    expected_counts = n_rows * 4

    fresh = True
    progress: dict = {}
    if progress_path.exists() and sums_path.exists() and counts_path.exists():
        try:
            progress = json.loads(progress_path.read_text())
            ok = (
                progress.get("n_rows") == n_rows
                and progress.get("n_sum_columns") == N_SUM_COLUMNS
                and progress.get("sort_signature") == sort_signature
                and sums_path.stat().st_size == expected_sums
                and counts_path.stat().st_size == expected_counts
            )
            if ok:
                fresh = False
            else:
                print("Existing checkpoint is incompatible; starting fresh.")
        except (OSError, ValueError):
            print("Existing checkpoint is unreadable; starting fresh.")

    if fresh:
        for path, size in [(sums_path, expected_sums), (counts_path, expected_counts)]:
            with open(path, "wb") as f:
                f.truncate(size)
        progress = {
            "n_rows": n_rows,
            "n_sum_columns": N_SUM_COLUMNS,
            "sort_signature": sort_signature,
            "completed_row_groups": [],
            "texts_done": 0,
        }
        progress_path.write_text(json.dumps(progress))

    sums_mm = np.memmap(sums_path, dtype=np.float32, mode="r+", shape=(n_rows, N_SUM_COLUMNS))
    counts_mm = np.memmap(counts_path, dtype=np.int32, mode="r+", shape=(n_rows,))
    sums_t = torch.from_numpy(sums_mm)
    counts_t = torch.from_numpy(counts_mm)
    return sums_t, counts_t, sums_mm, counts_mm, progress, progress_path


def _save_progress(
    progress: dict,
    progress_path: Path,
    sums_mm: np.memmap,
    counts_mm: np.memmap,
) -> None:
    sums_mm.flush()
    counts_mm.flush()
    tmp = progress_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(progress))
    os.replace(tmp, progress_path)


# ---------------------------------------------------------------------------
# Subset selection
# ---------------------------------------------------------------------------

def _make_balanced_subset(
    features: torch.Tensor,
    has_tweets: torch.Tensor,
    counts: torch.Tensor,
    tickers: list[str] | None,
    dates: list[str] | None,
    *,
    target_size: int,
    seed: int,
) -> dict:
    """Pick `target_size` rows with exactly 50% having text and 50% without.
    If either bucket has fewer rows than target_size/2, the smaller one caps
    the subset and we balance to the smaller count (still 50/50)."""
    n = features.shape[0]
    rng = np.random.default_rng(seed)

    has_idx = np.where(has_tweets.numpy())[0]
    no_idx = np.where(~has_tweets.numpy())[0]

    half = target_size // 2
    take_has = min(half, len(has_idx))
    take_no = min(half, len(no_idx))
    # If we couldn't get a full half from one side, also cap the other side
    # to keep the 50/50 ratio honest. The caller probably wants exact balance.
    take = min(take_has, take_no)

    if take == 0:
        return {
            "indices": torch.empty((0,), dtype=torch.int64),
            "features": features[:0],
            "tweet_count": counts[:0],
            "has_tweets": has_tweets[:0],
            "ticker": [],
            "Date": [],
            "note": "Could not build subset: one bucket is empty.",
        }

    chosen_has = rng.choice(has_idx, size=take, replace=False)
    chosen_no = rng.choice(no_idx, size=take, replace=False)
    chosen = np.concatenate([chosen_has, chosen_no])
    rng.shuffle(chosen)
    chosen_t = torch.from_numpy(chosen.astype(np.int64))

    sub_features = features.index_select(0, chosen_t).clone()
    sub_counts = counts.index_select(0, chosen_t).clone()
    sub_has = has_tweets.index_select(0, chosen_t).clone()
    sub_ticker = [tickers[i] for i in chosen.tolist()] if tickers is not None else None
    sub_date = [dates[i] for i in chosen.tolist()] if dates is not None else None

    return {
        "indices": chosen_t,
        "features": sub_features,
        "tweet_count": sub_counts,
        "has_tweets": sub_has,
        "ticker": sub_ticker,
        "Date": sub_date,
        "note": f"Balanced subset: {take} with text + {take} without text.",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/data.parquet")
    parser.add_argument(
        "--output",
        default="data/sentiment_features.pt",
        help="Full sentiment features artifact.",
    )
    parser.add_argument(
        "--subset-output",
        default=None,
        help="Balanced 50/50 subset artifact path. Defaults to <output>.subset.pt",
    )
    parser.add_argument(
        "--subset-size",
        type=int,
        default=5000,
        help="Total rows in the subset (will be exactly halved between with-text and without-text).",
    )
    parser.add_argument("--subset-seed", type=int, default=0)
    parser.add_argument("--model", default="yiyanghkust/finbert-tone")
    parser.add_argument("--max-length", type=int, default=128)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--flush-every", type=int, default=8192)
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    parser.add_argument("--no-sort", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--checkpoint-dir",
        default=None,
        help="Defaults to '<output>.ckpt'. Must be on a real disk with ~n_rows*20 bytes free.",
    )
    parser.add_argument("--keep-checkpoint", action="store_true")
    args = parser.parse_args()
    print(args)

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Input parquet not found: {input_path}")

    pf = pq.ParquetFile(input_path)
    schema_names = set(pf.schema_arrow.names)
    if "tweets" not in schema_names:
        raise ValueError("Expected a `tweets` column in the parquet.")

    n_rows_total = pf.metadata.num_rows
    if args.limit and args.limit > 0:
        n_rows_total = min(n_rows_total, args.limit)
    print(f"Parquet rows: {pf.metadata.num_rows:,}  (processing: {n_rows_total:,})")
    print(f"Row groups: {pf.num_row_groups}")

    # --- Sort order (same logic as embeddings precompute) -----------------
    final_order: np.ndarray | None = None
    sorted_ticker: list[str] | None = None
    sorted_date: list[str] | None = None
    if not args.no_sort and "Date" in schema_names:
        key_cols = [c for c in ("ticker", "Date") if c in schema_names]
        keys_tbl = pf.read(columns=key_cols)
        if args.limit and args.limit > 0:
            keys_tbl = keys_tbl.slice(0, n_rows_total)
        keys_df = keys_tbl.to_pandas()
        del keys_tbl
        sorted_idx = keys_df.sort_values(key_cols, kind="stable").index.to_numpy()
        final_order = np.empty(n_rows_total, dtype=np.int64)
        final_order[sorted_idx] = np.arange(n_rows_total, dtype=np.int64)
        if "ticker" in keys_df.columns:
            sorted_ticker = keys_df["ticker"].iloc[sorted_idx].astype(str).tolist()
        if "Date" in keys_df.columns:
            sorted_date = keys_df["Date"].iloc[sorted_idx].astype(str).tolist()
        del keys_df, sorted_idx
        gc.collect()
    elif not args.no_sort:
        print("No `Date` column; emitting in parquet order.")

    # --- Device + classifier ---------------------------------------------
    if args.device == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(args.device)
    print(f"Device: {device}")

    tokenizer, model, canonical_col_for = _load_classifier(args.model, device)

    # --- Open / resume checkpoint ----------------------------------------
    output_path = Path(args.output)
    ckpt_dir = Path(args.checkpoint_dir) if args.checkpoint_dir else Path(str(output_path) + ".ckpt")

    sums_gb = n_rows_total * N_SUM_COLUMNS * 4 / 1e9
    counts_gb = n_rows_total * 4 / 1e9
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    fs_type = _check_disk(ckpt_dir, sums_gb + counts_gb)
    print(f"Checkpoint: {ckpt_dir}  (~{sums_gb*1000:.0f} MB sums + {counts_gb*1000:.0f} MB counts, fs={fs_type or 'unknown'})")

    sort_signature = {
        "no_sort": bool(args.no_sort),
        "sort_keys": [c for c in ("ticker", "Date") if c in schema_names] if not args.no_sort else [],
        "limit": int(args.limit) if args.limit else 0,
        "model": args.model,
    }
    sums, counts, sums_mm, counts_mm, progress, progress_path = _open_checkpoint(
        ckpt_dir,
        n_rows=n_rows_total,
        sort_signature=sort_signature,
    )
    completed_groups = set(progress.get("completed_row_groups", []))
    if completed_groups:
        print(f"Resuming: {len(completed_groups)}/{pf.num_row_groups} row groups already done")

    # --- Stream + classify -----------------------------------------------
    texts_pbar = tqdm(
        total=None, desc="Texts ", unit="t", smoothing=0.05, position=0,
        initial=int(progress.get("texts_done", 0)),
    )
    rows_pbar = tqdm(total=n_rows_total, desc="Rows  ", unit="row", position=1)
    classifier = StreamingClassifier(
        tokenizer=tokenizer,
        model=model,
        canonical_col_for=canonical_col_for,
        sums=sums,
        counts=counts,
        device=device,
        max_length=args.max_length,
        batch_size=args.batch_size,
        flush_every=args.flush_every,
        pbar=texts_pbar,
    )

    streamed_idx = 0
    try:
        for rg in range(pf.num_row_groups):
            rg_n_rows = pf.metadata.row_group(rg).num_rows
            if args.limit and streamed_idx + rg_n_rows > n_rows_total:
                rg_n_rows_used = n_rows_total - streamed_idx
            else:
                rg_n_rows_used = rg_n_rows

            if rg in completed_groups:
                streamed_idx += rg_n_rows_used
                rows_pbar.update(rg_n_rows_used)
                if streamed_idx >= n_rows_total:
                    break
                continue

            tbl = pf.read_row_group(rg, columns=["tweets"])
            row_texts = _extract_texts_from_arrow(tbl.column("tweets"))
            del tbl
            if args.limit and streamed_idx + len(row_texts) > n_rows_total:
                row_texts = row_texts[: n_rows_total - streamed_idx]

            texts_in_group = 0
            for local_i, rt in enumerate(row_texts):
                if not rt:
                    continue
                streamed_i = streamed_idx + local_i
                final_i = int(final_order[streamed_i]) if final_order is not None else streamed_i
                for t in rt:
                    classifier.add(t, final_i)
                    texts_in_group += 1

            streamed_idx += len(row_texts)
            rows_pbar.update(len(row_texts))
            del row_texts
            gc.collect()

            classifier.flush()
            progress["texts_done"] = int(progress.get("texts_done", 0)) + texts_in_group
            progress.setdefault("completed_row_groups", []).append(rg)
            _save_progress(progress, progress_path, sums_mm, counts_mm)

            if streamed_idx >= n_rows_total:
                break

        classifier.flush()
        _save_progress(progress, progress_path, sums_mm, counts_mm)
    finally:
        texts_pbar.close()
        rows_pbar.close()

    # --- Free model + GPU -------------------------------------------------
    del model, tokenizer, classifier
    gc.collect()
    if device.type == "cuda":
        torch.cuda.empty_cache()

    # --- Finalize: compute the 5 features per row ------------------------
    print("Computing features...")
    counts_ram = torch.from_numpy(counts.numpy().copy()).to(torch.int64)
    has_tweets = counts_ram > 0

    # Output features tensor: (n_rows, 5)
    features = torch.zeros((n_rows_total, N_FEATURES_OUT), dtype=torch.float32)

    chunk = 500_000  # plenty since memmap is small now (~200 MB total)
    finalize_pbar = tqdm(total=n_rows_total, desc="Finalize", unit="row")
    for i in range(0, n_rows_total, chunk):
        j = min(i + chunk, n_rows_total)
        s = torch.from_numpy(np.array(sums[i:j].numpy(), copy=True))  # (b, 4)
        c = counts_ram[i:j].to(torch.float32)
        mask = c > 0

        if mask.any():
            cm = c[mask].unsqueeze(1)
            sm = s[mask]

            mean_bull = sm[:, 0] / cm[:, 0]
            mean_bear = sm[:, 1] / cm[:, 0]
            mean_neu = sm[:, 2] / cm[:, 0]
            # std of P(bullish) via E[X^2] - (E[X])^2, clamped at 0
            mean_sq = sm[:, 3] / cm[:, 0]
            var = (mean_sq - mean_bull ** 2).clamp(min=0.0)
            std_bull = var.sqrt()

            features[i:j][mask, 0] = mean_bull
            features[i:j][mask, 1] = mean_bear
            features[i:j][mask, 2] = mean_neu
            features[i:j][mask, 3] = c[mask]
            features[i:j][mask, 4] = std_bull

        del s
        finalize_pbar.update(j - i)
    finalize_pbar.close()

    del sums, counts, sums_mm, counts_mm
    gc.collect()

    # --- Save full artifact ----------------------------------------------
    output_path.parent.mkdir(parents=True, exist_ok=True)
    feature_names = ["mean_bullish", "mean_bearish", "mean_neutral", "count", "std_bullish"]
    artifact = {
        "sentiment_features": features,           # (n, 5) fp32
        "feature_names": feature_names,
        "tweet_count": counts_ram,
        "has_tweets": has_tweets,
        "ticker": sorted_ticker,
        "Date": sorted_date,
        "model_name": args.model,
        "max_length": int(args.max_length),
        "label_order": ["bullish", "bearish", "neutral"],
        "sorted_by": ["ticker", "Date"] if (final_order is not None) else None,
    }
    torch.save(artifact, output_path)
    print(
        f"Saved: {output_path}  rows={n_rows_total:,}  "
        f"with_text={int(has_tweets.sum()):,}  total_texts={int(counts_ram.sum()):,}"
    )

    # --- Save balanced 50/50 subset --------------------------------------
    subset_output = (
        Path(args.subset_output) if args.subset_output
        else output_path.with_suffix(".subset.pt")
    )
    subset = _make_balanced_subset(
        features=features,
        has_tweets=has_tweets,
        counts=counts_ram,
        tickers=sorted_ticker,
        dates=sorted_date,
        target_size=args.subset_size,
        seed=args.subset_seed,
    )
    print(subset["note"])
    if subset["indices"].numel() > 0:
        subset_artifact = {
            "sentiment_features": subset["features"],
            "feature_names": feature_names,
            "tweet_count": subset["tweet_count"],
            "has_tweets": subset["has_tweets"],
            "ticker": subset["ticker"],
            "Date": subset["Date"],
            "indices_in_full": subset["indices"],
            "model_name": args.model,
            "label_order": ["bullish", "bearish", "neutral"],
            "subset_seed": args.subset_seed,
        }
        torch.save(subset_artifact, subset_output)
        print(
            f"Saved subset: {subset_output}  rows={subset['indices'].numel():,}  "
            f"(50% with text, 50% without)"
        )

    # --- Cleanup ---------------------------------------------------------
    if not args.keep_checkpoint:
        try:
            shutil.rmtree(ckpt_dir)
            print(f"Removed checkpoint: {ckpt_dir}")
        except OSError as e:
            print(f"Warning: couldn't remove checkpoint dir {ckpt_dir}: {e}")
    else:
        print(f"Kept checkpoint: {ckpt_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())