import pandas as pd
import numpy as np
import torch
from sklearn.preprocessing import StandardScaler
import joblib
import os
import sys

# Add Model directory to path to import components
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def _process_tensors(table, scaler=None):
    df = pd.DataFrame(list(table))
    drop_list = ['momentum', 'raw_return', 'Date', 'ticker']
    df = df.drop(columns=[c for c in drop_list if c in df.columns], errors='ignore')
    df = df.select_dtypes(include=[np.number])
    df = df.replace([np.inf, -np.inf], np.nan).ffill().fillna(0)
    
    if scaler is None:
        scaler = StandardScaler()
        scaler.fit(df.to_numpy())
    
    return scaler, df.columns.tolist()

def main():
    data_path = "Model/data/data.parquet"
    if not os.path.exists(data_path):
        print(f"Data not found at {data_path}")
        return

    print(f"Loading data from {data_path}...")
    data = pd.read_parquet(data_path)
    
    print("Fitting stock scaler...")
    stock_scaler, stock_cols = _process_tensors(data["stock"])
    
    print("Fitting spy scaler...")
    spy_scaler, spy_cols = _process_tensors(data["spy"])
    
    os.makedirs("Model/inference/assets", exist_ok=True)
    joblib.dump(stock_scaler, "Model/inference/assets/stock_scaler.pkl")
    joblib.dump(spy_scaler, "Model/inference/assets/spy_scaler.pkl")
    joblib.dump(stock_cols, "Model/inference/assets/stock_cols.pkl")
    joblib.dump(spy_cols, "Model/inference/assets/spy_cols.pkl")
    
    print("Scalers and column lists saved to Model/inference/assets/")

if __name__ == "__main__":
    main()
