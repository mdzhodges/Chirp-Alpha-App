variable "environment" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "public_subnets" {
  type = list(string)
}

variable "private_subnets" {
  type = list(string)
}

variable "backend_repo_url" {
  type = string
}

variable "frontend_repo_url" {
  type = string
}

variable "grpc_repo_url" {
  type = string
}

variable "logo_dev_api_key" {
  type    = string
  default = ""
}
