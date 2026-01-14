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
sudo apt install -y cmake libjpeg-dev gcc g++ git python3-pip python3-flask ffmpeg v4l-utils nginx network-manager iw wireless-tools
echo "✓ Dipendenze installate"

# Abilita e avvia NetworkManager (necessario per hotspot)
sudo systemctl enable NetworkManager
sudo systemctl start NetworkManager
echo "✓ NetworkManager abilitato e avviato"
echo ""

# Step 2b - Configurazione Nginx come reverse proxy
echo "[2b/8] Configurazione Nginx come reverse proxy..."
sudo tee /etc/nginx/sites-available/stream-manager > /dev/null <<'EOF'
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    client_max_body_size 2000M;

    location / {
        proxy_pass http://localhost:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_request_buffering off;
    }
}
EOF

# Abilita il sito nginx
sudo rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
sudo ln -sf /etc/nginx/sites-available/stream-manager /etc/nginx/sites-enabled/stream-manager 2>/dev/null || true

# Test configurazione nginx
sudo nginx -t && echo "✓ Configurazione Nginx OK" || echo "⚠️  Errore configurazione Nginx"

# Abilita e avvia nginx
sudo systemctl enable nginx
sudo systemctl restart nginx
echo "✓ Nginx configurato come reverse proxy"
echo ""

# Step 3
echo "[3/8] Installazione librerie Python..."
pip3 install flask psutil --break-system-packages
echo "✓ Librerie Python installate"
echo ""

# Step 3b
echo "[3b/8] Configurazione permessi dispositivi..."
sudo usermod -a -G video,dialout,plugdev $USER
sudo chmod a+rw /dev/video* 2>/dev/null || true
echo "✓ Permessi dispositivi configurati"
echo "⚠️  Potrebbe essere necessario effettuare il logout e login per applicare i permessi di gruppo"
echo ""

# Step 4
echo "[4/8] Compilazione mjpg-streamer..."
echo "ℹ️  La compilazione potrebbe richiedere diversi minuti su dispositivi con risorse limitate..."
cd ~
[ -d "mjpg-streamer" ] && rm -rf mjpg-streamer
git clone --depth 1 https://github.com/jacksonliam/mjpg-streamer.git
cd mjpg-streamer/mjpg-streamer-experimental
# Usa un solo job per evitare problemi di memoria
make -j1
sudo make install
echo "✓ mjpg-streamer compilato"
echo ""

# Step 5
echo "[5/8] Installazione MediaMTX..."
cd ~
ARCH=$(uname -m)
if [ "$ARCH" = "aarch64" ]; then
    MEDIAMTX_ARCH="arm64v8"
else
    MEDIAMTX_ARCH="armv7"
fi
echo "ℹ️  Architettura rilevata: $ARCH -> MediaMTX: $MEDIAMTX_ARCH"

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

# Crea file di log per wifi_fallback
sudo touch /var/log/wifi_fallback.log
sudo chmod 644 /var/log/wifi_fallback.log

# Configura NetworkManager per WiFi Fallback
if command -v nmcli &> /dev/null; then
    sudo mkdir -p /etc/NetworkManager/conf.d/
    sudo tee /etc/NetworkManager/conf.d/hotspot-fallback.conf > /dev/null <<'NMEOF'
[main]
plugins=keyfile

[keyfile]
unmanaged-devices=
NMEOF
    
    # Disabilita power management WiFi per evitare che l'hotspot sparisca
    sudo tee /etc/NetworkManager/conf.d/wifi-powersave.conf > /dev/null <<'PWEOF'
[wifi]
wifi.powersave = 2
PWEOF
    echo "✓ Power save WiFi disabilitato"
    
    # Riavvia NetworkManager per applicare la configurazione
    sudo systemctl restart NetworkManager
    echo "✓ NetworkManager configurato"
else
    echo "⚠️  NetworkManager non trovato! L'hotspot WiFi non funzionerà."
    echo "   Installa con: sudo apt install network-manager"
fi

echo "✓ File applicazione verificati e WiFi Fallback configurato"
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

# Crea il servizio WiFi Fallback
echo "[8b/8] Configurazione WiFi Fallback Hotspot..."
sudo tee /etc/systemd/system/wifi-fallback.service > /dev/null <<EOF
[Unit]
Description=WiFi Fallback to Hotspot
After=network-online.target NetworkManager.service
Wants=network-online.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/wifi_fallback.sh
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
EOF
echo "✓ Servizio WiFi Fallback configurato"
echo ""

sudo systemctl daemon-reload
sudo systemctl enable stream-manager.service
sudo systemctl enable mediamtx.service
sudo systemctl enable wifi-fallback.service
echo "✓ Servizi abilitati all'avvio"
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
sudo tee "$SUDOERS_FILE" > /dev/null <<EOF
# Permessi per Stream Manager - utente: $USER
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
$USER ALL=(ALL) NOPASSWD: /usr/bin/nmcli
$USER ALL=(ALL) NOPASSWD: /usr/bin/killall
$USER ALL=(ALL) NOPASSWD: /bin/rm -f /tmp/hotspot_active
$USER ALL=(ALL) NOPASSWD: /sbin/shutdown
$USER ALL=(ALL) NOPASSWD: /sbin/reboot
EOF
sudo chmod 0440 "$SUDOERS_FILE"
echo "✓ Permessi sudo configurati"
echo ""

# Avvio servizi
echo "Avvio servizi..."
sudo systemctl start stream-manager.service || true
sudo systemctl start mediamtx.service || true
sudo systemctl start wifi-fallback.service || true
echo "✓ Servizi avviati"
echo ""

# Informazioni finali
IP=$(hostname -I | awk '{print $1}')

echo "==============================================="
echo "  Installazione completata!"
echo "==============================================="

