import os
from datetime import datetime
from typing import Optional

import boto3
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from architecture.models.encoder import Encoder
from architecture.models.final_output import OutputNN
from architecture.models.index_nn import IndexNetwork
from architecture.models.stock_nn import StockNetwork
from eval.validate import validate
from tqdm import tqdm
import torch.nn as nn


from architecture.data_utils import get_dataloader
from torch.optim.lr_scheduler import ReduceLROnPlateau


class Trainer:

    @staticmethod
    def init_weights(m):
        if isinstance(m, nn.Linear):
            nn.init.kaiming_normal_(m.weight, a=0.1, nonlinearity='leaky_relu')
            if m.bias is not None:
                nn.init.constant_(m.bias, 0)
    
    def __init__(
            self,
            train_data: pd.DataFrame,
            num_epochs: int,
            sample_size: int,
            train_stock: torch.Tensor,
            train_spy: torch.Tensor,
            learning_rate: float = 1e-3,
            dropout: float = 0.1,
            noise_std: float = 0.01,
            contrastive_lambda: float = 0.05,
            train_tweet_embeddings: Optional[torch.Tensor] = None,
            train_tweet_counts: Optional[torch.Tensor] = None,
            encoder: Optional[torch.nn.Module] = None,
            pca_stock=None,
            pca_spy=None,
    ):
        self.pca_stock = pca_stock
        self.pca_spy = pca_spy
        self.contrastive_lambda = contrastive_lambda
        self.noise_std = noise_std

        # Models
        if encoder is not None:
            self.encoder = encoder
        elif train_tweet_embeddings is not None:
            self.encoder = None
        else:
            self.encoder = Encoder()
        
        # Use dynamic input dimensions based on PCA-reduced training tensors
        self.stock_network = StockNetwork(input_dim=train_stock.shape[1], dropout=.05)
        self.index_network = IndexNetwork(input_dim=train_spy.shape[1], dropout=.05)
        self.output_network = OutputNN(dropout=dropout)

        self.stock_network.apply(self.init_weights)
        self.index_network.apply(self.init_weights)
        self.output_network.apply(self.init_weights)

        self.dropout = dropout

        self.train_data = train_data
        self.num_epochs = num_epochs
        self.sample_size = sample_size
        self.train_stock = train_stock
        self.train_spy = train_spy
        self.learning_rate = learning_rate
        self.train_tweet_embeddings = train_tweet_embeddings
        self.train_tweet_counts = train_tweet_counts

        momentum_values = pd.to_numeric(train_data['momentum'], errors='coerce').to_numpy()
        momentum_values = np.nan_to_num(momentum_values, nan=0.0, posinf=0.0, neginf=0.0)
        
        # We no longer de-mean by the median. 
        # The user wants Absolute Direction: Positive Pred = Green Stock, Negative = Red Stock.
        
        # FORCE zero-centered scaling to prevent bearish/bullish bias shift
        self.target_mean = 0.0
        self.target_std = momentum_values.std() + 1e-9
        
        self.train_momentum = torch.tensor(momentum_values, dtype=torch.float32).unsqueeze(1)

        total = len(self.train_data)
        
        abs_bins = [0, 1, 2, 5, 10, np.inf]
        bins = np.sort(np.concatenate([-np.array(abs_bins[1:][::-1]), abs_bins]))
        counts, _ = np.histogram(momentum_values, bins=bins)
        
        smooth_counts = counts + 0.01 * total 
        bin_weights_np = (total / len(counts)) / smooth_counts
        
        # We NO LONGER symmetrize weights.
        # This allows the rarer 'Down' moves to naturally have higher weight
        # than the more common 'Up' moves in a drift-positive market.
        
        neg_mask = bins[1:] <= 0
        pos_mask = bins[:-1] >= 0
        
        total_neg_weight = (counts[neg_mask] * bin_weights_np[neg_mask]).sum()
        total_pos_weight = (counts[pos_mask] * bin_weights_np[pos_mask]).sum()
        
        if total_neg_weight > 0 and total_pos_weight > 0:
            target_mass = (total_neg_weight + total_pos_weight) / 2
            bin_weights_np[neg_mask] *= (target_mass / total_neg_weight)
            bin_weights_np[pos_mask] *= (target_mass / total_pos_weight)

        bin_weights_np = bin_weights_np / bin_weights_np.mean()
        
        self.bin_weights = torch.tensor(bin_weights_np, dtype=torch.float32)
        self.bin_edges = torch.tensor(bins[1:-1], dtype=torch.float32)

        self.device = self._get_device()
        self.bin_weights = self.bin_weights.to(self.device)
        self.bin_edges = self.bin_edges.to(self.device)

        self.scaler = torch.amp.GradScaler(device="cuda", enabled=torch.cuda.is_available())

        # Descriptive run name
        self.run_name = f"LR_{self.learning_rate}_DR_{self.dropout}_NS_{self.noise_std}_CON_{self.contrastive_lambda}"
        self.output_dir = f'graphs/{self.run_name}'
        os.makedirs(self.output_dir, exist_ok=True)

        self.best_model_state = None
        self.best_val_mean_squared_val = float('inf')
        self.best_directional_score = float('-inf')

        self.early_stopping_patience = 10
        self.early_stopping_counter = 0
        self.min_epoch_early = 5

        self.val_error = []
        self.train_error = []
        self.accuracy_val = []
        self.accuracy_train = []
        self.accuracy_up_val = []
        self.accuracy_down_val = []
        self.r2_val = []
        self.r2_train = []
        self.spearman_val = []
        self.spearman_train = []
        self.hybrid_loss_val = []
        self.hybrid_loss_train = []
        self.best_r2 = float('-inf')

        if self.encoder is not None:
            self.encoder.to(self.device)
        self.stock_network.to(self.device)
        self.index_network.to(self.device)
        self.output_network.to(self.device)

    def supervised_contrastive_loss(self, latents, targets, weights=None, temperature=0.1):
        """
        Pulls together samples with the same momentum sign, pushes apart different ones.
        """
        # Strictly binary discretization: 1 (Pos), -1 (Neg)
        labels = torch.where(targets > 0, torch.tensor(1.0).to(self.device), torch.tensor(-1.0).to(self.device))
        
        latents = F.normalize(latents, p=2, dim=1)
        logits = torch.matmul(latents, latents.T) / temperature
        
        labels = labels.view(-1, 1)
        mask = torch.eq(labels, labels.T).float()
        
        logits_mask = torch.scatter(
            torch.ones_like(mask),
            1,
            torch.arange(mask.shape[0]).view(-1, 1).to(self.device),
            0
        )
        mask = mask * logits_mask
        
        exp_logits = torch.exp(logits) * logits_mask
        log_prob = logits - torch.log(exp_logits.sum(1, keepdim=True) + 1e-9)
        
        mean_log_prob_pos = (mask * log_prob).sum(1) / (mask.sum(1) + 1e-9)
        
        if weights is not None:
            # Weighted average loss across the batch
            loss = -(mean_log_prob_pos * weights.squeeze()).sum() / (weights.sum() + 1e-9)
        else:
            loss = -mean_log_prob_pos.mean()
        return loss

    def early_stopping(
            self,
            val_data: pd.DataFrame,
            stock_scaler,
            spy_scaler,
            expected_stock_cols,
            expected_spy_cols,
            epoch,
            val_tweet_embeddings: Optional[torch.Tensor] = None,
            val_tweet_counts: Optional[torch.Tensor] = None,
            pca_stock=None,
            pca_spy=None,
    ):
        val_mean_squared_val, val_l1, val_r2, val_directional_accuracy, val_up_acc, val_down_acc, val_spearman, val_hybrid_loss, val_r2_bulk = validate(
            val_data,
            self.encoder,
            self.stock_network,
            self.index_network,
            self.output_network,
            stock_scaler,
            spy_scaler,
            expected_stock_cols,
            expected_spy_cols,
            val_tweet_embeddings=val_tweet_embeddings,
            val_tweet_counts=val_tweet_counts,
            target_mean=self.target_mean,
            target_std=self.target_std,
            pca_stock=pca_stock,
            pca_spy=pca_spy,
            label="VAL",
        )
        train_results = validate(
            self.train_data,
            self.encoder,
            self.stock_network,
            self.index_network,
            self.output_network,
            stock_scaler,
            spy_scaler,
            expected_stock_cols,
            expected_spy_cols,
            val_tweet_embeddings=self.train_tweet_embeddings,
            val_tweet_counts=self.train_tweet_counts,
            target_mean=self.target_mean,
            target_std=self.target_std,
            pca_stock=pca_stock,
            pca_spy=pca_spy,
            label="TRAIN",
        )
        # Unpack train results
        train_mean_sqaure, train_l1, train_r2, train_directional_accuracy, train_up_acc, train_down_acc, train_spearman, train_hybrid_loss, train_r2_bulk = train_results

        self.val_error.append(val_mean_squared_val)
        self.train_error.append(train_mean_sqaure)
        self.accuracy_val.append(val_directional_accuracy)
        self.accuracy_train.append(train_directional_accuracy)
        self.accuracy_up_val.append(val_up_acc)
        self.accuracy_down_val.append(val_down_acc)
        self.r2_val.append(val_r2)
        self.r2_train.append(train_r2)
        self.spearman_val.append(val_spearman)
        self.spearman_train.append(train_spearman)
        self.hybrid_loss_val.append(val_hybrid_loss)
        self.hybrid_loss_train.append(train_hybrid_loss)

        if epoch < self.min_epoch_early:
            return val_mean_squared_val, val_l1, val_r2, val_directional_accuracy, val_up_acc, val_down_acc, val_spearman, val_hybrid_loss, val_r2_bulk

        current_directional_score = min(val_up_acc, val_down_acc) - (abs(val_up_acc - val_down_acc) * 0.5)

        # Use Bulk R2 (excluding extreme outliers) for deciding the "Best" model
        if val_r2_bulk > self.best_r2:
            self.best_r2 = val_r2_bulk
            self.best_directional_score = current_directional_score
            self.best_val_mean_squared_val = val_mean_squared_val
            self.best_model_state = {
                'encoder': self.encoder.state_dict() if self.encoder is not None else None,
                'stock_network': self.stock_network.state_dict(),
                'index_network': self.index_network.state_dict(),
                'output_network': self.output_network.state_dict(),
            }

            model_path = f'{self.output_dir}/best_model_weights_fold{self.fold}.pt'
            torch.save({
                'epoch': epoch,
                **self.best_model_state,
                'hyperparameters': {
                    'learning_rate': self.learning_rate,
                    'dropout': self.dropout,
                    'noise_std': self.noise_std,
                    'contrastive_lambda': self.contrastive_lambda,
                },
                'metrics': {
                    'best_val_directional_score': current_directional_score,
                    'best_val_up_acc': val_up_acc,
                    'best_val_down_acc': val_down_acc,
                    'best_val_r2_bulk': val_r2_bulk,
                },
                'target_stats': {'mean': self.target_mean, 'std': self.target_std},
                'scalers': {'stock_scaler': self.stock_scaler, 'spy_scaler': self.spy_scaler},
                'pca_models': {'pca_stock': self.pca_stock, 'pca_spy': self.pca_spy},
                'feature_cols': {'stock': self.stock_cols, 'spy': self.spy_cols},
            }, model_path)
            print(f"New best model found at epoch {epoch} (Score: {current_directional_score:.4f}). Best Bulk R2: {val_r2_bulk:.4f}")

            self.early_stopping_counter = 0
        else:
            self.early_stopping_counter += 1

        if val_up_acc > 0.52 and val_down_acc > 0.52 and abs(val_up_acc - val_down_acc) < 0.01:
            self.early_stopping_counter = self.early_stopping_patience

        return val_mean_squared_val, val_l1, val_r2, val_directional_accuracy, val_up_acc, val_down_acc, val_spearman, val_hybrid_loss, val_r2_bulk

    def train(
            self,
            test_data: pd.DataFrame,
            stock_scaler,
            spy_scaler,
            stock_cols,
            spy_cols,
            val_tweet_embeddings: Optional[torch.Tensor] = None,
            val_tweet_counts: Optional[torch.Tensor] = None,
            pca_stock=None,
            pca_spy=None,
            fold: int = 0,
    ):
        batch_size = 4096
        self.fold = fold
        self.stock_scaler = stock_scaler
        self.spy_scaler = spy_scaler
        self.stock_cols = stock_cols
        self.spy_cols = spy_cols

        if self.encoder is not None:
            self.encoder.eval()

        train_loader = get_dataloader(
            self.train_stock,
            self.train_spy,
            self.train_momentum,
            self.train_tweet_embeddings,
            self.train_tweet_counts,
            batch_size=batch_size,
            shuffle=True,
            num_workers=4
        )

        param_groups = [
            {'params': list(self.stock_network.parameters()) + list(self.index_network.parameters()), 'lr': self.learning_rate},
            {'params': self.output_network.parameters(), 'lr': self.learning_rate}
        ]

        self.global_optimizer = torch.optim.AdamW(param_groups, eps=1e-5, weight_decay=1e-4)
        self.scheduler = ReduceLROnPlateau(self.global_optimizer, mode='min', factor=0.5, patience=3)

        for epoch in tqdm(range(self.num_epochs)):
            epoch_loss = 0.0
            self.stock_network.train()
            self.index_network.train()
            self.output_network.train()

            for batch in train_loader:
                s_input = batch['stock'].to(self.device, non_blocking=True)
                i_input = batch['spy'].to(self.device, non_blocking=True)
                target = batch['momentum'].to(self.device, non_blocking=True)

                if self.stock_network.training and self.noise_std > 0:
                    s_input = s_input + torch.randn_like(s_input) * self.noise_std
                    i_input = i_input + torch.randn_like(i_input) * self.noise_std

                with torch.amp.autocast(self.device.type, enabled=torch.cuda.is_available()):
                    if 'tweet_embed' in batch:
                        text_feat = batch['tweet_embed'].to(self.device, non_blocking=True)
                        counts = batch['tweet_count'].to(self.device, non_blocking=True)
                        has_tweets = (counts > 0).unsqueeze(1)
                        no_tweet = self.output_network.no_tweet_embedding.unsqueeze(0).expand(text_feat.size(0), -1)
                        text_feat = torch.where(has_tweets, text_feat, no_tweet)
                    else:
                        text_feat = self.output_network.no_tweet_embedding.unsqueeze(0).expand(s_input.size(0), -1).to(self.device)

                    s_feat = self.stock_network(s_input)
                    i_feat = self.index_network(i_input)

                    if s_feat.dim() == 3 and text_feat.dim() == 2:
                        text_feat = text_feat.unsqueeze(1).expand(-1, s_feat.size(1), -1)

                    combined = torch.cat((s_feat, i_feat, text_feat), dim=-1)
                    prediction, fused_latent = self.output_network(combined, return_latents=True)
                    
                    if prediction.dim() == 3:
                        prediction = prediction[:, -1, :]

                    bin_indices = torch.bucketize(target, self.bin_edges)
                    weights = self.bin_weights[bin_indices].unsqueeze(1)
                    
                    scaled_target = (target - self.target_mean) / self.target_std
                    base_loss = F.huber_loss(prediction, scaled_target, reduction='none', delta=1.0)
                    
                    # Soft-Magnitude Sign Penalty: Care about direction, but give more weight to larger moves
                    # using log-scaling to prevent outliers from dominating.
                    sign_mismatch = (torch.sign(prediction) != torch.sign(scaled_target)).float()
                    soft_magnitude = torch.log1p(torch.abs(scaled_target))
                    
                    # Bearish Intensity: penalize False Positives slightly more to maintain balance
                    false_positive_mask = (torch.sign(prediction) > 0) & (torch.sign(scaled_target) <= 0)
                    directional_intensity = 1.0 + (false_positive_mask.float() * 0.25)
                    
                    # Combined Directional Loss
                    weighted_base = (base_loss * weights).mean()
                    weighted_sign = (sign_mismatch * soft_magnitude * weights * directional_intensity).mean()
                    
                    # Use RAW targets for sign labels in contrastive loss to avoid scaling bias
                    con_loss = self.supervised_contrastive_loss(fused_latent, target, weights=weights)
                    
                    # Bias Penalty: Force the model's average prediction to match ZERO (Perfect Neutrality)
                    # This prevents the model from drifting with the market's positive mean.
                    bias_penalty = F.mse_loss(prediction.mean(), torch.tensor(0.0).to(self.device))
                    
                    # We increase the weight of sign loss now that it's magnitude-invariant
                    total_loss = weighted_base + (2.0 * weighted_sign) + (self.contrastive_lambda * con_loss) + (0.5 * bias_penalty)

                self.global_optimizer.zero_grad()
                self.scaler.scale(total_loss).backward()
                self.scaler.unscale_(self.global_optimizer)
                torch.nn.utils.clip_grad_norm_(list(self.stock_network.parameters()) + list(self.index_network.parameters()) + list(self.output_network.parameters()), 1.0)
                self.scaler.step(self.global_optimizer)
                self.scaler.update()

                epoch_loss += total_loss.item()

            metrics = self.early_stopping(test_data, stock_scaler, spy_scaler, stock_cols, spy_cols, epoch, 
                                         val_tweet_embeddings=val_tweet_embeddings, val_tweet_counts=val_tweet_counts,
                                         pca_stock=pca_stock, pca_spy=pca_spy)
            self.scheduler.step(metrics[-2])

            if self.early_stopping_counter >= self.early_stopping_patience:
                print(f'Early stopping at epoch {epoch} run={self.run_name}')
                break

        if self.best_model_state is not None:
            self.stock_network.load_state_dict(self.best_model_state['stock_network'])
            self.index_network.load_state_dict(self.best_model_state['index_network'])
            self.output_network.load_state_dict(self.best_model_state['output_network'])

        # Final Plotting
        self._plot_metrics()
        
        pd.DataFrame({
            'epoch': list(range(len(self.train_error))), 
            'train_huber': self.train_error, 
            'val_huber': self.val_error,
            'train_acc': self.accuracy_train,
            'val_acc': self.accuracy_val,
            'val_up_acc': self.accuracy_up_val,
            'val_down_acc': self.accuracy_down_val,
            'train_r2': self.r2_train,
            'val_r2': self.r2_val,
            'train_spearman': self.spearman_train,
            'val_spearman': self.spearman_val,
            'train_hybrid_loss': self.hybrid_loss_train,
            'val_hybrid_loss': self.hybrid_loss_val
        }).to_csv(f'{self.output_dir}/epoch_metrics_fold{self.fold}.csv', index=False)

    def _plot_metrics(self):
        epochs = list(range(len(self.train_error)))
        
        # 1. Huber Loss
        plt.figure(figsize=(10, 6))
        plt.plot(epochs, self.val_error, label="Val Huber")
        plt.plot(epochs, self.train_error, label="Train Huber")
        plt.title(f"Huber Error Over Time (Fold {self.fold})\n{self.run_name}")
        plt.xlabel("Epoch")
        plt.ylabel("Loss")
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.savefig(f'{self.output_dir}/huber_error_fold{self.fold}.png')
        plt.close()

        # 2. Accuracy
        plt.figure(figsize=(10, 6))
        plt.plot(epochs, self.accuracy_val, label="Total Acc", linewidth=2)
        plt.plot(epochs, self.accuracy_up_val, label="Up Acc", linestyle='--')
        plt.plot(epochs, self.accuracy_down_val, label="Down Acc", linestyle='--')
        plt.axhline(y=0.5, color='r', linestyle=':', label="Random")
        plt.title(f"Directional Accuracy Over Time (Fold {self.fold})\n{self.run_name}")
        plt.xlabel("Epoch")
        plt.ylabel("Accuracy")
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.savefig(f'{self.output_dir}/accuracy_fold{self.fold}.png')
        plt.close()

        # 3. Hybrid Loss & Spearman
        fig, ax1 = plt.subplots(figsize=(10, 6))
        ax1.set_xlabel('Epoch')
        ax1.set_ylabel('Hybrid Loss', color='tab:blue')
        ax1.plot(epochs, self.hybrid_loss_val, color='tab:blue', label="Val Hybrid Loss")
        ax1.tick_params(axis='y', labelcolor='tab:blue')

        ax2 = ax1.twinx()
        ax2.set_ylabel('Spearman Corr', color='tab:green')
        ax2.plot(epochs, self.spearman_val, color='tab:green', label="Val Spearman")
        ax2.tick_params(axis='y', labelcolor='tab:green')

        plt.title(f"Hybrid Loss & Spearman Correlation (Fold {self.fold})\n{self.run_name}")
        fig.tight_layout()
        plt.savefig(f'{self.output_dir}/hybrid_spearman_fold{self.fold}.png')
        plt.close()

        # 4. R2
        plt.figure(figsize=(10, 6))
        plt.plot(epochs, self.r2_train, label="Train R2")
        plt.plot(epochs, self.r2_val, label="Val R2")
        plt.title(f"R^2 Score Over Time (Fold {self.fold})\n{self.run_name}")
        plt.xlabel("Epoch")
        plt.ylabel("R^2")
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.savefig(f'{self.output_dir}/r2_fold{self.fold}.png')
        plt.close()

    def _get_device(self) -> torch.device:
        if os.getenv("FORCE_CPU", "false").lower() == "true": return torch.device("cpu")
        if torch.cuda.is_available(): return torch.device("cuda")
        return torch.device("cpu")
