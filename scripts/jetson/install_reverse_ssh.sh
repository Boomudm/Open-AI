#!/usr/bin/env bash
# Install persistent reverse SSH tunnel: Jetson → VPS → Mac can `ssh jetson`
#
# Run ON the Jetson (local console / LAN SSH):
#   VPS_HOST=130.61.x.x VPS_USER=ubuntu ./scripts/jetson/install_reverse_ssh.sh
#
# Optional:
#   VPS_PORT=22          # use 443 if Fortinet blocks outbound 22
#   REMOTE_LISTEN=2222   # port on VPS that forwards to Jetson :22
#   VPS_KEY_PATH=...     # private key on Jetson (default ~/.ssh/id_ed25519_vps)
set -euo pipefail

VPS_HOST="${VPS_HOST:?set VPS_HOST to the VPS public IP or hostname}"
VPS_USER="${VPS_USER:-ubuntu}"
VPS_PORT="${VPS_PORT:-22}"
REMOTE_LISTEN="${REMOTE_LISTEN:-2222}"
KEY_PATH="${VPS_KEY_PATH:-$HOME/.ssh/id_ed25519_vps}"
SERVICE_NAME="jetson-reverse-ssh"
UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

echo "==> Reverse SSH: $(whoami)@$(hostname) → ${VPS_USER}@${VPS_HOST}:${VPS_PORT} (R ${REMOTE_LISTEN}:localhost:22)"

if [[ "$(id -u)" -eq 0 ]]; then
  echo "Run as the jetson user (not root). Script will sudo when needed."
  exit 1
fi

echo "==> Ensure openssh client + autossh"
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-client autossh

if [[ ! -f "$KEY_PATH" ]]; then
  echo "==> Creating SSH key: $KEY_PATH"
  mkdir -p "$(dirname "$KEY_PATH")"
  ssh-keygen -t ed25519 -f "$KEY_PATH" -N "" -C "jetson-reverse-ssh@$(hostname)"
fi

echo "==> Public key (must be in ${VPS_USER}@${VPS_HOST}:~/.ssh/authorized_keys):"
echo "----"
cat "${KEY_PATH}.pub"
echo "----"

if [[ "${SKIP_VPS_PUSH:-0}" != "1" ]]; then
  echo "==> Trying to install key on VPS (needs password or existing access once)"
  if ssh-copy-id -i "${KEY_PATH}.pub" -p "$VPS_PORT" -o StrictHostKeyChecking=accept-new \
    "${VPS_USER}@${VPS_HOST}"; then
    echo "    key installed"
  else
    echo "WARN: ssh-copy-id failed. Paste the public key above onto the VPS manually, then re-run:"
    echo "  SKIP_VPS_PUSH=1 VPS_HOST=$VPS_HOST VPS_USER=$VPS_USER VPS_PORT=$VPS_PORT $0"
    exit 2
  fi
fi

echo "==> Testing SSH Jetson → VPS"
ssh -i "$KEY_PATH" -p "$VPS_PORT" \
  -o BatchMode=yes \
  -o ConnectTimeout=15 \
  -o StrictHostKeyChecking=accept-new \
  "${VPS_USER}@${VPS_HOST}" 'echo VPS_OK; hostname; date -u'

echo "==> Writing systemd unit: $UNIT_PATH"
sudo tee "$UNIT_PATH" >/dev/null <<EOF
[Unit]
Description=Reverse SSH tunnel Jetson to VPS
After=network-online.target
Wants=network-online.target

[Service]
User=$(whoami)
Environment=AUTOSSH_GATETIME=0
ExecStart=/usr/bin/autossh -M 0 -N \\
  -i ${KEY_PATH} \\
  -p ${VPS_PORT} \\
  -o ServerAliveInterval=30 \\
  -o ServerAliveCountMax=3 \\
  -o ExitOnForwardFailure=yes \\
  -o StrictHostKeyChecking=accept-new \\
  -R ${REMOTE_LISTEN}:localhost:22 \\
  ${VPS_USER}@${VPS_HOST}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE_NAME"
sleep 2
sudo systemctl --no-pager --full status "$SERVICE_NAME" || true

echo ""
echo "==> Done on Jetson."
echo "    From Mac (after Mac SSH config is set):"
echo "      ssh -p ${REMOTE_LISTEN} -J ${VPS_USER}@${VPS_HOST} jetson@127.0.0.1"
echo "    Logs: journalctl -u ${SERVICE_NAME} -f"
