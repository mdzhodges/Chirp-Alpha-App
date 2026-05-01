# Chirp Alpha

<p align="center">
  <img src="https://img.shields.io/badge/Stars-Private%20Repo-lightgrey?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Last%20Commit-Private%20Repo-lightgrey?style=for-the-badge" />
  <img src="https://img.shields.io/badge/License-Private%20Repo-lightgrey?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Python-3.12+-blue?style=for-the-badge&logo=python" />
  <img src="https://img.shields.io/badge/Poetry-Dependency%20Management-blueviolet?style=for-the-badge" />
</p>

---

## Table of Contents

- [Introduction](#introduction)
- [Sentiment Encoder Tower](#sentiment-encoder-tower)
- [Stock Neural Network Tower](#stock-neural-network-tower)
- [Market Index Neural Network Tower](#market-index-neural-network-tower)
- [Fusion & Output Layer](#fusion--output-layer)
- [Training Setup](#training-setup)
- [Equities To Follow](#equities-to-follow)
- [Algorithmic Trading Execution](#algorithmic-trading-execution)

---

## **Introduction**

This project created a multimodal machine learning architecture to predict momentum in financial markets. 
This was done by leveraging a pre-trained sentiment analysis encoder in FinTwit (financial X/Twitter) as well as a custom deep neural network architecture that ingested stock and index data aligned with the time frame of the tweets. 
Predicting momentum will allow retail traders to make more informed decisions before investing, as well as potentially forecasting the future trajectory of a stock.gi

---

### **Sentiment Encoder Tower**

The sentiment encoder tower used was the pretrained “FinTwitBERT” encoder from huggingface. 
This encoder has a 768 embedding dimension. 
For days with multiple tweets, the embeddings are mean pooled across the \[CLS\] vector in order to assure the 768 embedding dimension. 
This encoder was specifically trained on financial Twitter data, in which it aims to capture the unique dialect of Twitter and finance language.  
The reason this encoder was frozen during training was solely due to computational limitations.   

---

### **Stock Neural Network Tower**

The stock neural network tower consisted of a deep neural network architecture. 
This network took in the 37-dimensional input per stock. 
From there are 2 hidden layers, going from 128 to 64, finally outputting to a 32 output dimension. 
The activation function used after each hidden layer was a LeakyReLU function set to .01. Using the LeakyReLU setup prevented the issue of diminishing gradients in such a deep architecture. 
Finally, after the first activation function, a dropout layer was inserted, in order to help combat overfitting and/or escaping local minima during training. 

---

### **Market Index Neural Network Tower**

The market index neural network had a very similar architectural design to the stock neural network with different hidden dimensions as well as output dimension. 
This network took in the 42 input dimensions, passing through two hidden layers of 64 and 32 units respectively, before outputting a 16-dimensional embedding. 
Similar to the stock neural network, the activation function used was LeakyReLU with a value of .01 as well as a dropout layer after the first activation function. 

---

### **Fusion & Output Layer**

Due to the large embedding dimension of the encoder and the relatively small output dimension of the stock and market index networks, the encoder dimension is reduced through a learnable projection layer. 
This is done as if the encoder dimension was not reduced, the encoder dimension would dominate the fused representation, limiting the impact of the stock and market neural networks. 
This learnable projection layer projects the encoder output to a dimension of 32\. 
This allows the stock network to make up over 50% of the fused embedding. 
The completed fused embedding space was 80 (32 stock \+ 16 index \+ 32 projected encoder \= 80). 
The fusion was simply the concatenation of the three towers, allowing for all three embeddings to live in the same embedding space.

The three regression models used in this project (as per project specifications) were a linear model, a shallow neural network and the deep neural network. 
he linear network was extremely simple, taking the 80-dimensional input, and projecting it to 1 dimension, which represents the target momentum. 
The shallow neural network has only 1 hidden layer. 
This network also uses a LeakyReLU activation function (set to .01) with a drop out layer. 
The deep neural network utilizes two LeakyReLU activation functions (both set to .01) with two hidden layers and two dropout layers. 
The output dimension for all three networks is one, as there is only one prediction target (momentum). 
The hidden layer dimensions for the deep neural network are 64 and 32 respectively, while the hidden layer dimension for the shallow neural network is 64\. 

---

### **Training Setup**

For this project, the loss function used was a weighted huber loss with L1 regularization applied to the weights of the models. 
The weights for the huber loss were proportional to the number of “up days” and “down days” in the dataset. 
This helps with dealing with the natural imbalance in each fold of the dataset. 
The model was evaluated for at most 50 epochs, with the potential to stop early after 20 epochs with a patience of 10\. 
To determine if or when to stop early, the validation set was evaluated at the end of each epoch and the highest R2 value was saved and used on the test set.  
   
The learning rate for the stock and market neural networks were 2e-5 with a dropout of 0.2. 
The learning rate for the output regression head was 2e-4 with a dropout of also 0.2. 
The stock and market networks, along with the output regression head, utilized the AdamW optimizer with weight decays of 1e-4 and 1e-2, respectively. 
During backpropagation, the loss only traveled through the stock and market neural networks as well as the output head because the encoder was frozen.

---

### **Equities To Follow**

In this project, we will be trading a selected group of equities and ETFs, including major technology companies, financial institutions, consumer staples, and broad market funds. 
These assets were chosen to provide exposure across different sectors of the market, allowing us to analyze price movements, compare performance, and evaluate trading strategies under varying market conditions.

![BLK](https://img.shields.io/badge/BLK-BlackRock-black?logo=blackrock&logoColor=white)

![AAPL](https://img.shields.io/badge/AAPL-Apple-black?logo=apple)

![WMT](https://img.shields.io/badge/WMT-Walmart-0071CE?logo=walmart&logoColor=white)

![NVDA](https://img.shields.io/badge/NVDA-NVIDIA-76B900?logo=nvidia&logoColor=white)

![KO](https://img.shields.io/badge/KO-Coca--Cola-D71920?logo=cocacola&logoColor=white)

![CRWV](https://img.shields.io/badge/CRWV-CoreWeave-00A67E?logoColor=white)

![QQQ](https://img.shields.io/badge/QQQ-Invesco%20QQQ-1F5AA6?logo=invesco&logoColor=white)

![SPY](https://img.shields.io/badge/SPY-SPDR%20S%26P%20500-E41E26?logoColor=white)

![JPM](https://img.shields.io/badge/JPM-JPMorgan%20Chase-0C2340?logo=jpmorganchase&logoColor=white)

![GS](https://img.shields.io/badge/GS-Goldman%20Sachs-7399C6?logo=goldmansachs&logoColor=white)

---

### **Algorithmic Trading Execution**

(1) Prior to the start of each trading session (9:30 AM EST) the model will be run for each equity in the [Equities To Follow](#algorithmic-trading-execution) section.

(2) The model will output the following metrics for each equity:

    (1) The magnitude of growth / shrinkage for a given equity for the next 5 trading days
    (2) Accuracy percentage for the growth / shrinkage of a given equity for the following 5 trading days

(3) The trades will be executed via the Alpaca Markets paper trading API.

(4) This process will be repeated prior to the start of each trading session.

---
