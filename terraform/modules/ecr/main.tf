resource "aws_ecr_repository" "backend" {
  name                 = "chirp-backend"
  image_tag_mutability = "MUTABLE"
  force_delete         = true
}

resource "aws_ecr_repository" "frontend" {
  name                 = "chirp-frontend"
  image_tag_mutability = "MUTABLE"
  force_delete         = true
}

resource "aws_ecr_repository" "grpc" {
  name                 = "chirp-grpc"
  image_tag_mutability = "MUTABLE"
  force_delete         = true
}

output "backend_repo_url" {
  value = aws_ecr_repository.backend.repository_url
}

output "frontend_repo_url" {
  value = aws_ecr_repository.frontend.repository_url
}

output "grpc_repo_url" {
  value = aws_ecr_repository.grpc.repository_url
}
