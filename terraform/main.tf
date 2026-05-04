variable "environment" {
  type    = string
  default = "local"
}

provider "aws" {
  region = "us-east-1"

  # Use mock credentials if local, default to AWS profile if prod
  access_key                  = var.environment == "local" ? "test" : null
  secret_key                  = var.environment == "local" ? "test" : null
  skip_credentials_validation = var.environment == "local"
  skip_requesting_account_id  = var.environment == "local"
  skip_metadata_api_check     = var.environment == "local"
}

module "auth" {
  source      = "./modules/auth"
  pool_name   = "chirp_alpha_pool_${var.environment}"
  client_name = "chirp_alpha_client_${var.environment}"
}

module "networking" {
  source      = "./modules/networking"
  environment = var.environment
}

module "ecr" {
  source      = "./modules/ecr"
}

module "compute" {
  source           = "./modules/compute"
  environment      = var.environment
  vpc_id           = module.networking.vpc_id
  public_subnets   = module.networking.public_subnets
  backend_repo_url = module.ecr.backend_repo_url
  frontend_repo_url = module.ecr.frontend_repo_url
  grpc_repo_url    = module.ecr.grpc_repo_url
}