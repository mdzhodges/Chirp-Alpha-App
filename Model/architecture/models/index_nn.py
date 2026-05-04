
import torch.nn as nn
import os


INDEX_NN_LR = float(os.environ.get("INDEX_NN_LR", 1e-5))
INDEX_NN_DROP = float(os.environ.get("INDEX_NN_DROP", 0.05))


class IndexNetwork(nn.Module):
    def __init__(self, input_dim: int = 42, dropout: float = INDEX_NN_DROP):
        super(IndexNetwork, self).__init__()
        self.dropout = dropout
        
        self.input_layer = nn.Sequential(
            nn.Linear(input_dim, 64),
            nn.LayerNorm(64),
            nn.LeakyReLU(0.1)
        )
        
        # Residual Block
        self.res_block = nn.Sequential(
            nn.Linear(64, 64),
            nn.LayerNorm(64),
            nn.LeakyReLU(0.1),
            nn.Dropout(self.dropout),
            nn.Linear(64, 64),
            nn.LayerNorm(64)
        )
        
        self.output_layer = nn.Sequential(
            nn.LeakyReLU(0.1),
            nn.Linear(64, 16)
        )

    def forward(self, x):
        x = self.input_layer(x)
        x = x + self.res_block(x)
        return self.output_layer(x)
