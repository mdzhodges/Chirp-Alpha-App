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
- [Local Setup](#local-setup)
- [Sentiment Encoder Tower](#sentiment-encoder-tower)
- [Stock Neural Network Tower](#stock-neural-network-tower)
- [Market Index Neural Network Tower](#market-index-neural-network-tower)
- [Fusion & Output Layer](#fusion--output-layer)
- [Training Setup](#training-setup)
- [Equities To Follow](#equities-to-follow)
- [Algorithmic Trading Execution](#algorithmic-trading-execution)
- [Algorithmic Trading Approach](#algorithmic-trading-approach)

---

## **Introduction**

This project created a multimodal machine learning architecture to predict momentum in financial markets. 
This was done by leveraging a pre-trained sentiment analysis encoder in FinTwit (financial X/Twitter) as well as a custom deep neural network architecture that ingested stock and index data aligned with the time frame of the tweets. 
Predicting momentum will allow retail traders to make more informed decisions before investing, as well as potentially forecasting the future trajectory of a stock.gi

---

## **Local Setup**

The local startup script now launches a Redis container automatically when Docker is available.

- `./run_app.sh` starts Redis, the Python gRPC service, the Spring backend, and the frontend.
- Redis runs on `localhost:6379` by default.
- Set `START_REDIS=false` if you want to skip Redis startup.
- Set `REDIS_CONTAINER_NAME` or `REDIS_IMAGE` if you want to customize the container.

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

(3) The trades will be executed via the Alpaca Markets paper trading API.

(4) This process will be repeated prior to the start of each trading session.

---

### **Connecting gRPC to Trading Account**

To integrate the gRPC momentum prediction service with the trading logic in `Model/trading_account/alpaca_algo_trading_implementation.py`, follow these technical steps:

#### **1. Initialize the gRPC Client**
Setup a persistent channel and stub within the `AlpacaAlgoTradingImplementation` class:
```python
import grpc
import grpc.momentum_pb2
import grpc.momentum_pb2_grpc as momentum_pb2_grpc

class AlpacaAlgoTradingImplementation:
    def __init__(self, ...):
        # ... existing init ...
        self._channel = grpc.insecure_channel('localhost:50051')
        self._stub = momentum_pb2_grpc.MomentumServiceStub(self.channel)
```

#### **2. Implement Data Gathering for Inference**
The model requires 60 days of historical data for both the target ticker and market indices.
- **Market History**: Populate a dictionary with `OHLCVList` for `["SPY", "QQQ", "DIA", "^VIX"]`.
- **Sentiment**: Aggregate recent tweets/posts for the target ticker into a list of strings.

#### **3. Populate `_get_model_predictions_dict`**
Bridge the gRPC response to Alpaca orders:
```python
def _get_model_predictions_dict(self) -> dict:
    model_predictions_dict = {}
    for ticker in Constants.TICKER_SYMBOL_LIST:
        # Construct the request with gathered historical bars and tweets
        request = momentum_pb2.MomentumRequest(
            ticker=ticker,
            stock_history=stock_history,  # List of momentum_pb2.OHLCV
            market_history=market_history, # Dict of momentum_pb2.OHLCVList
            tweets=tweets                 # List of strings
        )
        
        # Call the gRPC service
        response = self.stub.PredictMomentum(request)
        
        # Use response.momentum to determine action
        # Example: Buy if momentum > 0.02, Sell if < -0.02
        if response.momentum > 0.02:
            action = OrderSide.BUY
        elif response.momentum < -0.02:
            action = OrderSide.SELL
        else:
            continue
            
        model_predictions_dict[ticker] = (quantity, current_price, action)
    
    return model_predictions_dict
```

#### **4. Execution Flow**
1. **Start Service**: Run `python grpc/momentum_server.py`.
2. **Execute Algorithm**: Run the trading implementation which will now query the live gRPC service for momentum signals before submitting orders to Alpaca.

---

Sample Model Outputs from the gRPC

| Index | GS | JPM | SPY | QQQ | BLK | WMT | NVDA | KO | CRWV | AAPL |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 0 | -0.0632 | -0.0115 | -0.0210 | -0.0253 | -0.0393 | -0.0446 | 0.0647 | -0.0073 | -0.3444 | -0.0332 |
| 1 | 0.0445 | 0.0234 | 0.0306 | 0.0221 | 0.0335 | 0.0085 | 0.0854 | 0.0291 | -0.1671 | -0.0310 |
| 2 | -0.0206 | 0.0025 | -0.0163 | -0.0204 | -0.0341 | -0.0315 | 0.1137 | -0.0138 | -0.2869 | -0.0621 |
| 3 | 0.0572 | 0.0554 | 0.0664 | 0.0423 | 0.0618 | 0.0701 | 0.1769 | 0.0822 | -0.1800 | -0.0388 |
| 4 | -0.0632 | -0.0115 | -0.0210 | -0.0253 | -0.0393 | -0.0446 | 0.0647 | -0.0073 | -0.3444 | -0.0330 |
| 5 | -0.0355 | -0.0330 | -0.0402 | -0.0519 | -0.0612 | 0.0085 | 0.0854 | 0.0291 | -0.1671 | -0.0173 |
| 6 | -0.0282 | -0.0127 | -0.0405 | -0.0483 | -0.0729 | -0.0315 | 0.1137 | -0.0138 | -0.2869 | -0.0588 |
| 7 | -0.0177 | -0.0255 | -0.0345 | -0.0286 | -0.0343 | 0.0701 | 0.1769 | 0.0822 | -0.1800 | -0.0480 |
| 8 | -0.0544 | -0.0200 | -0.0340 | -0.0393 | -0.0536 | -0.0408 | 0.0349 | -0.0235 | -0.2497 | -0.0238 |
| 9 | -0.0164 | -0.0029 | -0.0315 | -0.0459 | -0.0217 | -0.0519 | 0.0398 | -0.0237 | -0.0952 | -0.0676 |
| 10 | -0.0468 | -0.0394 | -0.0471 | -0.0506 | -0.0447 | 0.0276 | 0.0902 | 0.0560 | -0.0944 | -0.0284 |
| 11 | -0.0551 | -0.0503 | -0.0486 | -0.0573 | -0.0751 | 0.0078 | 0.1557 | 0.0750 | -0.1043 | -0.0289 |
| 12 | -0.0298 | -0.0276 | -0.0237 | -0.0276 | -0.0501 | -0.0312 | -0.0402 | -0.0123 | -0.3910 | -0.0692 |
| 13 | -0.0631 | -0.0708 | -0.0568 | -0.0613 | -0.0564 | 0.0055 | -0.0083 | -0.0285 | -0.1501 | -0.0237 |
| 14 | -0.0378 | -0.0265 | -0.0397 | -0.0488 | -0.0326 | 0.0020 | -0.0134 | 0.0398 | -0.2286 | -0.0358 |
| 15 | -0.0502 | -0.0662 | -0.0562 | -0.0634 | -0.0282 | 0.0559 | 0.0244 | 0.0650 | -0.1660 | -0.0406 |
| 16 | -0.0293 | -0.0312 | -0.0737 | -0.0797 | -0.0448 | -0.0341 | -0.0505 | -0.0552 | 0.0413 | -0.0736 |
| 17 | -0.0177 | -0.0220 | -0.0488 | -0.0571 | -0.0515 | 0.0575 | 0.0094 | 0.0094 | 0.0961 | -0.0487 |
| 18 | -0.0194 | -0.0390 | -0.0527 | -0.0531 | -0.0476 | 0.0409 | -0.0127 | 0.0003 | 0.0400 | -0.1420 |
| 19 | -0.0576 | -0.0501 | -0.0765 | -0.0799 | -0.0576 | 0.0892 | 0.0573 | 0.0631 | 0.0747 | -0.0120 |
| 20 | -0.0658 | -0.0931 | -0.0803 | -0.0932 | -0.0966 | -0.0326 | -0.1038 | -0.0079 | -0.2625 | -0.1155 |
| 21 | -0.0976 | -0.0598 | -0.0758 | -0.0785 | -0.1370 | 0.0463 | -0.0464 | 0.0253 | -0.0966 | -0.0472 |
| 22 | -0.0353 | -0.0546 | -0.1186 | -0.1445 | -0.0569 | 0.0439 | -0.0647 | -0.0192 | -0.1601 | -0.0222 |
| 23 | -0.0404 | -0.0369 | -0.0883 | -0.0979 | -0.0414 | 0.1012 | 0.0061 | 0.1114 | -0.1347 | -0.0020 |
| 24 | -0.0774 | -0.0756 | -0.0935 | -0.1212 | -0.1049 | -0.0189 | -0.0764 | -0.0114 | -0.1083 | 0.0119 |
| 25 | -0.1366 | -0.0344 | -0.0429 | -0.0421 | 0.0082 | 0.0163 | -0.0113 | -0.0057 | -0.0055 | 0.0286 |
| 26 | -0.1885 | -0.1445 | -0.0178 | -0.0230 | -0.1090 | 0.0110 | -0.0356 | -0.0651 | -0.0855 | -0.0095 |
| 27 | 0.0023 | 0.0014 | 0.0020 | -0.0031 | 0.0501 | 0.1100 | 0.0482 | 0.0522 | 0.0021 | 0.0015 |
| 28 | 0.0314 | 0.0464 | 0.0086 | 0.0089 | 0.0766 | -0.0692 | -0.0456 | -0.0742 | -0.2380 | -0.0312 |
| 29 | 0.0344 | -0.0154 | 0.0179 | 0.0070 | 0.0519 | -0.0465 | 0.0180 | 0.0003 | -0.0346 | 0.0065 |
| 30 | -0.2061 | -0.0554 | -0.0144 | -0.0077 | -0.1938 | 0.0069 | -0.0405 | -0.0564 | -0.1633 | -0.0070 |

Those values above are sample momentum values. This is raw output from the model, additional post processing can be done, but this is good for now I think. The higher the `abs` of the output, the more in that direction the model thinks the stock is going to go. The values on the front end are demeaning and unstandardized if that makes sense. The model is trained on standardized values (the mean of the training is 0), to help prevent skewing, so the values displayed on the front end needs to be unstandardized.

The model output is in the form:

`tensor([[-0.0632]], device='cuda:0')`

``` python3 
    # Line 520 of gRPC server.
    unstandardized_val = (standardized_val * m["target_std"]) + m["target_mean"]
```
---

### **Algorithmic Trading Approach**

The following outlines the policy our trading implementation will follow:

1. When first initializing our portfolio each equity will hold 5% of the portfolio while 50% of the portfolio will be held in cash reserves. 
- This allows us to purchase more shares in the event of upward momentum and sell shares in the event of downward momentum

2. At all times each equity will carry no less than 2.5% of the total portfolio and no more than 10% of the total portfolio.
- This will eliminate the possibility of attempting to sell an equity we don't own
- This will eliminate the possibility of our portfolio becoming too heavy weighted on a single equity

3. In the event an equity has an upward momentum of > 5%, then 0.5% of the total portfolio for that equity will be **purchased** (as long as the maximum holding percentage is not exceeded) 

4. In the event an equity has a downward momentum of > 5%, then 0.5% of that equity will be **sold** (as long as the minimum holding percentage is not passed)

5. This process will be repeated daily

**Extensions To This Policy:**

1. Add more equities
2. Lower the minimum we hold of a given equity to 1.0%
3. Increase the maximum we hold of a given equity to 11.5%
4. Decrease the upward momentum percentage that's required for us to purchase an equity
- i.e 5% to 4% 
5. Decrease the downward momentum percentage that's required for us to sell an equity
- i.e 5% to 4% 
6. Decrease the timeframe from which project into the future
- i.e. we currently project 5 days in the future, we will gradually scale this down until the application is day-trading
7. Incorporate call options
8. Incorporate put options

---
