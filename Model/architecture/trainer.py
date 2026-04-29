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


class Trainer:
    def __init__(
            self,
            train_data: pd.DataFrame,
            num_epochs: int,
            sample_size: int,
            train_stock: torch.Tensor,
            train_spy: torch.Tensor,
            learning_rate: float = 1e-3,
            dropout: float = 0.1,
            l1_lambda: float = 1e-5,
            train_tweet_embeddings: Optional[torch.Tensor] = None,
            train_tweet_counts: Optional[torch.Tensor] = None,
            encoder: Optional[torch.nn.Module] = None,
    ):
        # Models
        if encoder is not None:
            self.encoder = encoder
        elif train_tweet_embeddings is not None:
            self.encoder = None
        else:
            self.encoder = Encoder()
        self.stock_network = StockNetwork(dropout=.1)
        self.index_network = IndexNetwork(dropout=.1)
        self.output_network = OutputNN(816, dropout=dropout)

        self.dropout = dropout
        self.l1_lambda = l1_lambda

        self.train_data = train_data
        self.num_epochs = num_epochs
        self.sample_size = sample_size
        self.train_stock = train_stock
        self.train_spy = train_spy
        self.learning_rate = learning_rate
        self.train_tweet_embeddings = train_tweet_embeddings
        self.train_tweet_counts = train_tweet_counts
        self._train_tweet_embeddings_device: Optional[torch.Tensor] = None
        self._train_tweet_counts_device: Optional[torch.Tensor] = None

        momentum_vals = train_data['stock'].apply(lambda x: x.get('momentum')).values

        total = len(self.train_data)
        num_up = len(np.where(momentum_vals >= 0)[0])
        num_down = total - num_up

        self.weight_up = total / (2 * num_up)
        self.weight_down = total / (2 * num_down)

        self.device = self._get_device()
        self.scaler = torch.amp.GradScaler(device="cuda", enabled=torch.cuda.is_available())

        self.best_model_state = None
        self.best_val_mean_squared_val = float('inf')
        self.best_l1 = float('inf')
        self.best_r2 = float('-inf')

        self.early_stopping_patience = 10
        self.early_stopping_counter = 0
        self.min_epoch_early = 20

        self.val_error = []
        self.train_error = []
        self.accuracy_val = []
        self.accuracy_train = []
        self.accuracy_up_val = []
        self.accuracy_down_val = []
        self.r2_val = []
        self.r2_train = []

        if self.encoder is not None:
            self.encoder.to(self.device)
        self.stock_network.to(self.device)
        self.index_network.to(self.device)
        self.output_network.to(self.device)

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
    ):
        val_mean_squared_val, val_l1, val_r2, val_directional_accuracy, val_up_acc, val_down_acc = validate(
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
        )
        train_mean_sqaure, train_l1, train_r2, train_directional_accuracy, train_up_acc, train_down_acc = validate(
            self.train_data,
            self.encoder,
            self.stock_network,
            self.index_network,
            self.output_network,
            stock_scaler,
            spy_scaler,
            expected_stock_cols,
            expected_spy_cols,
            val_tweet_embeddings=self._train_tweet_embeddings_device if self._train_tweet_embeddings_device is not None else self.train_tweet_embeddings,
            val_tweet_counts=self._train_tweet_counts_device if self._train_tweet_counts_device is not None else self.train_tweet_counts,
        )

        self.val_error.append(val_mean_squared_val)
        self.train_error.append(train_mean_sqaure)
        self.accuracy_val.append(val_directional_accuracy)
        self.accuracy_train.append(train_directional_accuracy)
        self.accuracy_up_val.append(val_up_acc)
        self.accuracy_down_val.append(val_down_acc)
        self.r2_val.append(val_r2)
        self.r2_train.append(train_r2)

        if epoch < self.min_epoch_early:
            return val_mean_squared_val, val_l1, val_r2, val_directional_accuracy, val_up_acc, val_down_acc

        if float(val_r2) > self.best_r2:
            self.best_val_mean_squared_val = val_mean_squared_val
            self.best_l1 = val_l1
            self.best_r2 = val_r2
            self.best_model_state = {
                'encoder': self.encoder.state_dict() if self.encoder is not None else None,
                'stock_network': self.stock_network.state_dict(),
                'index_network': self.index_network.state_dict(),
                'output_network': self.output_network.state_dict(),
            }
            
            # Save the best weights immediately
            model_dir = f'graphs/{self.learning_rate}_{self.dropout}_{self.l1_lambda}'
            os.makedirs(model_dir, exist_ok=True)
            model_path = f'{model_dir}/best_model_weights.pt'
            torch.save({
                'epoch': epoch,
                **self.best_model_state,
                'hyperparameters': {
                    'learning_rate': self.learning_rate,
                    'dropout': self.dropout,
                    'l1_lambda': self.l1_lambda,
                },
                'metrics': {
                    'best_val_huber': self.best_val_mean_squared_val,
                    'best_val_l1': self.best_l1,
                    'best_val_r2': self.best_r2,
                    'best_val_acc': val_directional_accuracy,
                    'best_val_up_acc': val_up_acc,
                    'best_val_down_acc': val_down_acc
                }
            }, model_path)
            print(f"New best model found at epoch {epoch} (R2: {val_r2:.4f}). Saved to {model_path}")
            
            self.early_stopping_counter = 0
        else:
            self.early_stopping_counter += 1

        return val_mean_squared_val, val_l1, val_r2, val_directional_accuracy, val_up_acc, val_down_acc

    def train(
            self,
            test_data: pd.DataFrame,
            stock_scaler,
            spy_scaler,
            stock_cols,
            spy_cols,
            val_tweet_embeddings: Optional[torch.Tensor] = None,
            val_tweet_counts: Optional[torch.Tensor] = None,
    ):
        batch_size = 1024

        if self.encoder is not None:
            self.encoder.eval()
        if self.train_tweet_embeddings is not None:
            self._train_tweet_embeddings_device = self.train_tweet_embeddings.to(self.device, dtype=torch.float32)
        if self.train_tweet_counts is not None:
            self._train_tweet_counts_device = self.train_tweet_counts.to(self.device)

        val_tweet_embeddings_device = None
        val_tweet_counts_device = None
        if val_tweet_embeddings is not None:
            val_tweet_embeddings_device = val_tweet_embeddings.to(self.device, dtype=torch.float32)
        if val_tweet_counts is not None:
            val_tweet_counts_device = val_tweet_counts.to(self.device)

        param_groups = [
            {
                'params': list(self.stock_network.parameters()) + list(self.index_network.parameters()),
                'lr': self.learning_rate,
                'weight_decay': 1e-4
            },
            {
                'params': self.output_network.parameters(),
                'lr': self.learning_rate * 10,
                'weight_decay': 1e-2
            }
        ]

        self.global_optimizer = torch.optim.AdamW(
            param_groups,
            eps=1e-5
        )

        loss_history = []
        loss_history_per_epoch = []

        for epoch in range(self.num_epochs):
            indices = torch.randperm(len(self.train_data))
            epoch_loss = 0.0

            for i in range(0, len(self.train_data), batch_size):
                batch_idx = indices[i: i + batch_size]
                batch = self.train_data.iloc[batch_idx.tolist()]
                self.stock_network.train()
                self.index_network.train()
                self.output_network.train()

                curr_size = len(batch)

                with torch.amp.autocast(self.device.type, enabled=torch.cuda.is_available()):

                    target = torch.tensor([row['momentum'] for row in batch['stock']],
                                          dtype=torch.float32, device=self.device).unsqueeze(1)

                    flat_texts = []
                    lengths = []

                    with torch.no_grad():
                        if self._train_tweet_embeddings_device is not None:
                            text_feat = self._train_tweet_embeddings_device[batch_idx]
                            if self._train_tweet_counts_device is not None:
                                has_tweets = (self._train_tweet_counts_device[batch_idx] > 0).unsqueeze(1)
                                no_tweet = self.output_network.no_tweet_embedding.unsqueeze(0).expand(curr_size, -1)
                                text_feat = torch.where(has_tweets, text_feat, no_tweet)
                        else:
                            for tl in batch['tweets']:
                                texts = [t['text'] for t in tl if isinstance(t, dict) and 'text' in t]
                                flat_texts.extend(texts)
                                lengths.append(len(texts))

                            text_feat = self.output_network.no_tweet_embedding.unsqueeze(0).repeat(curr_size, 1)

                            if flat_texts:
                                if self.encoder is None:
                                    raise RuntimeError(
                                        "Encoder is required when precomputed tweet embeddings are not provided.")
                                all_embs = self.encoder(flat_texts)
                                splits = torch.split(all_embs, lengths)
                                for idx, (split, length) in enumerate(zip(splits, lengths)):
                                    if length > 0:
                                        text_feat[idx] = split.mean(dim=0)

                    s_input = self.train_stock[batch_idx].to(self.device, non_blocking=torch.cuda.is_available())
                    s_feat = self.stock_network(s_input)

                    i_input = self.train_spy[batch_idx].to(self.device, non_blocking=torch.cuda.is_available())
                    i_feat = self.index_network(i_input)

                    combined = torch.cat((s_feat, i_feat, text_feat), dim=1)
                    prediction = self.output_network(combined)
                    weights = torch.where(target >= 0, self.weight_up, self.weight_down)

                    base_loss = F.huber_loss(prediction, target, reduction='mean', weight=weights)

                    l1_reg = sum(p.norm(1) for p in self.output_network.parameters())

                    total_loss = base_loss + self.l1_lambda * l1_reg
                    self.global_optimizer.zero_grad()
                    self.scaler.scale(total_loss).backward()
                    self.scaler.unscale_(self.global_optimizer)
                    self.scaler.step(self.global_optimizer)
                    self.scaler.update()
                    epoch_loss += total_loss.item()
                    loss_history.append(total_loss.item())

            num_batches = max(1, len(self.train_data) // batch_size)
            if len(self.train_data) % batch_size != 0 and len(self.train_data) > batch_size:
                num_batches += 1
            loss_history_per_epoch.append(epoch_loss / num_batches)

            self.early_stopping(
                test_data,
                stock_scaler,
                spy_scaler,
                stock_cols,
                spy_cols,
                epoch,
                val_tweet_embeddings=val_tweet_embeddings_device,
                val_tweet_counts=val_tweet_counts_device,
            )
            if self.early_stopping_counter >= self.early_stopping_patience:
                print(
                    f'Early stopping at epoch {epoch} LR={self.learning_rate}, DR={self.dropout}, L1={self.l1_lambda}')
                break

        if self.best_model_state is not None:
            print(
                f"Loading best weights with R2: {self.best_r2:.4f} | Huber Error: {self.best_val_mean_squared_val:.4f} | Combo: LR={self.learning_rate}, DR={self.dropout}, L1={self.l1_lambda}")
            if self.encoder is not None:
                self.encoder.load_state_dict(self.best_model_state['encoder'])
            self.stock_network.load_state_dict(self.best_model_state['stock_network'])
            self.index_network.load_state_dict(self.best_model_state['index_network'])
            self.output_network.load_state_dict(self.best_model_state['output_network'])

        os.makedirs(f'graphs/{self.learning_rate}_{self.dropout}_{self.l1_lambda}', exist_ok=True)

        plt.plot(self.val_error, label="Validation Huber Error")
        plt.plot(self.train_error, label="Training Huber Error")
        plt.xlabel('Epochs')
        plt.ylabel('Huber Error')
        plt.legend()
        plt.title('Val Error vs Train Error')
        plt.savefig(f'graphs/{self.learning_rate}_{self.dropout}_{self.l1_lambda}/training_vs_val_error.png')
        plt.close()

        plt.plot(loss_history_per_epoch)
        plt.xlabel('Epoch')
        plt.ylabel('Loss')
        plt.title('Training Loss per Epoch')
        plt.savefig(f'graphs/{self.learning_rate}_{self.dropout}_{self.l1_lambda}/training_loss_per_epoch.png')
        plt.close()

        plt.plot(self.r2_train, label="Training R2")
        plt.plot(self.r2_val, label="Validation R2")
        plt.xlabel('Epochs')
        plt.ylabel('R^2')
        plt.legend()
        plt.title('R^2 per Epoch')
        plt.savefig(f'graphs/{self.learning_rate}_{self.dropout}_{self.l1_lambda}/r^2_per_epoch.png')
        plt.close()

        data = {
            'epoch': list(range(len(self.train_error))),
            'train_huber_error': self.train_error,
            'val_huber_error': self.val_error,
            'avg_epoch_loss': loss_history_per_epoch,
            'accuracy_val': self.accuracy_val,
            'accuracy_train': self.accuracy_train,
            'accuracy_up_val': self.accuracy_up_val,
            'accuracy_down_val': self.accuracy_down_val,
            'r2_val': self.r2_val,
            'r2_train': self.r2_train,
        }

        df = pd.DataFrame(data)

        csv_path = f'graphs/{self.learning_rate}_{self.dropout}_{self.l1_lambda}/metrics_{self.learning_rate}_{self.dropout}_{self.l1_lambda}.csv'
        df.to_csv(csv_path, index=False)

        graph_dir = f'graphs/{self.learning_rate}_{self.dropout}_{self.l1_lambda}'
        for graph_file in ['training_vs_val_error.png', 'training_loss_per_epoch.png', 'r^2_per_epoch.png']:
            graph_path = f'{graph_dir}/{graph_file}'
            if os.path.exists(graph_path):
                self._upload_to_s3(graph_path)

        model_path = f'graphs/{self.learning_rate}_{self.dropout}_{self.l1_lambda}/best_model_weights.pt'
        if self.best_model_state is not None:
            torch.save({
                **self.best_model_state,
                'hyperparameters': {
                    'learning_rate': self.learning_rate,
                    'dropout': self.dropout,
                    'l1_lambda': self.l1_lambda,
                },
                'metrics': {
                    'best_val_huber': self.best_val_mean_squared_val,
                    'best_val_l1': self.best_l1,
                    'best_val_r2': self.best_r2,
                }
            }, model_path)

            self._upload_to_s3(model_path)
        self._upload_to_s3(csv_path)

    def _upload_to_s3(self, local_path: str):
        # S3 uploads disabled per user request
        return
        import dotenv
        dotenv.load_dotenv()
        s3_bucket = os.getenv("S3_BUCKET", "")
        if not s3_bucket:
            return
        s3_prefix = os.getenv("S3_PREFIX", "training-results")
        aws_region = os.getenv("AWS_REGION", "us-east-1")
        s3_key = f"{s3_prefix}/{datetime.now().strftime('%Y%m%d-%H%M%S')}/{local_path}"
        try:
            s3_client = boto3.client("s3", region_name=aws_region)
            s3_client.upload_file(local_path, s3_bucket, s3_key)
            print(f"Uploaded {local_path} to s3://{s3_bucket}/{s3_key}")
        except Exception as e:
            print(f"Failed to upload {local_path} to S3: {e}")

    def _get_device(self) -> torch.device:
        if os.getenv("FORCE_CPU", "false").lower() == "true":
            return torch.device("cpu")

        if torch.cuda.is_available():
            return torch.device("cuda")

        if torch.backends.mps.is_available():
            return torch.device("mps")

        return torch.device("cpu")
