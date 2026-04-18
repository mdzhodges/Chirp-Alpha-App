"""
Flatten nested tweet JSON files into clean JSONL.

Usage:
    python flatten_tweets.py /path/to/data /path/to/output.jsonl

Expects directory structure: {root}/{TICKER}/{DATE} where each DATE file
contains one JSON object per line (JSONL).
"""

import json
import sys
from pathlib import Path
from typing import Any


def flatten(obj: Any, prefix: str = "") -> dict:
    """Recursively flatten a nested dict. Lists are JSON-serialized."""
    out = {}
    if not isinstance(obj, dict):
        return {prefix: obj} if prefix else {}
    for k, v in obj.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(flatten(v, key))
        elif isinstance(v, list):
            out[key] = json.dumps(v)  # preserve lists as JSON strings
        else:
            out[key] = v
    return out


def process_file(filepath: Path, ticker: str, date_str: str) -> list[dict]:
    """Read a single date file and return flattened records."""
    records = []
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                tweet = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"  WARN: {ticker}/{date_str} line {lineno}: {e}", file=sys.stderr)
                continue

            flat = flatten(tweet)
            flat["_ticker"] = ticker
            flat["_date"] = date_str
            records.append(flat)
    return records


def main(data_root: str, output_path: str):
    root = Path(data_root)
    if not root.is_dir():
        print(f"ERROR: {root} is not a directory", file=sys.stderr)
        sys.exit(1)

    tickers = sorted([d for d in root.iterdir() if d.is_dir()])
    total_tweets = 0
    total_errors = 0

    with open(output_path, "w", encoding="utf-8") as out:
        for ticker_dir in tickers:
            ticker = ticker_dir.name
            date_files = sorted([f for f in ticker_dir.iterdir() if f.is_file()])
            ticker_count = 0

            for date_file in date_files:
                date_str = date_file.name
                records = process_file(date_file, ticker, date_str)
                for rec in records:
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                ticker_count += len(records)

            total_tweets += ticker_count
            print(f"  {ticker}: {ticker_count:,} tweets across {len(date_files)} files")

    print(f"\nDone. {total_tweets:,} tweets written to {output_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <data_root> <output.jsonl>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])