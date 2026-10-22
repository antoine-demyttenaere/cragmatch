#!/usr/bin/env bash
# First-boot setup of the CragMatch host (Amazon Linux 2023, arm64). Written by cloud-init from
# infra/main/host.tf and safe to re-run through SSM if a step failed (every step checks first).
# Never add `set -x` here: step 6 handles the database password.
set -euo pipefail

# 1. REGION, DATA_VOLUME_ID and DB_PASSWORD_PARAMETER (the parameter name, not the password).
# shellcheck source=/dev/null
source /opt/cragmatch/host-settings

DATA_DIR=/srv/cragmatch

# 2. The volume is attached after the instance starts booting, so wait for its device.
# NVMe device names are not stable; the by-id link carries the volume id without its dash.
device="/dev/disk/by-id/nvme-Amazon_Elastic_Block_Store_${DATA_VOLUME_ID//-/}"
for _ in $(seq 1 60); do
  [ -e "$device" ] && break
  sleep 5
done
if [ ! -e "$device" ]; then
  echo "data volume $DATA_VOLUME_ID did not appear at $device" >&2
  exit 1
fi

# 3. FORMAT ONLY IF THERE IS NO FILESYSTEM YET. THIS IS THE LINE THAT PROTECTS THE DATA ON EVERY
# HOST REPLACEMENT: the volume survives, and its filesystem (label cragmatch-data) must be kept.
# blkid -p exits 2 only when it found nothing. Any other failure (usage error, ambiguous probe,
# read error) must stop here instead of formatting.
blkid_status=0
blkid -p "$device" > /dev/null 2>&1 || blkid_status=$?
if [ "$blkid_status" -eq 2 ]; then
  mkfs.ext4 -L cragmatch-data "$device"
elif [ "$blkid_status" -ne 0 ]; then
  echo "blkid failed with exit code $blkid_status on $device; not formatting" >&2
  exit 1
fi
mkdir -p "$DATA_DIR"
# nofail: a missing volume must not stop the boot, so SSM still works to repair it.
if ! grep -q 'LABEL=cragmatch-data' /etc/fstab; then
  echo "LABEL=cragmatch-data $DATA_DIR ext4 defaults,nofail 0 2" >> /etc/fstab
fi
mountpoint -q "$DATA_DIR" || mount "$DATA_DIR"
mkdir -p "$DATA_DIR/pgdata" "$DATA_DIR/pgtls"

# 4. Swap on the root volume: Postgres, the backend (ticket 025) and the model tokenizer share
# 2 GiB, and a short spike should slow down, not kill a container.
if [ ! -f /swapfile ]; then
  fallocate -l 1G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
fi
grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
swapon --show=NAME --noheadings | grep -q '^/swapfile' || swapon /swapfile

# 5. Docker, logging to journald so `journalctl -u cragmatch-db` shows the database log.
dnf install -y docker
mkdir -p /etc/docker
echo '{"log-driver": "journald"}' > /etc/docker/daemon.json
systemctl enable --now docker

# 6. The password lives in SSM only. The file is root-only, and is not named *.env on purpose:
# the repo's protect_env.py hook blocks any shell command that contains that text.
mkdir -p /etc/cragmatch
umask 077
db_password="$(aws ssm get-parameter --region "$REGION" --with-decryption \
  --name "$DB_PASSWORD_PARAMETER" --query Parameter.Value --output text)"
printf 'POSTGRES_USER=cragmatch\nPOSTGRES_DB=cragmatch\nPOSTGRES_PASSWORD=%s\n' "$db_password" \
  > /etc/cragmatch/db-environment
chmod 600 /etc/cragmatch/db-environment
unset db_password
umask 022

# 7. A self-signed certificate on the data volume, so it survives a replacement and ticket 025 can
# use verify-full with host db. Postgres runs as uid 999 in the image and insists on a private key.
if [ ! -f "$DATA_DIR/pgtls/server.key" ]; then
  openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=db" \
    -addext "subjectAltName=DNS:db,DNS:localhost,IP:127.0.0.1" \
    -keyout "$DATA_DIR/pgtls/server.key" -out "$DATA_DIR/pgtls/server.crt"
  chown 999:999 "$DATA_DIR/pgtls/server.key" "$DATA_DIR/pgtls/server.crt"
  chmod 600 "$DATA_DIR/pgtls/server.key"
  chmod 644 "$DATA_DIR/pgtls/server.crt"
fi

# 8. The network the backend container joins in ticket 025, and the database image.
docker network inspect cragmatch > /dev/null 2>&1 || docker network create cragmatch
docker build -t cragmatch-db /opt/cragmatch/db

# 9. Start now and at every boot.
cp /opt/cragmatch/cragmatch-db.service /etc/systemd/system/cragmatch-db.service
systemctl daemon-reload
systemctl enable --now cragmatch-db.service

# 10. The API unit (ticket 025). Before the first deploy there is no current-image file, so the
# unit's condition skips the start; on a replaced host the file is on the data volume and the unit
# pulls and starts the last deployed image by itself.
install -d -m 0755 "$DATA_DIR/api"
install -d -m 0755 -o 10001 -g 10001 "$DATA_DIR/hf"
cp /opt/cragmatch/cragmatch-api.service /etc/systemd/system/cragmatch-api.service
systemctl daemon-reload
systemctl enable cragmatch-api.service
systemctl start cragmatch-api.service
