import torch
from torch.utils.data import Dataset, DataLoader
import pandas as pd
import numpy as np

class ChirpDataset(Dataset):
    def __init__(self, stock_tensor, spy_tensor, momentum_tensor, tweet_embeddings=None, tweet_counts=None):
        self.stock_tensor = stock_tensor
        self.spy_tensor = spy_tensor
        self.momentum_tensor = momentum_tensor
        self.tweet_embeddings = tweet_embeddings
        self.tweet_counts = tweet_counts

    def __len__(self):
        return len(self.stock_tensor)

    def __getitem__(self, idx):
        sample = {
            'stock': self.stock_tensor[idx],
            'spy': self.spy_tensor[idx],
            'momentum': self.momentum_tensor[idx],
        }
        if self.tweet_embeddings is not None:
            sample['tweet_embed'] = self.tweet_embeddings[idx]
            sample['tweet_count'] = self.tweet_counts[idx] if self.tweet_counts is not None else torch.tensor(1)
        return sample

def get_dataloader(stock_tensor, spy_tensor, momentum_tensor, tweet_embeddings=None, tweet_counts=None, batch_size=1024, shuffle=True, num_workers=4):
    dataset = ChirpDataset(stock_tensor, spy_tensor, momentum_tensor, tweet_embeddings, tweet_counts)
    return DataLoader(
        dataset, 
        batch_size=batch_size, 
        shuffle=shuffle, 
        num_workers=num_workers,
        pin_memory=torch.cuda.is_available()
    )