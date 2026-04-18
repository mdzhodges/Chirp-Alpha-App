
import os

import torch.nn as nn

STOCK_NN_LR = float(os.environ.get("STOCK_NN_LR", 1e-5))
STOCK_NN_DROP = float(os.environ.get("STOCK_NN_DROP", 0.1))


class StockNetwork(nn.Module):
    def __init__(self, input_dim: int = 37, dropout: float = STOCK_NN_DROP):
        super(StockNetwork, self).__init__()
        self.dropout = dropout
        self.model = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.LeakyReLU(.01),
            nn.Dropout(self.dropout),
            nn.Linear(128, 64),
            nn.LeakyReLU(.01),
            nn.Linear(64, 32),
        )
        
        
        
    def forward(self, x):
        return self.model(x)