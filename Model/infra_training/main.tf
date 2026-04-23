provider "aws" {
  region  = var.region
  profile = var.aws_profile
}

# --- New Quota Request Block ---
resource "aws_servicequotas_service_quota" "vcpu_increase" {
  quota_code   = "L-1216C47A" # For Standard On-Demand instances. Use L-3819A6DF for GPU (G/VT) instances.
  service_code = "ec2"
  value        = 8          # Set this to the total number of vCPUs you require
}
# -------------------------------

data "http" "myip" {
  count = var.ssh_ingress_cidr == null && var.ssh_ingress_auto ? 1 : 0
  url   = "https://checkip.amazonaws.com/"
}

data "aws_vpc" "by_id" {
  count = var.vpc_id == null ? 0 : 1
  id    = var.vpc_id
}

data "aws_vpc" "default" {
  count   = var.vpc_id == null ? 1 : 0
  default = true
}

locals {
  vpc_id = var.vpc_id != null ? data.aws_vpc.by_id[0].id : data.aws_vpc.default[0].id
}

data "aws_subnets" "in_vpc" {
  filter {
    name   = "vpc-id"
    values = [local.vpc_id]
  }
}

locals {
  subnet_id = var.subnet_id != null ? var.subnet_id : tolist(data.aws_subnets.in_vpc.ids)[0]
}

data "aws_subnet" "selected" {
  id = local.subnet_id
}

data "aws_ami" "ubuntu_jammy" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

locals {
  ami_id = coalesce(var.ami_id, data.aws_ami.ubuntu_jammy.id)
  ssh_ingress_cidr = coalesce(
    var.ssh_ingress_cidr,
    var.ssh_ingress_auto ? format("%s/32", chomp(data.http.myip[0].response_body)) : null,
  )
  tags = merge(
    {
      Project = var.project_name
    },
    var.tags,
  )
}

resource "aws_security_group" "trainer" {
  name_prefix = "${var.project_name}-sg-"
  description = "Training instance security group"
  vpc_id      = local.vpc_id

  lifecycle {
    precondition {
      condition     = local.ssh_ingress_cidr != null
      error_message = "SSH ingress CIDR is not set. Set ssh_ingress_cidr (e.g. \"YOUR_PUBLIC_IP/32\") or enable ssh_ingress_auto=true."
    }
  }

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [local.ssh_ingress_cidr]
  }

  egress {
    description = "All egress"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.tags
}

data "aws_iam_policy" "ssm_core" {
  count = var.enable_ssm ? 1 : 0
  arn   = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role" "trainer" {
  count       = var.enable_ssm ? 1 : 0
  name_prefix = "${var.project_name}-role-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      },
    ]
  })

  tags = local.tags
}

resource "aws_iam_role_policy_attachment" "trainer_ssm" {
  count      = var.enable_ssm ? 1 : 0
  role       = aws_iam_role.trainer[0].name
  policy_arn = data.aws_iam_policy.ssm_core[0].arn
}

resource "aws_iam_instance_profile" "trainer" {
  count       = var.enable_ssm ? 1 : 0
  name_prefix = "${var.project_name}-profile-"
  role        = aws_iam_role.trainer[0].name
  tags        = local.tags
}

resource "aws_instance" "trainer" {
  ami                         = local.ami_id
  instance_type               = var.instance_type
  subnet_id                   = local.subnet_id
  vpc_security_group_ids      = [aws_security_group.trainer.id]
  key_name                    = var.key_name
  associate_public_ip_address = var.associate_public_ip

  iam_instance_profile = var.enable_ssm ? aws_iam_instance_profile.trainer[0].name : null

  root_block_device {
    encrypted   = true
    volume_size = var.root_volume_size
    volume_type = var.root_volume_type
    iops        = var.root_volume_type == "gp3" ? var.root_volume_iops : null
    throughput  = var.root_volume_type == "gp3" ? var.root_volume_throughput : null
  }

  user_data = templatefile("${path.module}/user_data.sh", {
    data_volume_id = var.data_volume_size > 0 ? aws_ebs_volume.data[0].id : ""
    mount_path     = var.data_mount_path
    ssh_user       = var.ssh_user
  })

  tags = merge(local.tags, { Name = "${var.project_name}-trainer" })
  
  # Ensure the instance waits for the quota increase to be processed
  depends_on = [aws_servicequotas_service_quota.vcpu_increase]
}

resource "aws_ebs_volume" "data" {
  count             = var.data_volume_size > 0 ? 1 : 0
  availability_zone = data.aws_subnet.selected.availability_zone
  size              = var.data_volume_size
  type              = var.data_volume_type
  encrypted         = true

  iops       = var.data_volume_type == "gp3" ? var.data_volume_iops : null
  throughput = var.data_volume_type == "gp3" ? var.data_volume_throughput : null

  tags = merge(local.tags, { Name = "${var.project_name}-data" })
}

resource "aws_volume_attachment" "data" {
  count       = var.data_volume_size > 0 ? 1 : 0
  device_name = "/dev/sdf"
  volume_id   = aws_ebs_volume.data[0].id
  instance_id = aws_instance.trainer.id
}