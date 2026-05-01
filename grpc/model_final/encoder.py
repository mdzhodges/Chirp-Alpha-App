import os

import torch.nn as nn
from transformers import AutoModel, AutoTokenizer
from transformers import logging as transformers_logging

transformers_logging.set_verbosity_error()

ENCODER_LR = float(os.environ.get("ENCODER_LR", 1e-5))


class Encoder(nn.Module):
    def __init__(self, model_name="yiyanghkust/finbert-tone"):
        super().__init__()
        # finbert-tone needs the BertTokenizer/BertModel fallback path:
        # its tokenizer config trips the fast-tokenizer converter, and its
        # config.json lacks a model_type field for AutoModel to dispatch on.
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=False)
        except (ValueError, OSError):
            from transformers import BertTokenizer
            self.tokenizer = BertTokenizer.from_pretrained(model_name)

        try:
            self.model = AutoModel.from_pretrained(model_name)
        except (ValueError, OSError):
            from transformers import BertModel
            self.model = BertModel.from_pretrained(model_name)

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