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


dotenv.load_dotenv()

NUM_EPOCHS = int(os.getenv("NUM_EPOCHS", 5))
SAMPLE_SIZE = int(os.getenv("SAMPLE_SIZE", 1000))
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
TWEET_EMBEDDINGS_PATH = os.getenv("TWEET_EMBEDDINGS_PATH", "data/fintwitbert_tweet_embeddings.pt")

_TWEET_EMBED_CACHE = {}


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
    parquet_path = "data/data.parquet"
    jsonl_path = "data/data.jsonl"

    if os.path.exists(parquet_path):
        data = _read_parquet_tail(parquet_path, SAMPLE_SIZE)
    else:
        data = pd.read_json(jsonl_path, lines=True).tail(SAMPLE_SIZE).reset_index(drop=True)
    data = data.sort_values("Date").tail(SAMPLE_SIZE).reset_index(drop=True)
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

    tweet_index = _load_tweet_embedding_index(TWEET_EMBEDDINGS_PATH)

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

        huber_val, l1_error, r2_value, directional_accuracy = validate(
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
        
        results = huber_val, l1_error, r2_value, directional_accuracy
        
        print(f'For Combo: LR={lr}, DR={dropout}, L1={l1_lambda}: Final Test Huber: {huber_val} | L1 Error: {l1_error} | R^2: {r2_value} | Directional Accuracy: {directional_accuracy}')
        
        
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
    lr, dr, l1 = params
    results = walkforward(lr=lr, dropout=dr, l1_lambda=l1)
    
    avg_results = np.mean(results, axis=0)
    
    last_fold = results[-1]
        
    return {
        "Hyperparameters": f"LR:{lr}|DR:{dr}|L1:{l1}",
        "Huber_Avg": avg_results[0],
        "L1_Avg": avg_results[1],
        "R2_Avg": avg_results[2],
        "Accuracy_Avg": avg_results[3],
        "Last_Fold_Huber": last_fold[0],
        "Last_Fold_L1": last_fold[1],
        "Last_Fold_R2": last_fold[2],
        "Last_Fold_Accuracy": last_fold[3]
    }


def main():
    learning_rates = [1e-4, 5e-5, 2e-5]
    dropout_rates = [0.1, 0.2]
    l1_lambdas = [1e-3, 1e-4]
    
    combos = [(lr, dr, l1) for lr in learning_rates for dr in dropout_rates for l1 in l1_lambdas]
    
    summary_results = []
    

    max_workers = 12
    
    print(f"Parallelizing {len(combos)} experiments across {max_workers} workers...")
    
    results_list = list(map(run_experiment, combos))
    summary_results.extend(results_list)

    df = pd.DataFrame(summary_results)
    fig, axes = plt.subplots(4, 1, figsize=(40, 40)) 
    
    metrics = ['L1_Avg', 'Huber_Avg', 'R2_Avg', 'Accuracy_Avg']
    colors = ['skyblue', 'lightgreen', 'salmon', 'purple']
    
    for i, metric in enumerate(metrics):
        sns.barplot(data=df, x='Hyperparameters', y=metric, ax=axes[i], color=colors[i])
        axes[i].set_title(f'Average {metric}')
        axes[i].tick_params(axis='x', rotation=90)

    plt.tight_layout()
    plt.savefig("hyperparameter_analysis.png")
    plt.close(fig)
    
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
    plt.savefig("hyperparameter_last_fold_analysis.png")
    plt.close(fig_last)
    
if __name__ == "__main__":
    torch.multiprocessing.set_start_method('spawn', force=True)
    main()
