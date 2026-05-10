# Chirp Alpha

<p align="center">
  <img src="https://img.shields.io/badge/Stars-Private%20Repo-lightgrey?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Last%20Commit-Private%20Repo-lightgrey?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Python-3.12+-blue?style=for-the-badge&logo=python" />
  <img src="https://img.shields.io/badge/Java-21+-orange?style=for-the-badge&logo=openjdk" />
  <img src="https://img.shields.io/badge/React-18+-61DAFB?style=for-the-badge&logo=react" />
  <img src="https://img.shields.io/badge/Terraform-Infrastructure-623CE4?style=for-the-badge&logo=terraform" />
</p>

Chirp Alpha is a sophisticated multimodal machine learning platform designed to predict financial market momentum. By fusing real-time sentiment analysis from social media (FinTwit) with historical stock and market index data, it provides actionable insights for algorithmic trading and retail investment.

---

## Architecture Overview

The system is built as a distributed microservices architecture, ensuring scalability and separation of concerns:

- **Frontend (React/Vite)**: A modern, responsive dashboard for visualizing ticker metrics, momentum signals, and portfolio health.
- **Backend (Spring Boot 3)**: Orchestrates data flow, manages user chirps/signals, and provides a robust REST API.
- **Inference Engine (gRPC/Python)**: A high-performance Python service that serves ML model predictions via gRPC.
- **ML Pipeline (PyTorch)**: A comprehensive suite for data collection, preprocessing, training, and walk-forward validation.
- **Infrastructure (Terraform/AWS)**: Automated provisioning of AWS resources (ECR, ECS, Cognito, Networking) with local emulation via Moto.

---

## Machine Learning Engine: The Brain

Chirp Alpha utilizes a **Multimodal Triple-Tower Architecture** to capture the complex relationship between sentiment and price action.

### 1. Sentiment Encoder Tower
- **Model**: Leverages pre-trained BERT-based encoders (e.g., `FinTwitBERT` or `FinBERT-tone`) specifically tuned for financial sentiment.
- **Processing**: Embeddings are mean-pooled across the [CLS] vector for multi-tweet days, resulting in a 768-dimensional sentiment representation.
- **Optimization**: The encoder is frozen during primary training to prioritize computational efficiency while focusing on the fusion layers.

### 2. Stock Neural Network Tower
- **Input**: 37-dimensional time-series data per stock.
- **Architecture**: Deep NN with hidden layers (128 -> 64 -> 32).
- **Features**: LeakyReLU activation and Dropout layers to combat overfitting and ensure gradient flow.

### 3. Market Index Neural Network Tower
- **Input**: 42-dimensional market-wide indicators (SPY, QQQ, DIA, ^VIX).
- **Architecture**: Hidden layers (64 -> 32 -> 16).
- **Purpose**: Provides macroeconomic context to the specific stock momentum prediction.

### 4. Fusion & Output Layer
- **Projection**: The 768-dim sentiment embedding is projected down to 32 dimensions via a learnable layer to prevent it from dominating the 80-dimensional fused representation (32 Stock + 16 Index + 32 Sentiment).
- **Regression Heads**: Supports Linear, Shallow, and Deep regression heads to predict the target momentum value.

---

## gRPC & Data Flow

The integration between the trading implementation and the ML model is handled via **gRPC**, defined in `momentum.proto`.

### Key RPC Methods:
- `PredictMomentum`: Single ticker inference.
- `BatchPredictMomentum`: High-throughput batch inference.

### Sample Request Structure:
```protobuf
message MomentumRequest {
  string ticker = 1;
  repeated OHLCV stock_history = 2;
  map<string, OHLCVList> market_history = 3; // SPY, QQQ, DIA, ^VIX
  repeated string tweets = 4;
}
```

---

## Algorithmic Trading Strategy

The platform includes a production-ready trading implementation using the **Alpaca Markets API**.

### Risk Management Policy:
1. **Portfolio Allocation**: 50% cash reserve, 5% initial weight per equity.
2. **Dynamic Rebalancing**: Min 2.5%, Max 10% per equity to prevent over-concentration.
3. **Execution Logic**: 
   - **Buy**: If predicted momentum > 5% (up to max holding).
   - **Sell**: If predicted momentum < -5% (down to min holding).
4. **Timeframe**: Currently projects 5 trading days into the future.

---

## Tech Stack

| Layer | Technology |
| :--- | :--- |
| **Frontend** | React, Vite, CSS Modules |
| **Backend** | Java 21, Spring Boot, Redis, Maven |
| **Inference** | Python 3.12, gRPC, PyTorch, Transformers |
| **Data** | Parquet, Pandas, Polars, S3 |
| **Infrastructure** | Terraform, AWS (ECR, Cognito, ECS), Docker |
| **Mocking** | Moto (AWS), Redis Container |

---

## Quick Start

### 1. Local Development
The repository includes a convenience script to launch the entire stack:
```bash
./run_app.sh
```
This script handles:
- Starting a Redis container.
- Launching the Python gRPC service.
- Running the Spring Boot backend.
- Starting the Vite development server.

### 2. Infrastructure Setup (Local)
Mock AWS services locally using Moto:
```bash
docker run -p 5000:5000 motoserver/moto:latest
export AWS_ENDPOINT_URL="http://localhost:5000"
cd terraform && terraform apply -var="environment=local"
```

---

## Repository Structure

```text
.
├── backend/            # Spring Boot REST API
├── frontend/           # React Application
├── grpc/               # gRPC Service & Proto Definitions
├── Model/              # ML Pipeline & Trading Logic
│   ├── architecture/   # PyTorch Model Definitions
│   ├── training_account/# Alpaca Trading Implementation
│   └── preprocessing/  # Data Cleaning & Collection
├── terraform/          # IaC for AWS Deployment
└── run_app.sh          # All-in-one startup script
```

---

## Future Roadmap
- [ ] Transition from 5-day projections to intraday day-trading.
- [ ] Incorporate Call and Put option strategies.
- [ ] Expand the ticker universe beyond the current core set (AAPL, NVDA, GS, etc.).
- [ ] Implement live sentiment streaming from social media APIs.

---
*Created by the Chirp Alpha Team.*
