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
  python3-pip

# Install AWS CLI v2 (Ubuntu repos can be behind).
if ! command -v aws >/dev/null 2>&1; then
  tmpdir="$(mktemp -d)"
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "$tmpdir/awscliv2.zip"
  unzip -q "$tmpdir/awscliv2.zip" -d "$tmpdir"
  "$tmpdir/aws/install" || true
  rm -rf "$tmpdir"
fi

DATA_VOLUME_ID="${data_volume_id}"
MOUNT_PATH="${mount_path}"
SSH_USER="${ssh_user}"

if [[ -n "$DATA_VOLUME_ID" ]]; then
  mkdir -p "$MOUNT_PATH"

  # On Nitro instances, EBS volumes appear as NVMe devices. The NVMe "serial"
  # typically contains the EBS volume id without dashes (e.g. vol0123...).
  data_volume_id_nodash="$(printf "%s" "$DATA_VOLUME_ID" | tr -d '-')"
  dev=""

  for _ in $(seq 1 30); do
    dev="$(nvme list 2>/dev/null | awk -v vid="$data_volume_id_nodash" '$0 ~ vid {print $1; exit}')"
    if [[ -n "$dev" ]]; then
      break
    fi
    sleep 2
  done

  # Fallback for non-NVMe mappings.
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
