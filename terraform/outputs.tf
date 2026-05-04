output "cognito_user_pool_id" {
  value = module.auth.user_pool_id
}

output "cognito_client_id" {
  value = module.auth.client_id
}

output "alb_dns_name" {
  value = module.compute.alb_dns_name
}