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