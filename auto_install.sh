#!/bin/bash
# Script di installazione automatica per Raspberry Pi Stream Manager
# Tutto si avvierà automaticamente al boot

set -e

echo "==============================================="
echo "  Raspberry Pi Stream Manager - Setup"
echo "==============================================="
echo ""

# Verifica che non sia root
if [ "$EUID" -eq 0 ]; then 
    echo "❌ Non eseguire questo script come root!"
    echo "Usa: bash auto_install.sh"
    exit 1
fi

# Step 1
echo "[1/8] Aggiornamento sistema..."
sudo apt update && sudo apt upgrade -y
echo "✓ Sistema aggiornato"
echo ""

# Step 2
echo "[2/8] Installazione dipendenze base..."
sudo apt install -y cmake libjpeg-dev gcc g++ git python3-pip python3-flask ffmpeg v4l-utils nginx
echo "✓ Dipendenze installate"
echo ""

# Step 3
echo "[3/8] Installazione librerie Python..."
pip3 install flask psutil --break-system-packages
echo "✓ Librerie Python installate"
echo ""

# Step 4
echo "[4/8] Compilazione mjpg-streamer..."
cd ~
[ -d "mjpg-streamer" ] && rm -rf mjpg-streamer
git clone https://github.com/jacksonliam/mjpg-streamer.git
cd mjpg-streamer/mjpg-streamer-experimental
make
sudo make install
echo "✓ mjpg-streamer compilato"
echo ""

# Step 5
echo "[5/8] Installazione MediaMTX..."
cd ~
ARCH=$(uname -m)
[ "$ARCH" = "aarch64" ] && MEDIAMTX_ARCH="arm64v8" || MEDIAMTX_ARCH="armv7"

wget -q https://github.com/bluenviron/mediamtx/releases/download/v1.5.0/mediamtx_v1.5.0_linux_${MEDIAMTX_ARCH}.tar.gz
tar -xzf mediamtx_v1.5.0_linux_${MEDIAMTX_ARCH}.tar.gz
sudo mv mediamtx /usr/local/bin/
sudo chmod +x /usr/local/bin/mediamtx
rm -f mediamtx_v1.5.0_linux_${MEDIAMTX_ARCH}.tar.gz
echo "✓ MediaMTX installato"
echo ""

# Step 6
echo "[6/8] Configurazione MediaMTX..."
sudo mkdir -p /etc/mediamtx
sudo tee /etc/mediamtx/mediamtx.yml > /dev/null <<'EOF'
logLevel: info
logDestinations: [stdout]
logFile: /var/log/mediamtx.log

rtspAddress: :8554
rtpAddress: :8000
rtcpAddress: :8001
hlsAddress: :8888

paths:
  all:
EOF
echo "✓ MediaMTX configurato"
echo ""

# Step 7
echo "[7/8] Creazione applicazione web..."
mkdir -p ~/videoStreamer/videos
mkdir -p ~/videoStreamer/templates
mkdir -p ~/videoStreamer/static
cd ~/videoStreamer

echo "⚠️  Copia i file necessari in ~/videoStreamer/:"
echo "   - app.py"
echo "   - change_password.py"
echo "   - change_hostname.sh"
echo "   - wifi_fallback.sh"
echo "   - templates/ (cartella con index.html e login.html)"
echo "   - static/ (cartella con stemma_small.png)"
echo ""
echo "Premi INVIO quando i file sono stati copiati..."
read

chmod +x app.py change_password.py change_hostname.sh wifi_fallback.sh 2>/dev/null || true

# Copia change_hostname.sh in /usr/local/bin se non lo è stato
if [ -f change_hostname.sh ]; then
    sudo cp change_hostname.sh /usr/local/bin/
    sudo chmod 755 /usr/local/bin/change_hostname.sh
    echo "✓ change_hostname.sh copiato in /usr/local/bin/"
fi

# Copia wifi_fallback.sh in /usr/local/bin
if [ -f wifi_fallback.sh ]; then
    sudo cp wifi_fallback.sh /usr/local/bin/
    sudo chmod 755 /usr/local/bin/wifi_fallback.sh
    echo "✓ wifi_fallback.sh copiato in /usr/local/bin/"
fi

echo "✓ File applicazione verificati"
echo ""

# Step 8
echo "[8/8] Configurazione servizi di avvio automatico..."

sudo tee /etc/systemd/system/stream-manager.service > /dev/null <<EOF
[Unit]
Description=Stream Manager Web Interface
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$HOME/videoStreamer
ExecStart=/usr/bin/python3 $HOME/videoStreamer/app.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/mediamtx.service > /dev/null <<EOF
[Unit]
Description=MediaMTX RTSP Server
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=$USER
ExecStart=/usr/local/bin/mediamtx /etc/mediamtx/mediamtx.yml
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable stream-manager.service
sudo systemctl enable mediamtx.service
sudo systemctl enable wifi-fallback.service
sudo systemctl start stream-manager.service
sudo systemctl start mediamtx.service
sudo systemctl start wifi-fallback.service
echo "✓ Servizi configurati e avviati"
echo ""

# Crea il servizio WiFi Fallback
echo "[8b/8] Configurazione WiFi Fallback Hotspot..."
sudo tee /etc/systemd/system/wifi-fallback.service > /dev/null <<EOF
[Unit]
Description=WiFi Fallback to Hotspot
After=network.target
Wants=network-online.target

[Service]
Type=oneshot
User=root
ExecStart=/usr/local/bin/wifi_fallback.sh
RemainAfterExit=yes
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
echo "✓ Servizio WiFi Fallback configurato"
echo ""

# Configurazione cloud-init
echo "Configurazione cloud-init..."
if [ -f /etc/cloud/cloud.cfg ]; then
    sudo sed -i 's/preserve_hostname: false/preserve_hostname: true/' /etc/cloud/cloud.cfg
    echo "✓ cloud-init configurato"
else
    echo "⚠️  /etc/cloud/cloud.cfg non trovato (opzionale)"
fi
echo ""

# Permessi sudo
echo "Configurazione permessi sudo..."
SUDOERS_FILE="/etc/sudoers.d/stream-manager"
sudo tee "$SUDOERS_FILE" > /dev/null <<'EOF'
# Permessi per Stream Manager
$USER ALL=(ALL) NOPASSWD: /bin/systemctl restart stream-manager
$USER ALL=(ALL) NOPASSWD: /bin/systemctl restart mediamtx
$USER ALL=(ALL) NOPASSWD: /bin/systemctl stop mediamtx
$USER ALL=(ALL) NOPASSWD: /bin/cp /tmp/mediamtx.yml /etc/mediamtx/mediamtx.yml
$USER ALL=(ALL) NOPASSWD: /usr/local/bin/change_hostname.sh
$USER ALL=(ALL) NOPASSWD: /bin/cp /tmp/hostname_new /etc/hostname
$USER ALL=(ALL) NOPASSWD: /bin/cp /tmp/hosts_new /etc/hosts
$USER ALL=(ALL) NOPASSWD: /usr/bin/hostname
$USER ALL=(ALL) NOPASSWD: /bin/systemctl restart systemd-hostnamed
$USER ALL=(ALL) NOPASSWD: /bin/netplan apply
$USER ALL=(ALL) NOPASSWD: /usr/sbin/netplan
EOF
sudo chmod 0440 "$SUDOERS_FILE"
echo "✓ Permessi sudo configurati"
echo ""

# Avvia servizi
echo "Avvio servizi..."
sudo systemctl start stream-manager.service || true
sudo systemctl start mediamtx.service || true
echo "✓ Servizi avviati"
echo ""

# Informazioni finali
IP=$(hostname -I | awk '{print $1}')

echo "==============================================="
echo "  ✅ Installazione completata!"
echo "==============================================="
echo ""
echo "🔐 CREDENZIALI DEFAULT (cambiale subito):"
echo "   Username: admin"
echo "   Password: admin"
echo ""
echo "📱 Accedi all'interfaccia web:"
echo "   http://$IP:5000"
echo ""
echo "🎥 Stream MJPG (quando avviato):"
echo "   http://$IP:8080"
echo ""
echo "📡 Stream RTSP (quando avviato):"
echo "   rtsp://$IP:8554/video"
echo ""
echo "🔑 Per cambiare password:"
echo "   cd ~/stream_manager"
echo "   python3 change_password.py"
echo ""
echo "🔧 Comandi utili:"
echo "   sudo systemctl status stream-manager"
echo "   sudo systemctl status mediamtx"
echo "   sudo journalctl -u stream-manager -f"
echo ""
echo "⚠️  IMPORTANTE: Cambia la password di default dopo il primo accesso!"
echo ""

