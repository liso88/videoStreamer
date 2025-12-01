#!/bin/bash
# Script di installazione automatica per Raspberry Pi Stream Manager
# Tutto si avvierà automaticamente al boot

set -e

echo "=========================================="
echo "  Raspberry Pi Stream Manager - Setup"
echo "=========================================="
echo ""

# Verifica che lo script sia eseguito come utente normale (non root)
if [ "$EUID" -eq 0 ]; then 
   echo "Non eseguire questo script come root!"
   echo "Usa: bash install.sh"
   exit 1
fi

# Aggiorna sistema
echo "[1/8] Aggiornamento sistema..."
sudo apt update && sudo apt upgrade -y

# Installa dipendenze base
echo "[2/8] Installazione dipendenze..."
sudo apt install -y \
    cmake libjpeg-dev gcc g++ git \
    python3-pip python3-flask \
    ffmpeg v4l-utils \
    nginx

# Installa librerie Python
echo "[3/8] Installazione librerie Python..."
pip3 install flask psutil --break-system-packages

# Compila mjpg-streamer
echo "[4/8] Compilazione mjpg-streamer..."
cd ~
if [ -d "mjpg-streamer" ]; then
    rm -rf mjpg-streamer
fi
git clone https://github.com/jacksonliam/mjpg-streamer.git
cd mjpg-streamer/mjpg-streamer-experimental
make
sudo make install

# Installa MediaMTX
echo "[5/8] Installazione MediaMTX..."
cd ~
ARCH=$(uname -m)
if [ "$ARCH" = "aarch64" ]; then
    MEDIAMTX_ARCH="arm64v8"
else
    MEDIAMTX_ARCH="armv7"
fi

wget -q https://github.com/bluenviron/mediamtx/releases/download/v1.5.0/mediamtx_v1.5.0_linux_${MEDIAMTX_ARCH}.tar.gz
tar -xzf mediamtx_v1.5.0_linux_${MEDIAMTX_ARCH}.tar.gz
sudo mv mediamtx /usr/local/bin/
sudo chmod +x /usr/local/bin/mediamtx
rm mediamtx_v1.5.0_linux_${MEDIAMTX_ARCH}.tar.gz

# Configura MediaMTX
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

# Crea directory per l'applicazione
echo "[7/8] Creazione applicazione web..."
mkdir -p ~/stream_manager
mkdir -p ~/stream_manager/videos
cd ~/stream_manager

# Scarica l'applicazione (devi prima salvare app.py e change_password.py)
# Se hai già app.py nella stessa directory, verrà utilizzato
if [ ! -f "app.py" ]; then
    echo "ATTENZIONE: Copia app.py in ~/stream_manager/"
    echo "Premi INVIO dopo aver copiato il file..."
    read
fi

if [ ! -f "change_password.py" ]; then
    echo "ATTENZIONE: Copia change_password.py in ~/stream_manager/"
    echo "Premi INVIO dopo aver copiato il file..."
    read
fi

chmod +x app.py
chmod +x change_password.py

# Crea servizio systemd per Stream Manager Web Interface
echo "[8/8] Configurazione servizi di avvio automatico..."

sudo tee /etc/systemd/system/stream-manager.service > /dev/null <<EOF
[Unit]
Description=Stream Manager Web Interface
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$HOME/stream_manager
ExecStart=/usr/bin/python3 $HOME/stream_manager/app.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Crea servizio systemd per MediaMTX
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

# Crea configurazione di default per avvio automatico
cat > ~/stream_manager/stream_config.json <<'EOF'
{
  "mjpg": {
    "enabled": true,
    "device": "/dev/video0",
    "resolution": "640x480",
    "framerate": 15,
    "quality": 85,
    "port": 8080,
    "autostart": true
  },
  "rtsp": {
    "enabled": true,
    "device": "/dev/video0",
    "resolution": "640x480",
    "framerate": 25,
    "bitrate": "1000k",
    "port": 8554,
    "autostart": false
  }
}
EOF

# Ricarica systemd e abilita i servizi
sudo systemctl daemon-reload
sudo systemctl enable stream-manager.service
sudo systemctl enable mediamtx.service

# Configura sudo per permettere il riavvio del servizio senza password
echo "[*] Configurazione permessi sudo per riavvio servizio..."
SUDOERS_LINE="$USER ALL=(ALL) NOPASSWD: /bin/systemctl restart stream-manager"
if ! sudo grep -q "$SUDOERS_LINE" /etc/sudoers.d/stream-manager 2>/dev/null; then
    echo "$SUDOERS_LINE" | sudo tee /etc/sudoers.d/stream-manager > /dev/null
    sudo chmod 0440 /etc/sudoers.d/stream-manager
    echo "✅ Permessi sudo configurati"
else
    echo "✅ Permessi sudo già configurati"
fi

# Avvia i servizi
sudo systemctl start stream-manager.service
sudo systemctl start mediamtx.service

# Ottieni l'IP del Raspberry
IP=$(hostname -I | awk '{print $1}')

echo ""
echo "=========================================="
echo "  ✅ Installazione completata!"
echo "=========================================="
echo ""
echo "🔐 CREDENZIALI DEFAULT (CAMBIALE SUBITO!):"
echo "   Username: admin"
echo "   Password: admin"
echo ""
echo "I servizi si avvieranno automaticamente ad ogni avvio."
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
echo "🔑 Per cambiare password da terminale:"
echo "   cd ~/stream_manager"
echo "   python3 change_password.py"
echo ""
echo "🔧 Comandi utili:"
echo "   sudo systemctl status stream-manager  # Stato web interface"
echo "   sudo systemctl status mediamtx        # Stato server RTSP"
echo "   sudo journalctl -u stream-manager -f  # Log web interface"
echo ""
echo "🔄 Per riavviare i servizi:"
echo "   sudo systemctl restart stream-manager"
echo "   sudo systemctl restart mediamtx"
echo ""
echo "⚠️  IMPORTANTE: Cambia la password di default dopo il primo accesso!"
echo ""
echo "Riavvia il Raspberry per testare l'avvio automatico:"
echo "   sudo reboot"
echo ""
