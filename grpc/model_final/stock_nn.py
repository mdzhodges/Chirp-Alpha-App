
import os

import torch.nn as nn

STOCK_NN_LR = float(os.environ.get("STOCK_NN_LR", 1e-5))
STOCK_NN_DROP = float(os.environ.get("STOCK_NN_DROP", 0.05)) # Lower dropout for stable representations


class StockNetwork(nn.Module):
    def __init__(self, input_dim: int = 37, dropout: float = STOCK_NN_DROP):
        super(StockNetwork, self).__init__()
        self.dropout = dropout

        self.input_layer = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.LayerNorm(128),
            nn.LeakyReLU(0.1)
        )

        # Residual Block
        self.res_block = nn.Sequential(
            nn.Linear(128, 128),
            nn.LayerNorm(128),
            nn.LeakyReLU(0.1),
            nn.Dropout(self.dropout),
            nn.Linear(128, 128),
            nn.LayerNorm(128)
        )

        self.output_layer = nn.Sequential(
            nn.LeakyReLU(0.1),
            nn.Linear(128, 32)
        )

    def forward(self, x):
        x = self.input_layer(x)
        x = x + self.res_block(x) # Residual connection
        return self.output_layer(x)