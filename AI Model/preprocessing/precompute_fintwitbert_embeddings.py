"""
Precompute FinTwitBERT tweet embeddings from `data/data.parquet` and save to a `.pt` file.

The training loop currently computes a per-row tweet feature by:
  1) encoding each tweet text with FinTwitBERT
  2) taking the CLS embedding for each tweet
  3) averaging embeddings across tweets in the same (ticker, Date) row

This script does the same aggregation offline and saves an artifact you can load later.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import torch
from tqdm import tqdm
from transformers import AutoModel, AutoTokenizer
from transformers import logging as transformers_logging

transformers_logging.set_verbosity_error()


def _iter_row_tweet_texts(tweets_value: Any) -> list[str]:
    if tweets_value is None:
        return []
    if isinstance(tweets_value, list):
        iterable = tweets_value
    else:
        # Pandas may load parquet list<struct> as a numpy.ndarray of dicts.
        try:
            import numpy as np  # type: ignore
        except Exception:  # pragma: no cover
            np = None  # type: ignore
        if np is not None and isinstance(tweets_value, np.ndarray):
            iterable = tweets_value.tolist()
        elif hasattr(tweets_value, "__iter__") and not isinstance(tweets_value, (str, bytes, dict)):
            iterable = list(tweets_value)
        else:
            return []

    texts: list[str] = []
    for t in iterable:
        if isinstance(t, dict):
            text = t.get("text")
        else:
            text = None
        if isinstance(text, str) and text.strip():
            texts.append(text)
    return texts


def _chunks(seq: list[Any], n: int) -> Iterable[list[Any]]:
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


@torch.no_grad()
def _embed_batch(
    tokenizer: Any,
    model: Any,
    texts: list[str],
    *,
    device: torch.device,
    max_length: int,
    autocast_enabled: bool,
) -> torch.Tensor:
    inputs = tokenizer(
        texts,
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=max_length,
    )
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.amp.autocast(device_type=device.type, enabled=autocast_enabled):
        outputs = model(**inputs)
        cls = outputs.last_hidden_state[:, 0, :]
    return cls.detach().to("cpu", dtype=torch.float32)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Precompute per-row tweet embeddings using FinTwitBERT and save as a .pt file."
    )
    parser.add_argument(
        "--input",
        default="data/data.parquet",
        help="Path to the input parquet (default: data/data.parquet).",
    )
    parser.add_argument(
        "--output",
        default="data/fintwitbert_tweet_embeddings.pt",
        help="Path to the output .pt file (default: data/fintwitbert_tweet_embeddings.pt).",
    )
    parser.add_argument(
        "--model",
        default="StephanAkkerman/FinTwitBERT",
        help="HuggingFace model name or path (default matches architecture/models/encoder.py).",
    )
    parser.add_argument("--max-length", type=int, default=128)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument(
        "--device",
        default="auto",
        choices=["auto", "cpu", "cuda"],
        help="Device to run embeddings on (default: auto).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read and validate the input parquet without loading the model.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="If set, only process the first N rows (useful for quick tests).",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Input parquet not found: {input_path}")

    df = pd.read_parquet(input_path)
    if "tweets" not in df.columns:
        raise ValueError("Expected a `tweets` column in the parquet.")
    if "Date" in df.columns:
        df = df.sort_values("Date").reset_index(drop=True)
    if args.limit and args.limit > 0:
        df = df.head(args.limit).reset_index(drop=True)

    # Basic sanity stats (also used by --dry-run).
    tweet_counts = []
    total_tweets = 0
    for tweets_value in df["tweets"].tolist():
        n = len(_iter_row_tweet_texts(tweets_value))
        tweet_counts.append(n)
        total_tweets += n

    if args.dry_run:
        print(f"rows={len(df):,} total_tweets={total_tweets:,} avg_tweets_per_row={total_tweets/max(len(df),1):.3f}")
        return 0

    if args.device == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(args.device)

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModel.from_pretrained(args.model)
    model.eval()
    model.to(device)

    hidden_size = int(getattr(model.config, "hidden_size", 768))

    # Aggregate tweet CLS embeddings per row using streaming `index_add_`.
    n_rows = len(df)
    sums = torch.zeros((n_rows, hidden_size), dtype=torch.float32)
    counts = torch.zeros((n_rows,), dtype=torch.int64)

    buffered_texts: list[str] = []
    buffered_row_ids: list[int] = []

    autocast_enabled = device.type == "cuda"

    def flush_buffer() -> None:
        nonlocal buffered_texts, buffered_row_ids, sums, counts
        if not buffered_texts:
            return
        cls = _embed_batch(
            tokenizer,
            model,
            buffered_texts,
            device=device,
            max_length=args.max_length,
            autocast_enabled=autocast_enabled,
        )
        row_ids = torch.tensor(buffered_row_ids, dtype=torch.int64)
        sums.index_add_(0, row_ids, cls)
        counts.index_add_(0, row_ids, torch.ones(len(buffered_row_ids), dtype=torch.int64))
        buffered_texts = []
        buffered_row_ids = []

    for row_id, tweets_value in enumerate(tqdm(df["tweets"].tolist(), desc="Rows")):
        texts = _iter_row_tweet_texts(tweets_value)
        for text in texts:
            buffered_texts.append(text)
            buffered_row_ids.append(row_id)
            if len(buffered_texts) >= args.batch_size:
                flush_buffer()
    flush_buffer()

    has_tweets = counts > 0
    means = torch.zeros_like(sums)
    if has_tweets.any():
        means[has_tweets] = sums[has_tweets] / counts[has_tweets].unsqueeze(1).to(torch.float32)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    artifact = {
        "tweet_embedding": means,  # [num_rows, hidden_size]
        "tweet_count": counts,  # [num_rows]
        "has_tweets": has_tweets,  # [num_rows]
        "ticker": df["ticker"].astype(str).tolist() if "ticker" in df.columns else None,
        "Date": df["Date"].astype(str).tolist() if "Date" in df.columns else None,
        "model_name": args.model,
        "max_length": int(args.max_length),
        "pooling": "mean_of_tweet_cls",
    }
    torch.save(artifact, output_path)
    print(f"Saved: {output_path} (rows={n_rows:,}, total_tweets={int(counts.sum()):,}, hidden={hidden_size})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
