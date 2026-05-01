import torch
import torch.nn as nn

class OutputNN(nn.Module):
    """
    Advanced regression head for Time Series Foundation Models.
    Optimized for high-variance momentum targets (+/- 30).
    """

    def __init__(
        self,
        _legacy_input_dim: int = None, 
        hidden_dim: int = 64,
        dropout: float = 0.2,
        numeric_dim: int = 48,  
        text_dim: int = 5,
        latent_dim: int = 64,
    ):
        super().__init__()

        self.numeric_dim = numeric_dim
        self.text_dim = text_dim
        self.latent_dim = latent_dim

        # Learnable substitute for missing text data
        self.no_tweet_embedding = nn.Parameter(torch.zeros(self.text_dim))

        # Projections
        self.numeric_projection = nn.Sequential(
            nn.Linear(self.numeric_dim, self.latent_dim),
            nn.LayerNorm(self.latent_dim),
            nn.LeakyReLU(0.1), 
        )

        self.text_projection = nn.Sequential(
            nn.Linear(self.text_dim, self.latent_dim),
            nn.LayerNorm(self.latent_dim),
            nn.LeakyReLU(0.1),
        )

        # Gating replaced by Attention
        self.attention = nn.MultiheadAttention(
            embed_dim=self.latent_dim,
            num_heads=8,
            dropout=dropout,
            batch_first=True
        )

        # Regression Trunk
        self.trunk = nn.Sequential(
            nn.Linear(self.latent_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.LeakyReLU(0.1),
            nn.Dropout(dropout),
        )

        self.head = nn.Linear(hidden_dim, 1)
        self.shortcut = nn.Linear(self.latent_dim, 1)

    @staticmethod
    def init_weights(m):
        """Standardizes initialization for LeakyReLU architectures."""
        if isinstance(m, nn.Linear):
            # 'a=0.1' matches the LeakyReLU slope for optimal variance
            nn.init.kaiming_normal_(m.weight, a=0.1, nonlinearity='leaky_relu')
            if m.bias is not None:
                nn.init.constant_(m.bias, 0)
        elif isinstance(m, nn.Parameter) and m.size(0) == 5: # text_dim
            nn.init.normal_(m, std=0.01)

    def forward(self, x: torch.Tensor, return_latents: bool = False) -> torch.Tensor:
        if x.shape[-1] != self.numeric_dim + self.text_dim:
            raise ValueError(f"Dim mismatch: expected {self.numeric_dim + self.text_dim}, got {x.shape[-1]}")

        # Feature Splitting
        numeric = x[..., : self.numeric_dim]
        text = x[..., self.numeric_dim :]

        # Projections into common latent space
        numeric_lat = self.numeric_projection(numeric)
        text_lat = self.text_projection(text)

        # Create modality sequence: [Batch, 2, latent_dim]
        modality_seq = torch.stack([numeric_lat, text_lat], dim=1)

        # Self-Attention Fusion
        attn_output, _ = self.attention(modality_seq, modality_seq, modality_seq)

        # Pool/Aggregate
        fused = attn_output.mean(dim=1)

        # Trunk + Residual path
        feat = self.trunk(fused)

        # Final Regression
        raw_output = self.head(feat) + self.shortcut(fused)
        
        if return_latents:
            return raw_output, fused
        return raw_output