#!/bin/bash
# WiFi Fallback: Se non riesce a connettersi, diventa hotspot
# Questo script viene eseguito al boot tramite systemd

set -e

INTERFACE="wlan0"
HOTSPOT_SSID="videoStreamer"
HOTSPOT_IP="192.168.50.1"
TIMEOUT_SECONDS=30
LOG_FILE="/var/log/wifi_fallback.log"

echo "[$(date)] ===== WiFi Fallback Script Avviato =====" >> $LOG_FILE

# Funzione per log
log_msg() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> $LOG_FILE
    echo "$1"
}

# Aspetta che la rete sia disponibile
log_msg "⏳ Attendo connessione WiFi per $TIMEOUT_SECONDS secondi..."
sleep 5

# Controlla se connesso a internet
check_internet() {
    timeout 5 ping -c 1 8.8.8.8 > /dev/null 2>&1
    return $?
}

# Se connesso, esci
if check_internet; then
    log_msg "✅ Connesso a internet. WiFi Fallback disattivato."
    exit 0
fi

# Conta i tentativi
for i in $(seq 1 $(($TIMEOUT_SECONDS / 5))); do
    log_msg "🔍 Tentativo $i: Ricerca reti WiFi..."
    
    if check_internet; then
        log_msg "✅ Internet disponibile al tentativo $i"
        exit 0
    fi
    
    sleep 5
done

# Se arriviamo qui, non c'è connessione: attiva hotspot
log_msg "❌ Nessuna connessione internet disponibile. Attivazione hotspot..."

# Verifica che hostapd e dnsmasq siano installati
if ! command -v hostapd &> /dev/null; then
    log_msg "❌ hostapd non è installato. Esegui auto_install.sh per installarlo."
    exit 1
fi

if ! command -v dnsmasq &> /dev/null; then
    log_msg "❌ dnsmasq non è installato. Esegui auto_install.sh per installarlo."
    exit 1
fi

# Configura indirizzo IP statico per hotspot
log_msg "🔧 Configurazione indirizzo IP $HOTSPOT_IP..."
sudo ip addr add $HOTSPOT_IP/24 dev $INTERFACE 2>/dev/null || sudo ip addr replace $HOTSPOT_IP/24 dev $INTERFACE

# Crea configurazione hostapd
log_msg "📝 Creazione configurazione hostapd..."
sudo tee /etc/hostapd/hostapd_fallback.conf > /dev/null <<EOF
interface=$INTERFACE
driver=nl80211
ssid=$HOTSPOT_SSID
hw_mode=g
channel=6
wmm_enabled=1
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=0
wpa_key_mgmt=NONE
EOF

# Crea configurazione dnsmasq
log_msg "📝 Creazione configurazione dnsmasq..."
sudo tee /etc/dnsmasq_fallback.conf > /dev/null <<EOF
interface=$INTERFACE
dhcp-range=192.168.50.50,192.168.50.150,255.255.255.0,24h
dhcp-option=option:router,$HOTSPOT_IP
dhcp-option=option:dns-server,8.8.8.8,8.8.4.4
address=/#/$HOTSPOT_IP
EOF

# Avvia hostapd
log_msg "🚀 Avvio hostapd..."
sudo systemctl stop hostapd 2>/dev/null || true
sudo hostapd -B /etc/hostapd/hostapd_fallback.conf

# Avvia dnsmasq
log_msg "🚀 Avvio dnsmasq..."
sudo systemctl stop dnsmasq 2>/dev/null || true
sudo dnsmasq -C /etc/dnsmasq_fallback.conf

log_msg "✅ Hotspot attivato!"
log_msg "📡 SSID: $HOTSPOT_SSID"
log_msg "🔐 Password: $HOTSPOT_PASSWORD"
log_msg "🌐 Accedi a: http://$HOTSPOT_IP"

exit 0
