#!/bin/bash
# WiFi Fallback: Se non riesce a connettersi a internet, diventa hotspot
# Versione corretta che non modifica file di sistema

INTERFACE="wlan0"
HOTSPOT_SSID="videoStreamer"
HOTSPOT_PASSWORD="videostreamer"
HOTSPOT_IP="192.168.50.1"
WAIT_TIME=30
LOG_FILE="/var/log/wifi_fallback.log"

# Funzione per logging
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a $LOG_FILE
}

log "===== WiFi Fallback Avviato ====="

# Attendi che il sistema si stabilizzi
log "Attendo $WAIT_TIME secondi per connessione WiFi..."
sleep $WAIT_TIME

# Verifica connessione internet
log "Verifico connessione internet..."
if ping -c 3 -W 5 8.8.8.8 &>/dev/null; then
    log "✅ Internet raggiungibile - hotspot NON necessario"
    exit 0
fi

log "❌ Nessuna connessione internet - avvio hotspot"

# Ferma NetworkManager per evitare conflitti
log "Fermo NetworkManager..."
systemctl stop NetworkManager 2>/dev/null || true
killall wpa_supplicant 2>/dev/null || true
sleep 2

# Configura interfaccia
log "Configuro interfaccia $INTERFACE..."
ip link set $INTERFACE down
sleep 1
ip link set $INTERFACE up
ip addr flush dev $INTERFACE
ip addr add $HOTSPOT_IP/24 dev $INTERFACE
sleep 2

# Crea configurazione hostapd in /tmp (NON modifica file di sistema!)
log "Creo configurazione hostapd..."
cat > /tmp/hostapd_hotspot.conf <<EOF
interface=$INTERFACE
driver=nl80211
ssid=$HOTSPOT_SSID
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=$HOTSPOT_PASSWORD
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
EOF

# Crea configurazione dnsmasq in /tmp (NON modifica file di sistema!)
log "Creo configurazione dnsmasq..."
cat > /tmp/dnsmasq_hotspot.conf <<EOF
interface=$INTERFACE
dhcp-range=192.168.50.50,192.168.50.150,255.255.255.0,24h
domain=wlan
address=/gw.wlan/$HOTSPOT_IP
EOF

# Ferma dnsmasq di sistema
systemctl stop dnsmasq 2>/dev/null || true

# Avvia hostapd con config temporanea
log "Avvio hostapd..."
/usr/sbin/hostapd -B /tmp/hostapd_hotspot.conf
sleep 3

# Avvia dnsmasq con config temporanea
log "Avvio dnsmasq..."
/usr/sbin/dnsmasq -C /tmp/dnsmasq_hotspot.conf

log "✅ Hotspot attivo!"
log "📡 SSID: $HOTSPOT_SSID"
log "🔐 Password: $HOTSPOT_PASSWORD"
log "🌐 IP: $HOTSPOT_IP"

# Loop infinito per mantenere lo script attivo
log "Loop di monitoraggio attivo..."
while true; do
    sleep 60
    if ! pgrep hostapd > /dev/null; then
        log "⚠️ hostapd morto, riavvio..."
        /usr/sbin/hostapd -B /tmp/hostapd_hotspot.conf
    fi
    if ! pgrep dnsmasq > /dev/null; then
        log "⚠️ dnsmasq morto, riavvio..."
        /usr/sbin/dnsmasq -C /tmp/dnsmasq_hotspot.conf
    fi
done
