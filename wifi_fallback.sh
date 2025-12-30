#!/bin/bash
# WiFi Fallback: Se non riesce a connettersi, diventa hotspot
# Versione corretta che evita conflitti con NetworkManager

set -e

INTERFACE="wlan0"
HOTSPOT_SSID="VideoStreamer"
HOTSPOT_IP="192.168.50.1"
HOTSPOT_PASSWORD="videostreamer123"  # Password per l'hotspot
TIMEOUT_SECONDS=45
LOG_FILE="/var/log/wifi_fallback.log"
LOCK_FILE="/tmp/wifi_fallback.lock"

# Crea directory log se non esiste
mkdir -p "$(dirname $LOG_FILE)"

echo "[$(date)] ===== WiFi Fallback Script Avviato =====" >> $LOG_FILE

# Funzione per log
log_msg() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a $LOG_FILE
}

# Funzione cleanup
cleanup() {
    log_msg "🧹 Cleanup in corso..."
    rm -f $LOCK_FILE
}

trap cleanup EXIT

# Verifica se già in esecuzione
if [ -f "$LOCK_FILE" ]; then
    log_msg "⚠️  Script già in esecuzione. Uscita."
    exit 0
fi

touch $LOCK_FILE

# Verifica che i comandi necessari esistano
if ! command -v hostapd &> /dev/null || ! command -v dnsmasq &> /dev/null; then
    log_msg "❌ hostapd o dnsmasq non installati. Esegui auto_install.sh"
    exit 1
fi

# Verifica che l'interfaccia esista
if ! ip link show $INTERFACE &> /dev/null; then
    log_msg "❌ Interfaccia $INTERFACE non trovata"
    exit 1
fi

# Funzione per controllare la connessione
check_connectivity() {
    # Verifica se l'interfaccia ha un IP valido (non 169.254.x.x)
    local ip=$(ip -4 addr show $INTERFACE | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | grep -v '^169\.254\.')
    
    if [ -n "$ip" ]; then
        log_msg "✅ IP trovato: $ip"
        
        # Verifica connettività internet
        if timeout 5 ping -c 1 -W 3 8.8.8.8 &> /dev/null; then
            log_msg "✅ Connessione internet attiva"
            return 0
        fi
    fi
    
    return 1
}

# Attesa iniziale per permettere a NetworkManager di connettersi
log_msg "⏳ Attendo connessione WiFi per $TIMEOUT_SECONDS secondi..."
sleep 10

# Loop di controllo connessione
for i in $(seq 1 7); do
    log_msg "🔍 Tentativo $i/7: Verifica connessione..."
    
    if check_connectivity; then
        log_msg "✅ WiFi connesso. WiFi Fallback non necessario."
        exit 0
    fi
    
    log_msg "⏳ Nessuna connessione. Attendo ancora..."
    sleep 5
done

# Se arriviamo qui, nessuna connessione: attiva hotspot
log_msg "❌ Nessuna connessione disponibile dopo $TIMEOUT_SECONDS secondi"
log_msg "🔄 Attivazione modalità Hotspot..."

# STOP NetworkManager per evitare conflitti
log_msg "🛑 Disattivazione temporanea NetworkManager..."
systemctl stop NetworkManager 2>/dev/null || log_msg "⚠️  NetworkManager già fermo"

# Aspetta che NetworkManager rilasci l'interfaccia
sleep 3

# Ferma servizi esistenti
log_msg "🛑 Arresto servizi esistenti..."
systemctl stop hostapd 2>/dev/null || true
systemctl stop dnsmasq 2>/dev/null || true
killall hostapd 2>/dev/null || true
killall dnsmasq 2>/dev/null || true

# Aspetta che i processi terminino
sleep 2

# Porta su l'interfaccia
log_msg "🔧 Configurazione interfaccia $INTERFACE..."
ip link set $INTERFACE down
sleep 1
ip link set $INTERFACE up
sleep 2

# Rimuovi IP esistenti
ip addr flush dev $INTERFACE 2>/dev/null || true

# Configura IP statico
log_msg "🔧 Assegnazione IP $HOTSPOT_IP..."
ip addr add $HOTSPOT_IP/24 dev $INTERFACE 2>/dev/null || {
    log_msg "⚠️  IP già assegnato, lo sostituisco..."
    ip addr replace $HOTSPOT_IP/24 dev $INTERFACE
}

# Configura hostapd
log_msg "📝 Creazione configurazione hostapd..."
cat > /tmp/hostapd_fallback.conf <<EOF
interface=$INTERFACE
driver=nl80211
ssid=$HOTSPOT_SSID
hw_mode=g
channel=6
ieee80211n=1
wmm_enabled=1
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=$HOTSPOT_PASSWORD
wpa_key_mgmt=WPA-PSK
wpa_pairwise=CCMP
rsn_pairwise=CCMP
EOF

# Configura dnsmasq
log_msg "📝 Creazione configurazione dnsmasq..."
cat > /tmp/dnsmasq_fallback.conf <<EOF
interface=$INTERFACE
bind-interfaces
dhcp-range=192.168.50.50,192.168.50.150,255.255.255.0,24h
dhcp-option=option:router,$HOTSPOT_IP
dhcp-option=option:dns-server,$HOTSPOT_IP
address=/#/$HOTSPOT_IP
no-resolv
log-queries
log-dhcp
EOF

# Avvia hostapd in background
log_msg "🚀 Avvio hostapd..."
hostapd -B /tmp/hostapd_fallback.conf -P /tmp/hostapd_fallback.pid >> $LOG_FILE 2>&1 &
HOSTAPD_PID=$!

sleep 3

# Verifica che hostapd sia attivo
if ! ps -p $HOSTAPD_PID > /dev/null 2>&1; then
    log_msg "❌ hostapd non si è avviato correttamente"
    log_msg "❌ Log hostapd:"
    tail -20 $LOG_FILE
    
    # Ripristina NetworkManager
    log_msg "🔄 Ripristino NetworkManager..."
    systemctl start NetworkManager
    exit 1
fi

log_msg "✅ hostapd avviato (PID: $HOSTAPD_PID)"

# Avvia dnsmasq
log_msg "🚀 Avvio dnsmasq..."
dnsmasq -C /tmp/dnsmasq_fallback.conf --pid-file=/tmp/dnsmasq_fallback.pid >> $LOG_FILE 2>&1

sleep 2

# Verifica che dnsmasq sia attivo
if ! pgrep -f "dnsmasq.*dnsmasq_fallback" > /dev/null; then
    log_msg "❌ dnsmasq non si è avviato correttamente"
    
    # Ferma hostapd
    kill $HOSTAPD_PID 2>/dev/null || true
    
    # Ripristina NetworkManager
    log_msg "🔄 Ripristino NetworkManager..."
    systemctl start NetworkManager
    exit 1
fi

log_msg "✅ dnsmasq avviato"

# Abilita IP forwarding (opzionale, per condividere eventuale connessione Ethernet)
echo 1 > /proc/sys/net/ipv4/ip_forward 2>/dev/null || true

log_msg ""
log_msg "=� Password: $HOTSPOT_PASSWORD====="
log_msg "✅ HOTSPOT ATTIVO!"
log_msg "============================================"
log_msg "📡 SSID: $HOTSPOT_SSID"
log_msg "🔓 Sicurezza: APERTA (nessuna password)"
log_msg "🌐 Accedi a: http://$HOTSPOT_IP"
log_msg "🌐 Oppure: http://$(hostname).local"
log_msg "============================================"
log_msg ""
log_msg "💡 Per disattivare l'hotspot e riprovare WiFi:"
log_msg "   sudo systemctl restart NetworkManager"
log_msg "   sudo systemctl stop wifi-fallback"
log_msg ""

# Crea file di stato per l'interfaccia web
cat > /tmp/hotspot_active <<EOF
ACTIVE=true
SSID=$HOTSPOT_SSID
IP=$HOTSPOT_IP
STARTED=$(date)
EOF

# ==========================================
# LOOP DI MONITORAGGIO HOTSPOT
# ==========================================
# Mantiene hostapd e dnsmasq attivi
# Verifica ogni 30 secondi che siano ancora in esecuzione

log_msg "🔄 Avvio loop di monitoraggio hotspot..."

while true; do
    sleep 30
    
    # Verifica hostapd
    if ! pgrep -f "hostapd.*hostapd_fallback" > /dev/null; then
        log_msg "⚠️  hostapd è caduto! Riavvio..."
        hostapd -B /tmp/hostapd_fallback.conf -P /tmp/hostapd_fallback.pid >> $LOG_FILE 2>&1 &
        sleep 2
    fi
    
    # Verifica dnsmasq
    if ! pgrep -f "dnsmasq.*dnsmasq_fallback" > /dev/null; then
        log_msg "⚠️  dnsmasq è caduto! Riavvio..."
        dnsmasq -C /tmp/dnsmasq_fallback.conf --pid-file=/tmp/dnsmasq_fallback.pid >> $LOG_FILE 2>&1
        sleep 2
    fi
    
    # Verifica che l'interfaccia sia ancora su
    if ! ip link show $INTERFACE 2>/dev/null | grep -q "UP"; then
        log_msg "⚠️  Interfaccia $INTERFACE down! Reboot..."
        ip link set $INTERFACE up
        sleep 2
    fi
    
done