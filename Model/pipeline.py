import matplotlib
matplotlib.use('Agg')
import os
import torch
import dotenv
import pandas as pd
import numpy as np
import pyarrow.parquet as pq
from architecture.trainer import Trainer
from eval.validate import validate
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit
import matplotlib.pyplot as plt
import seaborn as sns
import gc
from concurrent.futures import ProcessPoolExecutor
import boto3
from datetime import datetime
import json


dotenv.load_dotenv()

NUM_EPOCHS = int(os.getenv("NUM_EPOCHS", 5))
SAMPLE_SIZE = int(os.getenv("SAMPLE_SIZE", 1000))
FORCE_CPU = os.getenv("FORCE_CPU", "false").lower() == "true"
FULL_DATA = os.getenv("FULL_DATA", "false").lower() == "true"

if FORCE_CPU:
    DEVICE = torch.device("cpu")
    torch.set_num_threads(int(os.getenv("NUM_THREADS", os.cpu_count() or 1)))
else:
    DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

TWEET_EMBEDDINGS_PATH = os.getenv("TWEET_EMBEDDINGS_PATH", "data/fintwitbert_tweet_embeddings.pt")
DATA_PATH = os.getenv("DATA_PATH", "/home/ubuntu/training/data")
DATA_FORMAT = os.getenv("DATA_FORMAT", "parquet")  # "parquet" or "jsonl"
EMBEDDINGS_FULL_PATH = os.path.join(DATA_PATH, "fintwitbert_tweet_embeddings.pt") if not os.path.isabs(TWEET_EMBEDDINGS_PATH) else TWEET_EMBEDDINGS_PATH

S3_BUCKET = os.getenv("S3_BUCKET", "")
S3_PREFIX = os.getenv("S3_PREFIX", "training-results")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

_TWEET_EMBED_CACHE = {}


def get_data_date_range():
    """Return (first_date, last_date) from the data - auto-discovers."""
    data = _get_data()
    dates = pd.to_datetime(data['Date'], errors='coerce').dropna()
    return str(dates.min().date()), str(dates.max().date())


def print_data_info():
    """Print info about the dataset: date range, num rows, tickers, etc."""
    data = _get_data()
    first, last = get_data_date_range()
    tickers = data['ticker'].unique() if 'ticker' in data.columns else []
    num_tweets = sum(len(row.get('tweets', [])) for _, row in data.iterrows())
    
    print(f"=== Dataset Info ===")
    print(f"Date range: {first} to {last}")
    print(f"Total rows: {len(data):,}")
    print(f"Unique tickers: {len(tickers)}")
    print(f"Total tweets/articles: {num_tweets:,}")
    print(f"Data format: {DATA_FORMAT}")
    print(f"Data path: {DATA_PATH}")


def get_index_data():
    """Extract market index data (SPY, QQQ, DIA, VIX) as separate dict keyed by date."""
    data = _get_data()
    result = {}
    for _, row in data.iterrows():
        spy_data = row.get('spy', {})
        if spy_data:
            result[row['Date']] = spy_data
    return result


def get_stock_date_range():
    """Infer min/max date from stock CSV files."""
    import glob
    stock_dir = f"{DATA_PATH}/stock_data"
    if not os.path.exists(stock_dir):
        return None, None
    
    files = glob.glob(f"{stock_dir}/*.csv")
    if not files:
        return None, None
    
    min_date, max_date = None, None
    for path in files:
        try:
            df = pd.read_csv(path, usecols=['date'])
            if df.empty:
                continue
            dt = pd.to_datetime(df.get('date', df.get('Date')), errors='coerce').dropna()
            if dt.empty:
                continue
            lo, hi = dt.min().date(), dt.max().date()
            min_date = lo if min_date is None else min(min_date, lo)
            max_date = hi if max_date is None else max(max_date, hi)
        except Exception:
            continue
    
    return str(min_date) if min_date else None, str(max_date) if max_date else None


def download_index_data():
    """Download SPY/QQQ/DIA/VIX market indices matching stock date range."""
    import yfinance as yf
    tickers = ['SPY', 'QQQ', 'DIA', '^VIX']
    start_date, end_date = get_stock_date_range()
    if not start_date or not end_date:
        print("No stock date range found - run stock_clean.py first")
        return
    
    output_path = f"{DATA_PATH}/market_indices.jsonl"
    end_exclusive = (pd.to_datetime(end_date) + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    
    print(f"Downloading {tickers} from {start_date} to {end_date}...")
    data = yf.download(tickers, start=start_date, end=end_exclusive, auto_adjust=False)
    data.columns = [f'{t}_{p}' for p, t in data.columns]
    df = data.reset_index()
    df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
    df.to_json(output_path, orient='records', lines=True)
    print(f"Market data saved to {output_path} ({len(df):,} rows)")


def run_preprocessing():
    """Run preprocessing to build `data.parquet`/`data.jsonl` under `DATA_PATH`."""
    import sys

    print("=== Running Preprocessing ===")

    # Check for required inputs
    news_csv = f"{DATA_PATH}/news_data.csv"
    if os.path.exists(news_csv):
        print("news_data.csv detected - combined_jsonl.py will handle it")
    else:
        print(f"No news CSV found at {news_csv}, skipping")

    stock_dir = f"{DATA_PATH}/stock_data"
    if os.path.exists(stock_dir):
        print("stock_data/ detected - combined_jsonl.py will handle it")
    else:
        print(f"No stock_data/ folder found at {stock_dir}, skipping")
    
    # Run combined_jsonl.py (writes to DATA_PATH)
    print("\n--- Running combined_jsonl.py ---")
    os.environ.setdefault("PREPROCESS_START_DATE", "2010-01-01")
    os.environ["DATA_PATH"] = DATA_PATH
    sys.path.insert(0, os.path.dirname(__file__) or ".")
    from preprocessing.combined_jsonl import main as _preprocess_main

    _preprocess_main()
    print("combined_jsonl.py done - data.parquet created")
    
    print("\n=== Preprocessing Complete ===")
    print_data_info()


def _upload_to_s3(local_path: str, s3_key: str = None):
    # S3 uploads disabled per user request
    return
    if not S3_BUCKET:
        return
    if s3_key is None:
        s3_key = local_path
    s3_key = f"{S3_PREFIX}/{datetime.now().strftime('%Y%m%d-%H%M%S')}/{s3_key}"
    try:
        s3_client = boto3.client("s3", region_name=AWS_REGION)
        s3_client.upload_file(local_path, S3_BUCKET, s3_key)
        print(f"Uploaded {local_path} to s3://{S3_BUCKET}/{s3_key}")
    except Exception as e:
        print(f"Failed to upload {local_path} to S3: {e}")


def _load_tweet_embedding_index(path: str):
    if not path or not os.path.exists(path):
        return None
    cached = _TWEET_EMBED_CACHE.get(path)
    if cached is not None:
        return cached

    artifact = torch.load(path, map_location="cpu")
    embeddings = artifact.get("tweet_embedding")
    counts = artifact.get("tweet_count")
    tickers = artifact.get("ticker")
    dates = artifact.get("Date")

    if not torch.is_tensor(embeddings):
        raise ValueError(f"{path} is missing a tensor `tweet_embedding`.")
    if counts is None or not torch.is_tensor(counts):
        counts = torch.zeros((embeddings.shape[0],), dtype=torch.int64)
    if tickers is None or dates is None:
        raise ValueError(f"{path} is missing `ticker`/`Date` arrays for alignment.")

    key_to_idx = {(str(t), str(d)): i for i, (t, d) in enumerate(zip(tickers, dates))}
    cached = (embeddings.to(dtype=torch.float32), counts.to(dtype=torch.int64), key_to_idx)
    _TWEET_EMBED_CACHE[path] = cached
    return cached


def _align_tweet_embeddings(df: pd.DataFrame, embeddings: torch.Tensor, counts: torch.Tensor, key_to_idx: dict):
    n = len(df)
    hidden = int(embeddings.shape[1])
    aligned = torch.zeros((n, hidden), dtype=torch.float32)
    aligned_counts = torch.zeros((n,), dtype=torch.int64)

    for i, (ticker, date) in enumerate(zip(df["ticker"].astype(str).tolist(), df["Date"].astype(str).tolist())):
        j = key_to_idx.get((ticker, date), -1)
        if j >= 0:
            aligned[i] = embeddings[j]
            aligned_counts[i] = counts[j]
    return aligned, aligned_counts


def _read_parquet_tail(path: str, sample_size: int) -> pd.DataFrame:
    if sample_size <= 0:
        raise ValueError("SAMPLE_SIZE must be greater than 0.")

    parquet_file = pq.ParquetFile(path)
    total_row_groups = parquet_file.num_row_groups
    if total_row_groups == 0:
        return pd.DataFrame()

    selected_groups = []
    rows_accumulated = 0

    for rg_idx in range(total_row_groups - 1, -1, -1):
        rg_rows = parquet_file.metadata.row_group(rg_idx).num_rows
        selected_groups.append(rg_idx)
        rows_accumulated += rg_rows
        if rows_accumulated >= sample_size:
            break

    selected_groups.sort()
    table = parquet_file.read_row_groups(selected_groups)
    data = table.to_pandas()
    return data.tail(sample_size).reset_index(drop=True)


def _get_data():
    if DATA_FORMAT == "parquet":
        parquet_path = f"{DATA_PATH}/data.parquet"
        if not os.path.exists(parquet_path):
             raise FileNotFoundError(f"Parquet not found: {parquet_path}")
        
        if FULL_DATA:
            data = pd.read_parquet(parquet_path)
        else:
            data = _read_parquet_tail(parquet_path, SAMPLE_SIZE)
    else:
        jsonl_path = f"{DATA_PATH}/data.jsonl"
        if FULL_DATA:
            data = pd.read_json(jsonl_path, lines=True)
        else:
            data = pd.read_json(jsonl_path, lines=True).tail(SAMPLE_SIZE).reset_index(drop=True)
    
    if not FULL_DATA:
        data = data.sort_values("Date").tail(SAMPLE_SIZE).reset_index(drop=True)
    else:
        data = data.sort_values("Date").reset_index(drop=True)
    return data


def _process_tensors(table, scaler=None):
    df = pd.DataFrame(list(table))

    drop_list = ['momentum', 'raw_return', 'Date', 'ticker']
    df = df.drop(columns=[c for c in drop_list if c in df.columns], errors='ignore')

    df = df.select_dtypes(include=[np.number])
    df = df.replace([np.inf, -np.inf], np.nan).ffill().fillna(0)

    cols = df.columns.tolist() 

    if scaler is None:
        scaler = StandardScaler()
        scaled = scaler.fit_transform(df.to_numpy())
    else:
        scaled = scaler.transform(df.to_numpy())

    scaled = np.nan_to_num(scaled, nan=0.0, posinf=0.0, neginf=0.0)

    return scaler, torch.tensor(scaled, dtype=torch.float32), cols


def walkforward(lr:float, dropout:float, l1_lambda:float):
    data = _get_data()

    unique_dates = np.sort(data['Date'].unique())
    tscv = TimeSeriesSplit(n_splits=3)

    all_results = []

    tweet_index = _load_tweet_embedding_index(EMBEDDINGS_FULL_PATH)

    for fold, (train_date_idx, test_date_idx) in enumerate(tscv.split(unique_dates)):
        print(f"\nWALKFORWARD FOLD {fold+1} Combo: LR={lr}, DR={dropout}, L1={l1_lambda}")
        

        full_train_dates = unique_dates[train_date_idx]
        test_dates = unique_dates[test_date_idx]

        split_index = int(len(full_train_dates) * 0.90) 
        
        train_dates = full_train_dates[:split_index]
        val_dates = full_train_dates[split_index:]

        train_df = data[data['Date'].isin(train_dates)].copy()
        val_df = data[data['Date'].isin(val_dates)].copy() 
        test_df = data[data['Date'].isin(test_dates)].copy()
        
        
        train_mom = train_df['stock'].apply(lambda x: x.get('momentum'))
        val_mom = val_df['stock'].apply(lambda x: x.get('momentum'))
        test_mom = test_df['stock'].apply(lambda x: x.get('momentum'))
                
        print(f"Train Pos %: {(train_mom > 0).mean():.2%} | Val Pos %: {(val_mom > 0).mean():.2%} | Test Pos %: {(test_mom > 0).mean():.2%}")
        
        stock_scaler, train_stock, stock_cols = _process_tensors(train_df["stock"])
        spy_scaler, train_spy, spy_cols = _process_tensors(train_df["spy"])

        train_tweet_emb = train_tweet_counts = None
        val_tweet_emb = val_tweet_counts = None
        test_tweet_emb = test_tweet_counts = None
        if tweet_index is not None:
            embeddings, counts, key_to_idx = tweet_index
            train_tweet_emb, train_tweet_counts = _align_tweet_embeddings(train_df, embeddings, counts, key_to_idx)
            val_tweet_emb, val_tweet_counts = _align_tweet_embeddings(val_df, embeddings, counts, key_to_idx)
            test_tweet_emb, test_tweet_counts = _align_tweet_embeddings(test_df, embeddings, counts, key_to_idx)

        trainer = Trainer(
            train_stock=train_stock,
            train_spy=train_spy,
            train_data=train_df,
            num_epochs=NUM_EPOCHS,
            sample_size=SAMPLE_SIZE,
            learning_rate=lr,
            dropout=dropout,
            l1_lambda=l1_lambda,
            train_tweet_embeddings=train_tweet_emb,
            train_tweet_counts=train_tweet_counts,
        )

        trainer.train(
            val_df,
            stock_scaler,
            spy_scaler,
            stock_cols,
            spy_cols,
            val_tweet_embeddings=val_tweet_emb,
            val_tweet_counts=val_tweet_counts,
        )

        huber_val, l1_error, r2_value, directional_accuracy, up_accuracy, down_accuracy = validate(
            val_data=test_df,
            stock_scaler=stock_scaler,
            spy_scaler=spy_scaler,
            encoder=trainer.encoder,
            stock_network=trainer.stock_network,
            index_network=trainer.index_network,
            output_network=trainer.output_network,
            expected_stock_cols=stock_cols,
            expected_spy_cols=spy_cols,
            val_tweet_embeddings=test_tweet_emb,
            val_tweet_counts=test_tweet_counts,
        )
        
        results = huber_val, l1_error, r2_value, directional_accuracy, up_accuracy, down_accuracy
        
        print(f'For Combo: LR={lr}, DR={dropout}, L1={l1_lambda}: Final Test Huber: {huber_val} | L1 Error: {l1_error} | R^2: {r2_value} | Directional Accuracy: {directional_accuracy} | Up Acc: {up_accuracy:.4f} | Down Acc: {down_accuracy:.4f}')
        
        
        all_results.append(results)
        del trainer
        del train_stock
        del train_spy
        del train_df
        del val_df
        del test_df
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
        
    return all_results


def run_experiment(params):
    if FORCE_CPU:
        torch.set_num_threads(int(os.getenv("NUM_THREADS", os.cpu_count() or 1)))
    lr, dr, l1 = params
    results = walkforward(lr=lr, dropout=dr, l1_lambda=l1)
    
    avg_results = np.mean(results, axis=0)
    
    last_fold = results[-1]

    # Save per-fold results for this combo
    combo_dir = f"graphs/{lr}_{dr}_{l1}"
    os.makedirs(combo_dir, exist_ok=True)
    folds_df = pd.DataFrame(results, columns=['Huber', 'L1', 'R2', 'Accuracy', 'Up_Accuracy', 'Down_Accuracy'])
    folds_df.index.name = 'Fold'
    folds_df.to_csv(f"{combo_dir}/fold_results.csv")
        
    return {
        "Hyperparameters": f"LR:{lr}|DR:{dr}|L1:{l1}",
        "Huber_Avg": avg_results[0],
        "L1_Avg": avg_results[1],
        "R2_Avg": avg_results[2],
        "Accuracy_Avg": avg_results[3],
        "Up_Accuracy_Avg": avg_results[4],
        "Down_Accuracy_Avg": avg_results[5],
        "Last_Fold_Huber": last_fold[0],
        "Last_Fold_L1": last_fold[1],
        "Last_Fold_R2": last_fold[2],
        "Last_Fold_Accuracy": last_fold[3],
        "Last_Fold_Up_Accuracy": last_fold[4],
        "Last_Fold_Down_Accuracy": last_fold[5]
    }


def main():
    learning_rates = [1e-5, 5e-6, 1e-6]
    dropout_rates = [0.1, 0.2]
    l1_lambdas = [1e-3, 5e-3]
    
    combos = [(lr, dr, l1) for lr in learning_rates for dr in dropout_rates for l1 in l1_lambdas]
    
    summary_results = []
    

    max_workers = 12
    
    print(f"Parallelizing {len(combos)} experiments across {max_workers} workers...")
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        results_list = list(executor.map(run_experiment, combos))
    summary_results.extend(results_list)

    df = pd.DataFrame(summary_results)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    results_csv = f"hyperparameter_results_{timestamp}.csv"
    df.to_csv(results_csv, index=False)
    _upload_to_s3(results_csv)
    
    fig, axes = plt.subplots(4, 1, figsize=(40, 40)) 
    
    metrics = ['L1_Avg', 'Huber_Avg', 'R2_Avg', 'Accuracy_Avg']
    colors = ['skyblue', 'lightgreen', 'salmon', 'purple']
    
    for i, metric in enumerate(metrics):
        sns.barplot(data=df, x='Hyperparameters', y=metric, ax=axes[i], color=colors[i])
        axes[i].set_title(f'Average {metric}')
        axes[i].tick_params(axis='x', rotation=90)

    plt.tight_layout()
    analysis_png = f"hyperparameter_analysis_{timestamp}.png"
    plt.savefig(analysis_png)
    plt.close(fig)
    _upload_to_s3(analysis_png)
    
    fig_last, axes_last = plt.subplots(4, 1, figsize=(40, 40))
    last_fold_metrics = [
            ('Last_Fold_L1', 'skyblue'),
            ('Last_Fold_Huber', 'lightgreen'),
            ('Last_Fold_R2', 'salmon'),
            ('Last_Fold_Accuracy', 'purple')
        ]
    
    for i, (metric_key, color) in enumerate(last_fold_metrics):
            sns.barplot(data=df, x='Hyperparameters', y=metric_key, ax=axes_last[i], color=color)
            axes_last[i].set_title(f'Final Fold {metric_key.replace("Last_Fold_", "")}')
            axes_last[i].tick_params(axis='x', rotation=90)
    
    plt.tight_layout()
    last_fold_png = f"hyperparameter_last_fold_analysis_{timestamp}.png"
    plt.savefig(last_fold_png)
    plt.close(fig_last)
    _upload_to_s3(last_fold_png)
    
    print(f"Results saved to {results_csv} and uploaded to S3 bucket: {S3_BUCKET}")
    
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--preprocess-only', action='store_true', help='Run preprocessing only')
    parser.add_argument('--train-only', action='store_true', help='Run training only')
    args = parser.parse_args()
    
    if args.preprocess_only:
        run_preprocessing()
    elif args.train_only:
        torch.multiprocessing.set_start_method('spawn', force=True)
        main()
    else:
        # Default: run preprocessing first, then training
        run_preprocessing()
        print("\n" + "="*50 + "\n")
        torch.multiprocessing.set_start_method('spawn', force=True)
        main()
