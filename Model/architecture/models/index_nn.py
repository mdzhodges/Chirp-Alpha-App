
import torch.nn as nn
import os


INDEX_NN_LR = float(os.environ.get("INDEX_NN_LR", 1e-5))
INDEX_NN_DROP = float(os.environ.get("INDEX_NN_DROP", 0.1))


class IndexNetwork(nn.Module):
    def __init__(self, input_dim: int = 42, dropout: float = INDEX_NN_DROP):
        super(IndexNetwork, self).__init__()
        self.dropout = dropout
        self.model = nn.Sequential(
            nn.Linear(input_dim, 64),
            nn.LeakyReLU(.01),
            nn.Dropout(self.dropout),
            nn.Linear(64, 32),
            nn.LeakyReLU(.01),
            nn.Linear(32, 16)
        )


    def forward(self, x):
        return self.model(x)
