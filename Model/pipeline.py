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
import boto3
from datetime import datetime
from sklearn.decomposition import PCA
import polars as pl



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

TWEET_EMBEDDINGS_PATH = os.getenv("TWEET_EMBEDDINGS_PATH", "data/sentiment_features.pt")
DATA_PATH = os.getenv("DATA_PATH", "/home/ubuntu/training/data")
DATA_FORMAT = os.getenv("DATA_FORMAT", "parquet")
EMBEDDINGS_FULL_PATH = (
    os.path.join(DATA_PATH, "sentiment_features.pt")
    if not os.path.isabs(TWEET_EMBEDDINGS_PATH)
    else TWEET_EMBEDDINGS_PATH
)

S3_BUCKET = os.getenv("S3_BUCKET", "")
S3_PREFIX = os.getenv("S3_PREFIX", "training-results")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

_TWEET_EMBED_CACHE = {}


def _parquet_columns_to_load(path: str) -> list[str]:
    pf = pq.ParquetFile(path)
    return [c for c in pf.schema_arrow.names if c != "tweets"]


def get_data_date_range():
    data = _get_data()
    dates = pd.to_datetime(data['Date'], errors='coerce').dropna()
    return str(dates.min().date()), str(dates.max().date())


def print_data_info():
    data = _get_data()
    first, last = get_data_date_range()
    tickers = data['ticker'].unique() if 'ticker' in data.columns else []

    num_tweets = 0
    parquet_path = f"{DATA_PATH}/data.parquet"
    if DATA_FORMAT == "parquet" and os.path.exists(parquet_path):
        try:
            pf = pq.ParquetFile(parquet_path)
            if "tweets" in pf.schema_arrow.names:
                for batch in pf.iter_batches(batch_size=50_000, columns=["tweets"]):
                    col = batch.column("tweets")
                    if hasattr(col, "combine_chunks"):
                        col = col.combine_chunks()
                    try:
                        num_tweets += len(col.values)
                    except AttributeError:
                        for row in col.to_pylist():
                            num_tweets += len(row) if row else 0
        except Exception as e:
            print(f"(skipping tweet count: {e})")

    print(f"=== Dataset Info ===")
    print(f"Date range: {first} to {last}")
    print(f"Total rows: {len(data):,}")
    print(f"Unique tickers: {len(tickers)}")
    print(f"Total tweets/articles: {num_tweets:,}")
    print(f"Data format: {DATA_FORMAT}")
    print(f"Data path: {DATA_PATH}")


def _load_tweet_embedding_index(path: str):
    if not path or not os.path.exists(path):
        return None
    cached = _TWEET_EMBED_CACHE.get(path)
    if cached is not None:
        return cached

    artifact = torch.load(path, map_location="cpu", weights_only=False)

    features = artifact.get("sentiment_features")
    if features is None:
        features = artifact.get("tweet_embedding")
    if not torch.is_tensor(features):
        raise ValueError(f"{path} is missing feature tensors.")

    counts = artifact.get("tweet_count")
    tickers = artifact.get("ticker")
    dates = artifact.get("Date")

    if counts is None or not torch.is_tensor(counts):
        counts = torch.zeros((features.shape[0],), dtype=torch.int64)
    
    mapping_df = pd.DataFrame({
        "ticker": pd.array([str(t) for t in tickers], dtype="string"),
        "Date": pd.array([str(d) for d in dates], dtype="string"),
        "embed_idx": np.arange(len(tickers), dtype=np.int64),
    })

    cached = (features, counts.to(dtype=torch.int64), mapping_df)
    _TWEET_EMBED_CACHE[path] = cached
    return cached

def _align_tweet_embeddings(df, embeddings, counts, mapping_df):
    df_keys = pd.DataFrame({
        "ticker": df["ticker"].astype("string"),
        "Date": pd.to_datetime(df["Date"]).astype("string"),
    })
    merged = df_keys.merge(mapping_df, on=["ticker", "Date"], how="left")
    idxs = merged["embed_idx"].to_numpy()

    n = len(df)
    feat_dim = int(embeddings.shape[1])
    aligned = torch.zeros((n, feat_dim), dtype=torch.float32)
    aligned_counts = torch.zeros((n,), dtype=torch.int64)

    valid_mask_np = ~pd.isna(idxs)
    if valid_mask_np.any():
        valid_idxs = torch.from_numpy(idxs[valid_mask_np].astype(np.int64))
        valid_mask_t = torch.from_numpy(valid_mask_np)
        aligned[valid_mask_t] = embeddings.index_select(0, valid_idxs).to(torch.float32)
        aligned_counts[valid_mask_t] = counts.index_select(0, valid_idxs)

    return aligned, aligned_counts


def _get_data():
    parquet_path = f"{DATA_PATH}/data.parquet"
    if not os.path.exists(parquet_path):
        raise FileNotFoundError(f"Parquet not found: {parquet_path}")

    cols = _parquet_columns_to_load(parquet_path)
    if FULL_DATA:
        data = pl.read_parquet(parquet_path, columns=cols).to_pandas()
    else:
        data = (
            pl.scan_parquet(parquet_path)
            .select(cols)
            .tail(SAMPLE_SIZE)
            .collect()
            .to_pandas()
        )
    return data.sort_values("Date").reset_index(drop=True)


def _process_tensors(table, original_df=None, scaler=None, pca_model=None):
    df = pd.DataFrame(list(table))
    drop_list = ['momentum', 'raw_return', 'Date', 'ticker', 'Adj close', 'Adj Close', 'adj close', 'Adj_Close', 'adj_close']
    df = df.drop(columns=[c for c in drop_list if c in df.columns], errors='ignore')
    numeric_cols = df.select_dtypes(include=[np.number]).columns

    if original_df is not None and "ticker" in original_df.columns:
        df["ticker"] = original_df["ticker"].values
        df[numeric_cols] = df.groupby("ticker")[numeric_cols].ffill()
        df = df.drop(columns=["ticker"])

    df = df[numeric_cols].replace([np.inf, -np.inf], np.nan).fillna(0)

    # Pre-initialize scaled to ensure it exists in all paths
    data_np = df.to_numpy()
    if scaler is None:
        scaler = StandardScaler()
        scaled = scaler.fit_transform(data_np)
    else:
        scaled = scaler.transform(data_np)

    scaled = np.nan_to_num(scaled, nan=0.0, posinf=0.0, neginf=0.0)

    if pca_model is not None:
        if hasattr(pca_model, "components_"):
            scaled = pca_model.transform(scaled)
        else:
            scaled = pca_model.fit_transform(scaled)
    
    return scaler, torch.tensor(scaled, dtype=torch.float32), numeric_cols.tolist()

def walkforward(lr: float, dropout: float, noise_std: float, con_lambda: float):
    data = _get_data()
    data['momentum'] = data['momentum'].clip(-30, 30)
    unique_dates = np.sort(data['Date'].unique())
    tscv = TimeSeriesSplit(n_splits=3)
    all_results = []
    tweet_index = _load_tweet_embedding_index(EMBEDDINGS_FULL_PATH)

    for fold, (train_date_idx, test_date_idx) in enumerate(tscv.split(unique_dates)):
        print(f"\nWALKFORWARD FOLD {fold+1} Run: LR={lr}, DR={dropout}, NS={noise_std}, CON={con_lambda}")
        train_dates = unique_dates[train_date_idx]
        test_dates = unique_dates[test_date_idx]

        train_df = data[data['Date'].isin(train_dates)].copy()
        test_df = data[data['Date'].isin(test_dates)].copy()

        pca_stock = PCA(n_components=0.95)
        pca_spy = PCA(n_components=0.95)

        stock_scaler, train_stock, stock_cols = _process_tensors(train_df["stock"], train_df, pca_model=pca_stock)
        spy_scaler, train_spy, spy_cols = _process_tensors(train_df["spy"], pca_model=pca_spy)

        train_tweet_emb = train_tweet_counts = None
        test_tweet_emb = test_tweet_counts = None
        if tweet_index is not None:
            embeddings, counts, mapping_df = tweet_index
            train_tweet_emb, train_tweet_counts = _align_tweet_embeddings(train_df, embeddings, counts, mapping_df)
            test_tweet_emb, test_tweet_counts = _align_tweet_embeddings(test_df, embeddings, counts, mapping_df)

        trainer = Trainer(
            train_stock=train_stock, train_spy=train_spy, train_data=train_df,
            num_epochs=NUM_EPOCHS, sample_size=SAMPLE_SIZE, learning_rate=lr,
            dropout=dropout, noise_std=noise_std, contrastive_lambda=con_lambda,
            train_tweet_embeddings=train_tweet_emb, train_tweet_counts=train_tweet_counts,
            pca_stock=pca_stock, pca_spy=pca_spy
        )

        trainer.train(test_df, stock_scaler, spy_scaler, stock_cols, spy_cols, 
                      val_tweet_embeddings=test_tweet_emb, val_tweet_counts=test_tweet_counts,
                      pca_stock=pca_stock, pca_spy=pca_spy, fold=fold + 1)

        results = validate(test_df, trainer.encoder, trainer.stock_network, trainer.index_network, 
                           trainer.output_network, stock_scaler, spy_scaler, stock_cols, spy_cols,
                           val_tweet_embeddings=test_tweet_emb, val_tweet_counts=test_tweet_counts,
                           target_mean=trainer.target_mean, target_std=trainer.target_std,
                           pca_stock=pca_stock, pca_spy=pca_spy)

        all_results.append(results)
        del trainer
        gc.collect()
        if torch.cuda.is_available(): torch.cuda.empty_cache()

    return all_results

def run_experiment(params):
    lr, dr, ns, con = params
    results = walkforward(lr=lr, dropout=dr, noise_std=ns, con_lambda=con)
    avg_results = np.mean(results, axis=0)
    
    run_name = f"LR_{lr}_DR_{dr}_NS_{ns}_CON_{con}"
    combo_dir = f"graphs/{run_name}"
    os.makedirs(combo_dir, exist_ok=True)
    pd.DataFrame(results).to_csv(f"{combo_dir}/fold_results.csv")

    return {
        "Hyperparameters": run_name,
        "Huber_Avg": avg_results[0],
        "Accuracy_Avg": avg_results[3],
        "Spearman_Avg": avg_results[6],
        "Hybrid_Loss_Avg": avg_results[7],
    }

def main():
    # Strategic 8-combo grid for Attention-Fusion + Contrastive + Gaussian
    combos = [
        (2e-5, 0.2, 0.01, 0.05),  # Baseline
        (2e-5, 0.2, 0.05, 0.05),  # High Noise
        (2e-5, 0.2, 0.01, 0.1),   # High Contrastive
        (5e-5, 0.2, 0.01, 0.05),  # Faster LR
        (2e-5, 0.1, 0.01, 0.05),  # Low Dropout
        (2e-5, 0.3, 0.05, 0.1),   # Heavy Regularization
        (1e-5, 0.2, 0.01, 0.05),  # Slow LR
        (5e-5, 0.3, 0.02, 0.05),  # Balanced
    ]

    results_list = [run_experiment(combo) for combo in combos]
    df = pd.DataFrame(results_list)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    df.to_csv(f"hyperparameter_results_{timestamp}.csv", index=False)
    print(f"Results saved to hyperparameter_results_{timestamp}.csv")

if __name__ == "__main__":
    main()
