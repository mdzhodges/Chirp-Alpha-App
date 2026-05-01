import os
import sys
import torch
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import polars as pl
from typing import Optional
import argparse
from tqdm import tqdm

# Add parent directory to path to allow importing 'architecture'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Attempt to import umap, providing instructions if missing
try:
    import umap
except ImportError:
    print("\n[!] 'umap-learn' not found. Please install it with: pip install umap-learn\n")
    sys.exit(1)

from architecture.models.stock_nn import StockNetwork
from architecture.models.index_nn import IndexNetwork
from architecture.models.final_output import OutputNN

def load_model_and_metadata(weights_path, device):
    print(f"Loading weights from {weights_path}...")
    checkpoint = torch.load(weights_path, map_location=device, weights_only=False)
    
    # Metadata
    scalers = checkpoint.get("scalers")
    feature_cols = checkpoint.get("feature_cols")
    pca_models = checkpoint.get("pca_models", {})
    target_stats = checkpoint.get("target_stats", {"mean": 0.0, "std": 1.0})
    
    stock_scaler = scalers["stock_scaler"]
    spy_scaler = scalers["spy_scaler"]
    stock_cols = list(feature_cols["stock"])
    spy_cols = list(feature_cols["spy"])
    pca_stock = pca_models.get("pca_stock")
    pca_spy = pca_models.get("pca_spy")

    # Dimensions
    stock_in_dim = pca_stock.n_components_ if pca_stock else len(stock_cols)
    spy_in_dim = pca_spy.n_components_ if pca_spy else len(spy_cols)

    # Models
    stock_net = StockNetwork(input_dim=stock_in_dim).to(device)
    index_net = IndexNetwork(input_dim=spy_in_dim).to(device)
    output_net = OutputNN(numeric_dim=48, text_dim=5).to(device)

    # Load states
    stock_net.load_state_dict(checkpoint["stock_network"])
    index_net.load_state_dict(checkpoint["index_network"])
    output_net.load_state_dict(checkpoint["output_network"])

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
        "pca_spy": pca_spy,
        "target_stats": target_stats
    }

def process_tensors(table, expected_cols, scaler, pca_model=None):
    df = pd.DataFrame(list(table))
    # Filter only numeric and reindex to match training
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    df = df[numeric_cols].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    df = df.reindex(columns=expected_cols, fill_value=0.0)
    
    scaled = scaler.transform(df.to_numpy())
    if pca_model is not None:
        scaled = pca_model.transform(scaled)
    return torch.tensor(scaled, dtype=torch.float32)

def extract_latents(data_path, model_meta, device, sample_size=5000):
    print(f"Loading data from {data_path}...")
    df = pl.read_parquet(data_path).tail(sample_size * 20).sample(sample_size).to_pandas()
    
    stock_tensor = process_tensors(df['stock'], model_meta['stock_cols'], model_meta['stock_scaler'], model_meta['pca_stock']).to(device)
    spy_tensor = process_tensors(df['spy'], model_meta['spy_cols'], model_meta['spy_scaler'], model_meta['pca_spy']).to(device)
    momentum = df['momentum'].values
    
    latents = []
    
    with torch.no_grad():
        # Get backbone features
        s_feat = model_meta['stock_net'](stock_tensor)
        i_feat = model_meta['index_net'](spy_tensor)
        
        # For text, we'll just use the no_tweet_embedding for simplicity in this visualization
        # as aligning the precomputed embeddings is slow for a quick script
        text_feat = model_meta['output_net'].no_tweet_embedding.unsqueeze(0).expand(s_feat.size(0), -1)
        
        # Concatenate into the latent space the OutputNN sees
        combined = torch.cat((s_feat, i_feat, text_feat), dim=-1)
        latents.append(combined.cpu().numpy())
    
    return np.concatenate(latents, axis=0), momentum

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", type=str, required=True, help="Path to best_model_weights.pt")
    parser.add_argument("--data", type=str, default="data/data.parquet", help="Path to data.parquet")
    parser.add_argument("--samples", type=int, default=5000, help="Number of samples to visualize")
    parser.add_argument("--output", type=str, default="umap_momentum.png", help="Output filename")
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    
    model_meta = load_model_and_metadata(args.weights, device)
    latents, momentum = extract_latents(args.data, model_meta, device, sample_size=args.samples)
    
    print(f"Running UMAP on {latents.shape} latent space...")
    reducer = umap.UMAP(n_neighbors=15, min_dist=0.1, metric='cosine', random_state=42)
    embedding = reducer.fit_transform(latents)
    
    # Create labels
    # Use a small threshold to separate positive, neutral-ish, and negative
    labels = np.where(momentum > 0.5, "Positive", np.where(momentum < -0.5, "Negative", "Neutral"))
    
    plt.figure(figsize=(12, 10))
    sns.scatterplot(
        x=embedding[:, 0], 
        y=embedding[:, 1], 
        hue=labels, 
        palette={"Positive": "green", "Negative": "red", "Neutral": "gray"},
        alpha=0.6,
        s=10
    )
    plt.title(f"UMAP Projection of Model Latent Space\nColored by Momentum (Sample Size: {args.samples})")
    plt.xlabel("UMAP 1")
    plt.ylabel("UMAP 2")
    plt.legend(title="Momentum Sign")
    
    plt.savefig(args.output, dpi=300)
    print(f"Visualization saved to {args.output}")

if __name__ == "__main__":
    main()
