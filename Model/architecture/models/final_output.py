import torch
import torch.nn as nn


class OutputNN(nn.Module):
    def __init__(self, input_dim=816, hidden_dim=64, dropout=0.1):
        super(OutputNN, self).__init__()
        
        self.numeric_dim = 48 
        self.text_dim = 768
        self.latent_dim = 32 
        self.no_tweet_embedding = nn.Parameter(torch.zeros(self.text_dim))
        
        self.text_projection = nn.Sequential(
            nn.Linear(self.text_dim, self.latent_dim),
            nn.LayerNorm(self.latent_dim),
            nn.LeakyReLU(0.1)
        )
        
        ## linear Model
        self.model = nn.Sequential(
             nn.Linear(self.numeric_dim + self.latent_dim, 1)
        )
         
        # # Shallow NN
        # self.model = nn.Sequential(
        #      nn.Linear(self.numeric_dim + self.latent_dim, hidden_dim),
        #      nn.LeakyReLU(0.01),
        #      nn.Linear(hidden_dim, 1),
        # )
        
            
        
        # # Deep NN
        # self.model = nn.Sequential(
        #      nn.Linear(self.numeric_dim + self.latent_dim, hidden_dim),
        #      nn.LeakyReLU(0.01),
        #      nn.Dropout(dropout),
        #      nn.Linear(hidden_dim, hidden_dim//2),
        #      nn.LeakyReLU(0.01),
        #      nn.Dropout(dropout),
        #      nn.Linear(hidden_dim // 2, 1),
        #  )
        

    def forward(self, x):
        numeric = x[:, :self.numeric_dim]
        text = x[:, self.numeric_dim:]
        
        text_squished = self.text_projection(text)
        combined = torch.cat([numeric, text_squished], dim=1)
        
        return self.model(combined)
