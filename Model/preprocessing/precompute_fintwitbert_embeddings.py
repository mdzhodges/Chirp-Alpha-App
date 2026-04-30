"""
Precompute FinTwitBERT tweet embeddings from `data/data.parquet` and save to a `.pt` file.

Streaming version tuned for ~8 GB VRAM and large parquets:

  * reads parquet via pyarrow row-group by row-group, only the columns needed
  * extracts tweet text directly from the Arrow `list<struct>` (no pandas object dtype)
  * keeps sums/counts in RAM (n_rows * 768 * 4 bytes; e.g. 15.7M rows = ~48 GB)
  * streams tweets across row groups and fires length-bucketed GPU batches as
    soon as a small window fills, so the first batch hits the GPU within seconds
  * uses fp16 model weights on CUDA to fit comfortably in 8 GB VRAM and speed
    up inference; accumulation stays in fp32 for numerical safety
  * fp16 final output to halve the saved artifact
"""

from __future__ import annotations

import argparse
import gc
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import torch
from tqdm import tqdm
from transformers import AutoModel, AutoTokenizer
from transformers import logging as transformers_logging

transformers_logging.set_verbosity_error()


# ---------------------------------------------------------------------------
# Tweet text extraction from Arrow
# ---------------------------------------------------------------------------

def _extract_texts_from_arrow(tweets_col: pa.ChunkedArray | pa.Array) -> list[list[str]]:
    """
    Pull tweet `text` strings out of an Arrow `list<struct<text: string, ...>>`
    column without going through pandas object dtype.
    """
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
# Embedding helpers
# ---------------------------------------------------------------------------

@torch.inference_mode()
def _embed_batch(
    tokenizer: Any,
    model: Any,
    texts: list[str],
    *,
    device: torch.device,
    max_length: int,
) -> torch.Tensor:
    inputs = tokenizer(
        texts,
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=max_length,
    )
    inputs = {k: v.to(device, non_blocking=True) for k, v in inputs.items()}
    outputs = model(**inputs)
    cls = outputs.last_hidden_state[:, 0, :]
    return cls.detach().to("cpu", dtype=torch.float32)


# ---------------------------------------------------------------------------
# Streaming buffered embedder: collects texts across row groups, fires
# length-bucketed batches as soon as a small window fills.
# ---------------------------------------------------------------------------

class StreamingEmbedder:
    def __init__(
        self,
        tokenizer: Any,
        model: Any,
        sums: torch.Tensor,
        counts: torch.Tensor,
        *,
        device: torch.device,
        max_length: int,
        batch_size: int,
        flush_every: int,
        pbar: tqdm,
    ) -> None:
        self.tokenizer = tokenizer
        self.model = model
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

        # Length-bucket within this window only (bounded Python work per flush).
        order = np.argsort([len(t) for t in texts], kind="stable")
        for i in range(0, len(order), self.batch_size):
            sl = order[i : i + self.batch_size]
            batch_texts = [texts[k] for k in sl]
            batch_rows = torch.from_numpy(row_ids_np[sl])
            cls = _embed_batch(
                self.tokenizer,
                self.model,
                batch_texts,
                device=self.device,
                max_length=self.max_length,
            )
            self.sums.index_add_(0, batch_rows, cls)
            self.counts.index_add_(
                0, batch_rows, torch.ones(len(batch_rows), dtype=self.counts.dtype)
            )
            self.pbar.update(len(batch_texts))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/data.parquet")
    parser.add_argument("--output", default="data/fintwitbert_tweet_embeddings.pt")
    parser.add_argument("--model", default="StephanAkkerman/FinTwitBERT")
    parser.add_argument("--max-length", type=int, default=128)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument(
        "--flush-every",
        type=int,
        default=8192,
        help="Flush buffer to GPU every N tweets. Smaller = sooner first batch + "
             "more frequent progress updates. Larger = better length bucketing.",
    )
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    parser.add_argument("--dtype", default="fp16", choices=["fp16", "fp32"])
    parser.add_argument("--no-sort", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
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

    # --- Compute final sort order from key columns only -------------------
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

    # --- Dry run -----------------------------------------------------------
    if args.dry_run:
        total_tweets = 0
        rows_seen = 0
        for batch in pf.iter_batches(batch_size=50_000, columns=["tweets"]):
            row_texts = _extract_texts_from_arrow(batch.column("tweets"))
            for rt in row_texts:
                total_tweets += len(rt)
                rows_seen += 1
                if args.limit and rows_seen >= args.limit:
                    break
            if args.limit and rows_seen >= args.limit:
                break
        print(
            f"rows={rows_seen:,} total_tweets={total_tweets:,} "
            f"avg_tweets_per_row={total_tweets / max(rows_seen, 1):.3f}"
        )
        return 0

    # --- Load model --------------------------------------------------------
    if args.device == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(args.device)
    print(f"Device: {device}")

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    # Load directly in fp16 on CUDA to halve VRAM and speed up inference.
    model_kwargs: dict[str, Any] = {}
    if device.type == "cuda":
        model_kwargs["torch_dtype"] = torch.float16
    model = AutoModel.from_pretrained(args.model, **model_kwargs)
    model.eval()
    model.to(device)

    hidden_size = int(getattr(model.config, "hidden_size", 768))

    # --- Allocate accumulators in RAM -------------------------------------
    accum_gb = n_rows_total * hidden_size * 4 / 1e9
    print(f"Accumulator: {accum_gb:.1f} GB in RAM (sums fp32) + {n_rows_total*4/1e9:.2f} GB counts")
    sums = torch.zeros((n_rows_total, hidden_size), dtype=torch.float32)
    counts = torch.zeros((n_rows_total,), dtype=torch.int32)

    # --- Stream and embed --------------------------------------------------
    tweets_pbar = tqdm(total=None, desc="Tweets", unit="tw", smoothing=0.05, position=0)
    rows_pbar = tqdm(total=n_rows_total, desc="Rows  ", unit="row", position=1)
    embedder = StreamingEmbedder(
        tokenizer=tokenizer,
        model=model,
        sums=sums,
        counts=counts,
        device=device,
        max_length=args.max_length,
        batch_size=args.batch_size,
        flush_every=args.flush_every,
        pbar=tweets_pbar,
    )

    streamed_idx = 0
    try:
        for rg in range(pf.num_row_groups):
            tbl = pf.read_row_group(rg, columns=["tweets"])
            row_texts = _extract_texts_from_arrow(tbl.column("tweets"))
            del tbl
            if args.limit and streamed_idx + len(row_texts) > n_rows_total:
                row_texts = row_texts[: n_rows_total - streamed_idx]

            for local_i, rt in enumerate(row_texts):
                if not rt:
                    continue
                streamed_i = streamed_idx + local_i
                final_i = int(final_order[streamed_i]) if final_order is not None else streamed_i
                for t in rt:
                    embedder.add(t, final_i)

            streamed_idx += len(row_texts)
            rows_pbar.update(len(row_texts))
            del row_texts
            gc.collect()
            if streamed_idx >= n_rows_total:
                break

        embedder.flush()
    finally:
        tweets_pbar.close()
        rows_pbar.close()

    # --- Free the model + GPU state before the big RAM-heavy finalize -----
    # Nothing below needs the model, and BERT weights + CUDA context can
    # easily be a couple of GB. Drop them so the cast has more headroom.
    del model, tokenizer, embedder
    gc.collect()
    if device.type == "cuda":
        torch.cuda.empty_cache()

    # --- Compute means (chunked, in-place) --------------------------------
    # Peak extra RAM here is ~one chunk of fp16 output, not a full duplicate
    # of `sums`. We preallocate `means` and fill it chunk by chunk, doing the
    # divide in place inside `sums` so we never hold both full tensors twice.
    print("Computing means and writing artifact...")
    out_dtype = torch.float16 if args.dtype == "fp16" else torch.float32

    has_tweets = counts > 0
    means = torch.empty((n_rows_total, hidden_size), dtype=out_dtype)

    chunk = 200_000  # ~0.6 GB of fp32 per chunk at hidden=768
    finalize_pbar = tqdm(total=n_rows_total, desc="Finalize", unit="row")
    for i in range(0, n_rows_total, chunk):
        j = min(i + chunk, n_rows_total)
        c = counts[i:j].to(torch.float32)
        mask = c > 0
        if mask.any():
            # In-place divide on the slice view of `sums`.
            sums[i:j][mask] /= c[mask].unsqueeze(1)
        # Cast just this slice to the output dtype and copy into `means`.
        means[i:j] = sums[i:j].to(out_dtype)
        # Zero the slice we're done with so memory pages can be reclaimed
        # (Linux won't actually reclaim until we del sums, but this keeps
        # the working set predictable).
        sums[i:j].zero_()
        finalize_pbar.update(j - i)
    finalize_pbar.close()

    del sums
    gc.collect()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    artifact = {
        "tweet_embedding": means,
        "tweet_count": counts,
        "has_tweets": has_tweets,
        "ticker": sorted_ticker,
        "Date": sorted_date,
        "model_name": args.model,
        "max_length": int(args.max_length),
        "pooling": "mean_of_tweet_cls",
        "dtype": args.dtype,
        "sorted_by": ["ticker", "Date"] if (final_order is not None) else None,
    }
    torch.save(artifact, output_path)
    print(
        f"Saved: {output_path} (rows={n_rows_total:,}, "
        f"total_tweets={int(counts.sum()):,}, hidden={hidden_size}, dtype={args.dtype})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())