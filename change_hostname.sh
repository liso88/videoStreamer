#!/usr/bin/env bash
# Script per cambiare l'hostname del Raspberry Pi
# Uso: sudo /usr/local/bin/change_hostname.sh nuovo_hostname

if [ $# -ne 1 ]; then
    echo "Uso: $0 <nuovo_hostname>"
    exit 1
fi

NEW_HOSTNAME="$1"

# Validazione
if ! [[ "$NEW_HOSTNAME" =~ ^[a-z0-9-]{1,63}$ ]]; then
    echo "Hostname non valido"
    exit 1
fi

echo "[0] Disabilito cloud-init per preservare l'hostname..."
if [ -f /etc/cloud/cloud.cfg ]; then
    sed -i 's/preserve_hostname: false/preserve_hostname: true/' /etc/cloud/cloud.cfg
    echo "✓ preserve_hostname impostato a true"
fi

echo "[1] Aggiorno /etc/hostname..."
echo "$NEW_HOSTNAME" > /etc/hostname
if [ "$(cat /etc/hostname)" != "$NEW_HOSTNAME" ]; then
    echo "Errore: /etc/hostname non scritto correttamente"
    exit 1
fi
echo "✓ /etc/hostname = $NEW_HOSTNAME"

echo "[2] Aggiorno /etc/hosts..."
sed -i "s/127\.0\.0\.1.*/127.0.0.1\tlocalhost $NEW_HOSTNAME/" /etc/hosts
echo "✓ /etc/hosts aggiornato"

echo "[3] Applico hostname immediatamente..."
hostname "$NEW_HOSTNAME"
echo "✓ hostname = $(hostname)"

echo "[4] Riavvio systemd-hostnamed..."
systemctl restart systemd-hostnamed 2>/dev/null || true
echo "✓ systemd-hostnamed riavviato"

echo "[5] Configuro hostnamectl..."
if command -v hostnamectl &> /dev/null; then
    hostnamectl set-hostname "$NEW_HOSTNAME"
    echo "✓ hostnamectl set-hostname = $(hostnamectl hostname)"
fi

echo ""
echo "✅ Hostname cambiato in: $NEW_HOSTNAME"
echo "   Persistente al riavvio: SI (cloud-init disabilitato)"

