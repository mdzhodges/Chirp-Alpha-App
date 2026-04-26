#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

apt-get update -y
apt-get install -y --no-install-recommends \
  ca-certificates \
  curl \
  git \
  htop \
  jq \
  nvme-cli \
  tmux \
  unzip \
  vim \
  python3 \
  python3-venv \
  python3-pip \
  software-properties-common \
  add-apt-reposal \
  gnupg \
  ca-certificates \
  wget

# Install CUDA drivers for GPU instances
if ! command -v nvidia-smi >/dev/null 2>&1; then
  wget -q https://us.download.nvidia.com/tesla/535.129.03/NVIDIA-Linux-x86_64-535.129.03.run -O /tmp/nvidia.run || true
  if [[ -f /tmp/nvidia.run ]]; then
    chmod +x /tmp/nvidia.run
    /tmp/nvidia.run --silent --dkms || true
    rm -f /tmp/nvidia.run
  fi
fi

# Install AWS CLI v2
if ! command -v aws >/dev/null 2>&1; then
  tmpdir="$(mktemp -d)"
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "$tmpdir/awscliv2.zip"
  unzip -q "$tmpdir/awscliv2.zip" -d "$tmpdir"
  "$tmpdir/aws/install" || true
  rm -rf "$tmpdir"
fi

# Install Poetry for Python dependency management
if ! command -v poetry >/dev/null 2>&1; then
  curl -sSL https://install.python-poetry.org | python3 - --version 1.8.0 || true
fi

DATA_VOLUME_ID="${data_volume_id}"
MOUNT_PATH="${mount_path}"
SSH_USER="${ssh_user}"

if [[ -n "$DATA_VOLUME_ID" ]]; then
  mkdir -p "$MOUNT_PATH"

  data_volume_id_nodash="$(printf "%s" "$DATA_VOLUME_ID" | tr -d '-')"
  dev=""

  for _ in $(seq 1 30); do
    dev="$(nvme list 2>/dev/null | awk -v vid="$data_volume_id_nodash" '$0 ~ vid {print $1; exit}')"
    if [[ -n "$dev" ]]; then
      break
    fi
    sleep 2
  done

  if [[ -z "$dev" ]] && [[ -b /dev/xvdf ]]; then
    dev="/dev/xvdf"
  fi

  if [[ -n "$dev" ]] && [[ -b "$dev" ]]; then
    if ! blkid "$dev" >/dev/null 2>&1; then
      mkfs.ext4 -F "$dev"
    fi

    if ! mountpoint -q "$MOUNT_PATH"; then
      mount "$dev" "$MOUNT_PATH"
    fi

    if ! grep -q " $MOUNT_PATH " /etc/fstab; then
      echo "$dev $MOUNT_PATH ext4 defaults,nofail 0 2" >> /etc/fstab
    fi

    if id "$SSH_USER" >/dev/null 2>&1; then
      chown "$SSH_USER:$SSH_USER" "$MOUNT_PATH"
    fi
  fi
fi

# Create symlink from home directory for easy access
if [[ -d "/mnt/training" ]] && [[ "$SSH_USER" != "root" ]]; then
  su - "$SSH_USER" -c "ln -sf /mnt/training /home/$SSH_USER/training" || true
fi

# Copy .env file and install Python dependencies
if [[ -d "$MOUNT_PATH" ]]; then
  if [[ -f "$MOUNT_PATH/Model/.env" ]]; then
    cp "$MOUNT_PATH/Model/.env" /home/"$SSH_USER"/.env || true
  fi
  
  cd "$MOUNT_PATH/Model" || exit 0
  if [[ -f pyproject.toml ]]; then
    poetry install --no-interaction || pip install -e . || true
  fi
fi
