output "instance_id" {
  value = aws_instance.trainer.id
}

output "public_ip" {
  value = aws_instance.trainer.public_ip
}

output "public_dns" {
  value = aws_instance.trainer.public_dns
}

output "ssh_command" {
  value = "ssh -i /path/to/key.pem ${var.ssh_user}@${aws_instance.trainer.public_dns}"
}

output "scp_command_example" {
  value = "scp -i /path/to/key.pem -r /path/to/local/data ${var.ssh_user}@${aws_instance.trainer.public_dns}:${var.data_mount_path}/data"
}

output "s3_bucket_name" {
  value = aws_s3_bucket.training_results.id
  description = "S3 bucket for training results - use this as S3_BUCKET in your .env"
}

