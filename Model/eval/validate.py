import torch
import numpy as np
import pandas as pd
from sklearn.metrics import r2_score
import torch.nn.functional as F
from typing import Optional
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
    def extract_features(data_list, expected_cols, scaler):
        if not data_list:
            return torch.zeros((0, len(expected_cols)), device=device)
        df = pd.DataFrame(data_list)
        forbidden = ['momentum', 'raw_return', 'Date', 'ticker']
        df = df.drop(columns=[c for c in forbidden if c in df.columns], errors='ignore')
        df = df.select_dtypes(include=[np.number]).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        df = df.reindex(columns=expected_cols, fill_value=0.0)
        return torch.tensor(scaler.transform(df.to_numpy()), dtype=torch.float32)

    # Pre-process all validation data at once (Vectorized!)
    stock_tensor_all = extract_features(val_data['stock'].tolist(), expected_stock_cols, stock_scaler)
    spy_tensor_all = extract_features(val_data['spy'].tolist(), expected_spy_cols, spy_scaler)
    momentum_targets = torch.tensor(val_data['momentum'].values, dtype=torch.float32)
    
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
            combined = torch.cat((s_feat, i_feat, text_feat), dim=1)
            pred = output_network(combined).squeeze(-1)
            all_preds.append(pred.cpu())

    preds = torch.cat(all_preds).numpy()
    targets_momentum = momentum_targets.numpy()
    
    mean_l1_val = np.mean(np.abs(preds - targets_momentum))
    r_squared = r2_score(targets_momentum, preds)
    
    huber_val = float(F.huber_loss(torch.from_numpy(preds), torch.from_numpy(targets_momentum)).item())

    directional_accuracy = np.mean(np.sign(preds) == np.sign(targets_momentum))
    
    up_mask = targets_momentum >= 0
    down_mask = targets_momentum < 0
    
    up_accuracy = np.mean(np.sign(preds[up_mask]) == np.sign(targets_momentum[up_mask])) if up_mask.any() else 0.0
    down_accuracy = np.mean(np.sign(preds[down_mask]) == np.sign(targets_momentum[down_mask])) if down_mask.any() else 0.0

    # Restore modes
    if encoder is not None and prev_modes["encoder"] is not None:
        encoder.train(prev_modes["encoder"])
    stock_network.train(prev_modes["stock_network"])
    index_network.train(prev_modes["index_network"])
    output_network.train(prev_modes["output_network"])
    
    return huber_val, mean_l1_val, r_squared, directional_accuracy, up_accuracy, down_accuracy
