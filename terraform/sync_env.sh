#!/bin/bash

# 1. Grab the raw values directly from Terraform
POOL_ID=$(terraform output -raw cognito_user_pool_id)
CLIENT_ID=$(terraform output -raw cognito_client_id)

# 2. Define the path to your frontend .env file 
# (Adjust the "../frontend/.env" path if your folder structure is different)
ENV_FILE="../frontend/.env"

# 3. Clean out the old IDs (macOS specific sed syntax)
sed -i '' '/^VITE_USER_POOL_ID=/d' $ENV_FILE
sed -i '' '/^VITE_USER_POOL_CLIENT_ID=/d' $ENV_FILE

# 4. Inject the fresh IDs
echo "VITE_USER_POOL_ID=$POOL_ID" >> $ENV_FILE
echo "VITE_USER_POOL_CLIENT_ID=$CLIENT_ID" >> $ENV_FILE

echo "✅ Frontend .env updated with fresh Moto Cognito IDs!"