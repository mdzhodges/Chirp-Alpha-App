# Infrastructure

This directory contains the Terraform configuration for Chirp Alpha's AWS infrastructure.

## Prerequisites
* Docker (for local emulation)
* Terraform

## Local Development

We use Moto to mock AWS services (like Cognito) locally without requiring an account or license.

**1. Start Moto**
```bash
docker run --rm -it -p 5000:5000 motoserver/moto:latest
```

**2. Configure Environment**
Route Terraform's AWS requests to your local Moto container:
```bash
export AWS_ENDPOINT_URL="http://localhost:5000"
```

**3. Provision Infrastructure**
```bash
terraform init
terraform apply -var="environment=local"
```

## Production Deployment

To deploy to real AWS, remove the local override and provide standard AWS credentials.

```bash
unset AWS_ENDPOINT_URL
terraform init
terraform apply -var="environment=prod"
```