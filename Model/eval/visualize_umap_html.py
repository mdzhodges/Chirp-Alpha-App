import os
import sys
import torch
import numpy as np
import pandas as pd
import polars as pl
from typing import Optional
import argparse
import umap
import plotly.express as px

# Add project root and parent directory to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

model_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if model_dir not in sys.path:
    sys.path.insert(0, model_dir)

from architecture.models.stock_nn import StockNetwork
from architecture.models.index_nn import IndexNetwork
from architecture.models.final_output import OutputNN

# Hardcoded Top 100 S&P 500 Tickers by approximate market cap
TOP_100_SP500 = [
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'META', 'GOOGL', 'GOOG', 'BRK.B', 'LLY', 'AVGO', 
    'JPM', 'TSLA', 'UNH', 'XOM', 'V', 'JNJ', 'MA', 'PG', 'HD', 'COST', 'MRK', 'ABBV', 
    'CVX', 'CRM', 'AMD', 'BAC', 'NFLX', 'PEP', 'LIN', 'KO', 'TMO', 'WMT', 'ADBE', 
    'MCD', 'DIS', 'ABT', 'CSCO', 'INTU', 'QCOM', 'WFC', 'AMAT', 'DHR', 'CAT', 'IBM', 
    'TXN', 'VZ', 'PM', 'COP', 'NOW', 'GE', 'UNP', 'PFE', 'ISRG', 'BA', 'HON', 'AMGN', 
    'SPGI', 'INTC', 'LRCX', 'RTX', 'LOW', 'SYK', 'GS', 'PGR', 'BLK', 'MDT', 'T', 'ELV', 
    'VRTX', 'TJX', 'C', 'UPS', 'BKNG', 'CB', 'REGN', 'ADI', 'MMC', 'MDLZ', 'BSX', 'BMY', 
    'CVS', 'CI', 'KLAC', 'PANW', 'FI', 'DE', 'LMT', 'SNPS', 'GILD', 'ADP', 'CSX', 'MU', 
    'CDNS', 'SHW', 'MO', 'CME', 'SO', 'ICE', 'TGT'
]

def load_model_and_metadata(weights_path, device):
    print(f"Loading weights from {weights_path}...")
    checkpoint = torch.load(weights_path, map_location=device, weights_only=False)
    
    scalers = checkpoint.get("scalers")
    feature_cols = checkpoint.get("feature_cols")
    pca_models = checkpoint.get("pca_models", {})
    
    stock_scaler = scalers["stock_scaler"]
    spy_scaler = scalers["spy_scaler"]
    stock_cols = list(feature_cols["stock"])
    spy_cols = list(feature_cols["spy"])
    pca_stock = pca_models.get("pca_stock")
    pca_spy = pca_models.get("pca_spy")

    stock_in_dim = checkpoint["stock_network"]["input_layer.0.weight"].shape[1]
    spy_in_dim = checkpoint["index_network"]["input_layer.0.weight"].shape[1]
    
    print(f"Inferred dimensions: Stock Input={stock_in_dim}, Index Input={spy_in_dim}")

    stock_net = StockNetwork(input_dim=stock_in_dim).to(device)
    index_net = IndexNetwork(input_dim=spy_in_dim).to(device)
    output_net = OutputNN(numeric_dim=48, text_dim=5).to(device)

    stock_net.load_state_dict(checkpoint["stock_network"], strict=False)
    index_net.load_state_dict(checkpoint["index_network"], strict=False)
    output_net.load_state_dict(checkpoint["output_network"], strict=False)

    stock_net.eval()
    index_net.eval()
    output_net.eval()

    return {
        "stock_net": stock_net,
        "index_net": index_net,
        "output_net": output_net,
        "stock_scaler": stock_scaler,
        "spy_scaler": spy_scaler,
        "stock_cols": stock_cols,
        "spy_cols": spy_cols,
        "pca_stock": pca_stock,
        "pca_spy": pca_spy
    }

def process_tensors(table, expected_cols, scaler, pca_model=None):
    df = pd.DataFrame(list(table))
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    df = df[numeric_cols].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    
    if expected_cols:
        df = df.reindex(columns=expected_cols, fill_value=0.0)
    
    scaled = scaler.transform(df.to_numpy())
    if pca_model is not None:
        scaled = pca_model.transform(scaled)
    return torch.tensor(scaled, dtype=torch.float32)

def extract_latents(data_path, model_meta, device, sample_size=5000):
    print(f"Loading data from {data_path}...")
    
    # Filter directly in Polars for speed, then convert to pandas
    filtered_df = (
        pl.scan_parquet(data_path)
        .filter(pl.col('ticker').is_in(TOP_100_SP500))
        .collect()
        .to_pandas()
    )
    
    actual_sample_size = min(sample_size, len(filtered_df))
    if actual_sample_size == 0:
        raise ValueError("No matching Top 100 tickers found in the dataset.")
        
    df = filtered_df.sample(actual_sample_size)
    
    stock_raw_dim = len(model_meta['stock_cols'])
    spy_raw_dim = len(model_meta['spy_cols'])
    
    stock_in_layer = next(model_meta['stock_net'].parameters()).shape[1]
    spy_in_layer = next(model_meta['index_net'].parameters()).shape[1]
    
    if stock_in_layer < stock_raw_dim and model_meta['pca_stock'] is None:
        print(f"\n[!] WARNING: Model expects {stock_in_layer} stock features but only {stock_raw_dim} columns provided, and NO PCA object found in checkpoint.")
        print("[!] This will cause a RuntimeError. Please ensure PCA was saved during training.\n")

    stock_tensor = process_tensors(df['stock'], model_meta['stock_cols'], model_meta['stock_scaler'], model_meta['pca_stock']).to(device)
    spy_tensor = process_tensors(df['spy'], model_meta['spy_cols'], model_meta['spy_scaler'], model_meta['pca_spy']).to(device)
    
    latents = []
    with torch.no_grad():
        s_feat = model_meta['stock_net'](stock_tensor)
        i_feat = model_meta['index_net'](spy_tensor)
        text_feat = model_meta['output_net'].no_tweet_embedding.unsqueeze(0).expand(s_feat.size(0), -1)
        combined = torch.cat((s_feat, i_feat, text_feat), dim=-1)
        latents.append(combined.cpu().numpy())
    
    return np.concatenate(latents, axis=0), df

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", type=str, required=True, help="Path to best_model_weights.pt")
    parser.add_argument("--data", type=str, default="data/data.parquet", help="Path to data.parquet")
    parser.add_argument("--samples", type=int, default=3000, help="Number of samples to visualize")
    parser.add_argument("--output", type=str, default="umap_3d_momentum.html", help="Output HTML filename")
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    
    model_meta = load_model_and_metadata(args.weights, device)
    latents, full_df = extract_latents(args.data, model_meta, device, sample_size=args.samples)
    
    print(f"Running 3D UMAP on {latents.shape} latent space...")
    # Increased n_neighbors for more global structure/clusters
    reducer = umap.UMAP(n_components=3, n_neighbors=3, min_dist=0.1, metric='manhattan')
    embedding = reducer.fit_transform(latents)
    
    plot_df = pd.DataFrame({
        "UMAP 1": embedding[:, 0],
        "UMAP 2": embedding[:, 1],
        "UMAP 3": embedding[:, 2],
        "Momentum": full_df["momentum"].values,
        "Ticker": full_df["ticker"].values,
        "Date": full_df["Date"].values,
    })
    
    plot_df["Direction"] = np.where(plot_df["Momentum"] > 0, "Positive", 
                                   np.where(plot_df["Momentum"] < 0, "Negative", "Neutral"))

    print("Generating interactive 3D plot...")
    fig = px.scatter_3d(
        plot_df, 
        x="UMAP 1", 
        y="UMAP 2", 
        z="UMAP 3",
        color="Direction",
        color_discrete_map={"Positive": "#00FF00", "Negative": "#FF0000", "Neutral": "#808080"},
        hover_data=["Ticker", "Date", "Momentum"],
        title=f"3D Interactive UMAP Projection of Latent Space (Sample: {len(full_df)})",
        template="plotly_dark"
    )
    
    fig.update_traces(marker=dict(size=3, opacity=0.8))
    fig.write_html(args.output)
    print(f"3D Interactive visualization saved to {args.output}")

if __name__ == "__main__":
    main()