from transformers import AutoTokenizer, AutoModel
import os
import torch.nn as nn

from transformers import logging as transformers_logging

transformers_logging.set_verbosity_error()


ENCODER_LR = float(os.environ.get("ENCODER_LR", 1e-5))

class Encoder(nn.Module):
    def __init__(self, model_name="StephanAkkerman/FinTwitBERT"):
        super().__init__()
        self.model = AutoModel.from_pretrained(model_name)
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.lr = ENCODER_LR

    def forward(self, text_list):
            device = next(self.model.parameters()).device
            inputs = self.tokenizer(
                text_list,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=128,
            ).to(device)
            outputs = self.model(**inputs)
            return outputs.last_hidden_state[:, 0, :]
