# infra_training

Terraform stack to create a single EC2 instance for model training (sized for uploading a ~60GB dataset via `scp`).

## Prereqs

- Terraform `>= 1.5`
- AWS credentials configured locally (e.g. `AWS_PROFILE`, `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`)
- An existing EC2 key pair name for SSH/SCP (`key_name`)

## Quick start

From this folder:

```bash
terraform init
terraform apply \
  -var 'key_name=YOUR_KEYPAIR_NAME'
```

Then use the output `ssh_command` / `scp_command_example`.

You can also copy `terraform.tfvars.example` to `terraform.tfvars` and run:

```bash
terraform apply
```

## Notes

- For non-default VPCs, set `subnet_id` explicitly to a subnet that has outbound internet access and (if you need SSH) a route to an Internet Gateway.
- `data_volume_size` creates an extra encrypted EBS volume mounted at `data_mount_path` (default: `/mnt/training`). Set `data_volume_size=0` to disable.
- `enable_ssm=true` attaches the AWS-managed SSM policy so you can use Session Manager as a backup access path.
- If you see an error about "not eligible for Free Tier" when using a GPU instance type, you're likely using a restricted AWS sandbox account (common in classroom/lab environments). Switch to a full AWS account/profile or use a free-tier instance type for testing.

## Uploading data (60GB+)

`scp` works, but for large transfers `rsync` is often more resumable:

```bash
rsync -avP -e "ssh -i /path/to/key.pem" /path/to/local/data/ ubuntu@YOUR_PUBLIC_DNS:/mnt/training/data/
```

## Cleanup

```bash
terraform destroy
```
