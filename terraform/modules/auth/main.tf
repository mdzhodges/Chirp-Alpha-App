resource "aws_cognito_user_pool" "pool" {
  name = var.pool_name
}

resource "aws_cognito_user_pool_client" "client" {
  name            = var.client_name
  user_pool_id    = aws_cognito_user_pool.pool.id
  generate_secret = false
}