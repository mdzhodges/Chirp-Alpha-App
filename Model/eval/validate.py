import torch
import numpy as np
import pandas as pd
from sklearn.metrics import r2_score
import torch.nn.functional as F
from typing import Optional

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
    
    preds, targets, returns, dates = [], [], [], []
    momentum_targets = []
    
    forbidden = ['momentum', 'raw_return', 'Date', 'ticker']
    
    

    tweet_embeddings_device: Optional[torch.Tensor]
    if val_tweet_embeddings is not None:
        tweet_embeddings_device = val_tweet_embeddings.to(device, dtype=torch.float32, non_blocking=torch.cuda.is_available())
    else:
        tweet_embeddings_device = None

    with torch.no_grad():
        for pos, (_, row) in enumerate(val_data.iterrows()):
            stock_dict = row['stock']
            true_return = float(row.get('raw_return', stock_dict.get('raw_return', 0.0)))
            true_momentum = float(row.get('momentum', stock_dict.get('momentum', 0.0)))

            s_df = pd.DataFrame([stock_dict])
            s_df = s_df.drop(columns=[c for c in forbidden if c in s_df.columns], errors='ignore')
            s_df = s_df.select_dtypes(include=[np.number]).replace([np.inf, -np.inf], np.nan).fillna(0.0)
            s_df = s_df.reindex(columns=expected_stock_cols, fill_value=0.0)

            stock_tensor = torch.tensor(stock_scaler.transform(s_df.to_numpy()), device=device, dtype=torch.float32)

            spy_dict = row['spy']
            i_df = pd.DataFrame([spy_dict])
            i_df = i_df.drop(columns=[c for c in forbidden if c in i_df.columns], errors='ignore')
            i_df = i_df.select_dtypes(include=[np.number]).replace([np.inf, -np.inf], np.nan).fillna(0.0)
            i_df = i_df.reindex(columns=expected_spy_cols, fill_value=0.0)

            spy_tensor = torch.tensor(spy_scaler.transform(i_df.to_numpy()), device=device, dtype=torch.float32)

            if tweet_embeddings_device is not None:
                if val_tweet_counts is not None and int(val_tweet_counts[pos]) <= 0:
                    text_feat = output_network.no_tweet_embedding.to(device).unsqueeze(0)
                else:
                    text_feat = tweet_embeddings_device[pos].unsqueeze(0)
            else:
                if encoder is None:
                    raise RuntimeError("Encoder is required when precomputed tweet embeddings are not provided.")
                tweets = row.get('tweets', [])
                texts = [t['text'] for t in tweets if isinstance(t, dict) and t.get('text')]
                if texts:
                    text_feat = encoder(texts).mean(dim=0, keepdim=True)
                else:
                    text_feat = output_network.no_tweet_embedding.to(device).unsqueeze(0)
            text_feat = text_feat.to(device)

            s_feat = stock_network(stock_tensor)
            i_feat = index_network(spy_tensor)
            combined = torch.cat((s_feat, i_feat, text_feat), dim=1)

            pred = float(output_network(combined).squeeze().item())

            preds.append(pred)
            targets.append(1 if true_return > 0 else -1)
            momentum_targets.append(true_momentum)
            returns.append(true_return)
            dates.append(row.get('Date'))

    df = pd.DataFrame({
        "pred": preds,
        "ret": returns,
        "target": targets,
        "momentum_target": momentum_targets,
        "Date": dates,
        "ticker": val_data["ticker"].values
    })


    mean_l1_val = np.mean(np.abs(df["pred"] - df["momentum_target"]))
    
    r_squared = r2_score(df['momentum_target'], df['pred'])
    
    pred_tensor = torch.tensor(df['pred'], dtype=torch.float32)
    momentum_tensor = torch.tensor(df['momentum_target'], dtype=torch.float32)
    
    huber_val = float(F.huber_loss(pred_tensor, momentum_tensor).item())

    directional_accuracy = np.mean(np.sign(df['pred']) == np.sign(df['momentum_target']))

    if encoder is not None and prev_modes["encoder"] is not None:
        encoder.train(prev_modes["encoder"])
    stock_network.train(prev_modes["stock_network"])
    index_network.train(prev_modes["index_network"])
    output_network.train(prev_modes["output_network"])
    
    return huber_val, mean_l1_val, r_squared, directional_accuracy
