variable "project_name" {
  description = "Name prefix for AWS resources."
  type        = string
  default     = "chirp-training"
}

variable "region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "Optional AWS CLI profile name (useful if you have multiple accounts). If null, uses environment/default credentials."
  type        = string
  default     = null
}

variable "vpc_id" {
  description = "VPC to deploy into. If null, uses the account's default VPC."
  type        = string
  default     = null
}

variable "subnet_id" {
  description = "Subnet for the EC2 instance. If null, uses the first subnet found in the selected VPC."
  type        = string
  default     = null
}

variable "key_name" {
  description = "Existing EC2 Key Pair name to enable SSH/SCP."
  type        = string
}

variable "ssh_user" {
  description = "SSH username for the AMI (e.g. ubuntu for Ubuntu, ec2-user for Amazon Linux)."
  type        = string
  default     = "ubuntu"
}

variable "ssh_ingress_cidr" {
  description = "CIDR block allowed to SSH (port 22) into the instance. If null, and ssh_ingress_auto=true, uses your current public IP /32."
  type        = string
  default     = null
}

variable "ssh_ingress_auto" {
  description = "When true and ssh_ingress_cidr is null, auto-detect your current public IP for SSH ingress."
  type        = bool
  default     = true
}

variable "associate_public_ip" {
  description = "Whether to associate a public IP address with the instance."
  type        = bool
  default     = true
}

variable "instance_type" {
  description = "EC2 instance type for training."
  type        = string
  default     = "g5.2xlarge"
}

variable "ami_id" {
  description = "AMI ID to use. If null, uses Ubuntu 22.04 LTS (Jammy) amd64."
  type        = string
  default     = null
}

variable "root_volume_size" {
  description = "Root EBS volume size (GiB)."
  type        = number
  default     = 200
}

variable "root_volume_type" {
  description = "Root EBS volume type."
  type        = string
  default     = "gp3"
}

variable "root_volume_iops" {
  description = "Root EBS volume IOPS (gp3 only)."
  type        = number
  default     = 3000
}

variable "root_volume_throughput" {
  description = "Root EBS volume throughput (MiB/s, gp3 only)."
  type        = number
  default     = 125
}

variable "data_volume_size" {
  description = "Optional extra EBS volume size (GiB) mounted at data_mount_path. Set to 0 to disable."
  type        = number
  default     = 200
}

variable "data_volume_type" {
  description = "Extra EBS volume type."
  type        = string
  default     = "gp3"
}

variable "data_volume_iops" {
  description = "Extra EBS volume IOPS (gp3 only)."
  type        = number
  default     = 3000
}

variable "data_volume_throughput" {
  description = "Extra EBS volume throughput (MiB/s, gp3 only)."
  type        = number
  default     = 125
}

variable "data_mount_path" {
  description = "Mount path for the extra EBS volume."
  type        = string
  default     = "/mnt/training"
}

variable "enable_ssm" {
  description = "Attach an IAM role that enables AWS Systems Manager (Session Manager) access."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Additional tags applied to resources."
  type        = map(string)
  default     = {}
}
