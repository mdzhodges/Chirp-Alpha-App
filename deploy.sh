#!/bin/bash

# Exit on error
set -e

# Configuration
# Usage: ./deploy.sh [service] [environment]
# Example: ./deploy.sh backend prod
SERVICE=${1:-all}
ENVIRONMENT=${2:-prod}
AWS_REGION="us-east-1"
TERRAFORM_DIR="./terraform"
CLUSTER_NAME="chirp-cluster-$ENVIRONMENT"

echo "🚀 Starting deployment (Service: $SERVICE, Env: $ENVIRONMENT)..."

# 1. Apply Terraform
echo "🏗️  Applying Terraform infrastructure..."
cd $TERRAFORM_DIR
terraform init
terraform apply -var="environment=$ENVIRONMENT" -auto-approve

# Get ECR Repository URLs
BACKEND_REPO=$(terraform output -raw backend_repo_url)
FRONTEND_REPO=$(terraform output -raw frontend_repo_url)
GRPC_REPO=$(terraform output -raw grpc_repo_url)
ALB_DNS=$(terraform output -raw alb_dns_name)
cd ..

# 2. Authenticate Docker with ECR
echo "🔑 Authenticating Docker with ECR..."
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $BACKEND_REPO

# 3. Build, Push, and Force Restart
if [ "$SERVICE" == "all" ] || [ "$SERVICE" == "backend" ]; then
    echo "📦 Building and pushing Backend..."
    docker build -t $BACKEND_REPO:latest ./backend
    docker push $BACKEND_REPO:latest
    echo "🔄 Forcing Backend redeployment..."
    aws ecs update-service --cluster $CLUSTER_NAME --service backend --force-new-deployment --region $AWS_REGION > /dev/null
fi

if [ "$SERVICE" == "all" ] || [ "$SERVICE" == "frontend" ]; then
    echo "📦 Building and pushing Frontend..."
    docker build -t $FRONTEND_REPO:latest ./frontend
    docker push $FRONTEND_REPO:latest
    echo "🔄 Forcing Frontend redeployment..."
    aws ecs update-service --cluster $CLUSTER_NAME --service frontend --force-new-deployment --region $AWS_REGION > /dev/null
fi

if [ "$SERVICE" == "all" ] || [ "$SERVICE" == "grpc" ]; then
    echo "📦 Building and pushing gRPC..."
    docker build -t $GRPC_REPO:latest ./grpc
    docker push $GRPC_REPO:latest
    echo "🔄 Forcing gRPC redeployment..."
    aws ecs update-service --cluster $CLUSTER_NAME --service grpc --force-new-deployment --region $AWS_REGION > /dev/null
fi

echo "✅ Deployment complete!"
echo "🌐 Load Balancer DNS: $ALB_DNS"
echo "💡 Tip: Monitor logs with: aws logs tail /ecs/backend-$ENVIRONMENT --follow"
