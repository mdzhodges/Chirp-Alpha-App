import torch
import numpy as np
import pandas as pd
from sklearn.metrics import r2_score
import torch.nn.functional as F
from typing import Optional
from scipy.stats import spearmanr
from torch.utils.data import DataLoader, TensorDataset

def validate(
    val_data: pd.DataFrame,
    encoder,
    stock_network,
    index_network,
    output_network,
    stock_scaler,
    spy_scaler,
    expected_stock_cols,
    expected_spy_cols,
    val_tweet_embeddings: Optional[torch.Tensor] = None,
    val_tweet_counts: Optional[torch.Tensor] = None,
    batch_size: int = 4096,
    target_mean: float = 0.0,
    target_std: float = 1.0,
    pca_stock=None,
    pca_spy=None,
    label: str = "VAL",
):
    try:
        device = next(output_network.parameters()).device
    except StopIteration:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    prev_modes = {
        "encoder": encoder.training if encoder is not None else None,
        "stock_network": stock_network.training,
        "index_network": index_network.training,
        "output_network": output_network.training,
    }

    if encoder is not None:
        encoder.eval()
    stock_network.eval()
    index_network.eval()
    output_network.eval()
    
    # Vectorized data extraction
    def extract_features(data_list, expected_cols, scaler, pca_model=None, tickers=None):
        if not data_list:
            return torch.zeros((0, len(expected_cols)), device=device)
        df = pd.DataFrame(data_list)
        forbidden = ['momentum', 'raw_return', 'Date', 'ticker']
        df = df.drop(columns=[c for c in forbidden if c in df.columns], errors='ignore')
        
        # Numeric columns only
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        
        if tickers is not None:
            df["ticker"] = tickers
            df[numeric_cols] = df.groupby("ticker")[numeric_cols].ffill()
            df = df.drop(columns=["ticker"])
            
        df = df[numeric_cols].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        df = df.reindex(columns=expected_cols, fill_value=0.0)
        
        scaled = scaler.transform(df.to_numpy())
        if pca_model is not None:
            scaled = pca_model.transform(scaled)
            
        return torch.tensor(scaled, dtype=torch.float32)

    # Pre-process all validation data at once (Vectorized!)
    val_tickers = val_data['ticker'].values if 'ticker' in val_data.columns else None
    stock_tensor_all = extract_features(val_data['stock'].tolist(), expected_stock_cols, stock_scaler, pca_model=pca_stock, tickers=val_tickers)
    spy_tensor_all = extract_features(val_data['spy'].tolist(), expected_spy_cols, spy_scaler, pca_model=pca_spy)
    
    # Validation targets: Use RAW momentum for Absolute Signal Evaluation
    val_momentum_raw_abs = val_data['momentum'].values.copy() 
    val_momentum_raw = val_data['momentum'].values
    
    momentum_targets = torch.tensor(val_momentum_raw, dtype=torch.float32)
    
    # Prepare embeddings
    if val_tweet_embeddings is not None:
        # Keep embeddings on CPU for now, we'll move batches to GPU
        tweet_emb_all = val_tweet_embeddings.to(dtype=torch.float32)
        tweet_counts_all = val_tweet_counts if val_tweet_counts is not None else torch.ones(len(val_data))
    else:
        # If no precomputed embeddings, we might still need the encoder (though user said they are precomputed)
        # For simplicity and speed in the precomputed case:
        tweet_emb_all = None
        tweet_counts_all = None

    all_preds = []
    
    with torch.no_grad():
        num_samples = len(val_data)
        for i in range(0, num_samples, batch_size):
            batch_end = min(i + batch_size, num_samples)
            
            s_batch = stock_tensor_all[i:batch_end].to(device)
            i_batch = spy_tensor_all[i:batch_end].to(device)
            
            if tweet_emb_all is not None:
                t_batch = tweet_emb_all[i:batch_end].to(device)
                counts_batch = tweet_counts_all[i:batch_end].to(device)
                
                # Handle no-tweet case
                has_tweets = (counts_batch > 0).unsqueeze(1)
                no_tweet = output_network.no_tweet_embedding.unsqueeze(0).expand(t_batch.size(0), -1)
                text_feat = torch.where(has_tweets, t_batch, no_tweet)
            else:
                # Fallback to encoder or no-tweet embedding
                if encoder is not None:
                    # This part is still slow if used, but usually we have precomputed embs
                    batch_tweets = val_data.iloc[i:batch_end]['tweets'].tolist()
                    text_feats = []
                    for tweets in batch_tweets:
                        texts = [t['text'] for t in tweets if isinstance(t, dict) and t.get('text')]
                        if texts:
                            text_feats.append(encoder(texts).mean(dim=0))
                        else:
                            text_feats.append(output_network.no_tweet_embedding.clone())
                    text_feat = torch.stack(text_feats).to(device)
                else:
                    text_feat = output_network.no_tweet_embedding.unsqueeze(0).expand(batch_end - i, -1).to(device)

            s_feat = stock_network(s_batch)
            i_feat = index_network(i_batch)
            
            # Ensure text_feat matches numeric features rank
            if s_feat.dim() == 3 and text_feat.dim() == 2:
                text_feat = text_feat.unsqueeze(1).expand(-1, s_feat.size(1), -1)
                
            combined = torch.cat((s_feat, i_feat, text_feat), dim=-1)
            
            # Single-task regression output
            pred = output_network(combined).squeeze(-1)
            
            # If prediction is sequential [Batch, Seq], take the last step
            if pred.dim() == 2 and s_feat.dim() == 3:
                pred = pred[:, -1]
                
            all_preds.append(pred.cpu())

    preds_scaled = torch.cat(all_preds).numpy()
    
    # Unscale predictions back to the original momentum range
    preds = preds_scaled * target_std + target_mean
    
    targets_momentum = momentum_targets.numpy()
    
    # Calculate Hybrid Loss on scaled space for early stopping
    targets_scaled = (targets_momentum - target_mean) / (target_std + 1e-9)
    mse_val = np.mean((preds_scaled - targets_scaled)**2)
    
    # Sign Penalty calculation with Directional Parity (mirrors trainer.py)
    # Softened by removing the +1.0 constant for smoother zero-crossing
    sign_mismatch = (np.sign(preds_scaled) != np.sign(targets_scaled)).astype(float)
    sign_penalty_raw = sign_mismatch * np.abs(preds_scaled - targets_scaled)
    
    pos_mask_v = (targets_scaled > 0).astype(float)
    neg_mask_v = (targets_scaled < 0).astype(float)
    
    sign_penalty_pos = np.sum(sign_penalty_raw * pos_mask_v) / (np.sum(pos_mask_v) + 1e-6)
    sign_penalty_neg = np.sum(sign_penalty_raw * neg_mask_v) / (np.sum(neg_mask_v) + 1e-6)
    sign_penalty = (sign_penalty_pos + sign_penalty_neg) / 2
    
    # Mean Stability constraint
    mean_penalty = (np.mean(preds_scaled))**2
    
    hybrid_loss = mse_val + 0.5 * sign_penalty + 0.5 * mean_penalty
    
    mean_l1_val = np.mean(np.abs(preds - targets_momentum))
    r_squared = r2_score(targets_momentum, preds)
    
    huber_val = float(F.huber_loss(torch.from_numpy(preds), torch.from_numpy(targets_momentum)).item())

    directional_accuracy = np.mean(np.sign(preds) == np.sign(targets_momentum))
    
    # Directional Metrics (Recall & Precision)
    up_mask = targets_momentum > 0
    down_mask = targets_momentum < 0
    
    up_accuracy = np.mean(np.sign(preds[up_mask]) == np.sign(targets_momentum[up_mask])) if up_mask.any() else 0.0
    down_accuracy = np.mean(np.sign(preds[down_mask]) == np.sign(targets_momentum[down_mask])) if down_mask.any() else 0.0
    
    pred_up_mask = preds > 0
    pred_down_mask = preds < 0
    
    up_precision = np.mean(np.sign(preds[pred_up_mask]) == np.sign(targets_momentum[pred_up_mask])) if pred_up_mask.any() else 0.0
    down_precision = np.mean(np.sign(preds[pred_down_mask]) == np.sign(targets_momentum[pred_down_mask])) if pred_down_mask.any() else 0.0
    
    # Spearman rank correlation (IC)
    rank_corr, _ = spearmanr(preds, targets_momentum)
    if np.isnan(rank_corr):
        rank_corr = 0.0
        
    # Bulk R2 (R2 on scaled space for target absolute value < 10)
    bulk_mask = np.abs(targets_momentum) < 10
    if bulk_mask.any():
        r2_bulk = r2_score(targets_scaled[bulk_mask], preds_scaled[bulk_mask])
    else:
        r2_bulk = 0.0
    
    # Raw Metrics (Against non-shifted targets if any, otherwise same as above)
    raw_directional_acc = directional_accuracy
    abs_up_precision = up_precision
    abs_down_precision = down_precision

    # Consolidated Metrics Print
    print(f"\n--- [{label}] Results ---")
    print(f"Losses: Hybrid={hybrid_loss:.4f} | Huber={huber_val:.4f} | MSE={mse_val:.4f} | SignP={sign_penalty:.4f}")
    print(f"Corrs:  Spearman={rank_corr:.4f} | R²={r_squared:.4f} | R²_Bulk={r2_bulk:.4f}")
    print(f"Alpha:  Acc={directional_accuracy:.4f} | UpRec={up_accuracy:.4f} | DnRec={down_accuracy:.4f} | UpPre={up_precision:.4f} | DnPre={down_precision:.4f}")
    print(f"Raw:    Acc={raw_directional_acc:.4f} | UpPre={abs_up_precision:.4f} | DnPre={abs_down_precision:.4f}")
    
    unique_dates_val = val_data['Date'].unique()
    date_spearmans = []
    for d in unique_dates_val:
        mask = (val_data['Date'].values == d)
        if mask.sum() < 10:
            continue
        sp, _ = spearmanr(preds[mask], targets_momentum[mask])
        if not np.isnan(sp):
            date_spearmans.append(sp)
    
    if date_spearmans:
        print(f"Date-wise Spearman: Mean={np.mean(date_spearmans):.4f} | Median={np.median(date_spearmans):.4f}")

    # Restore modes
    if encoder is not None and prev_modes["encoder"] is not None:
        encoder.train(prev_modes["encoder"])
    stock_network.train(prev_modes["stock_network"])
    index_network.train(prev_modes["index_network"])
    output_network.train(prev_modes["output_network"])
    
    return huber_val, mean_l1_val, r_squared, directional_accuracy, up_accuracy, down_accuracy, rank_corr, hybrid_loss, r2_bulk
