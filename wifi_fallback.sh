#!/bin/bash
# WiFi Fallback: Se non connesso a una WiFi nota, diventa hotspot
# Questo script viene eseguito al boot tramite systemd

set -e
set -o pipefail

# Verifica che lo script sia eseguito con privilegi root
if [ "$EUID" -ne 0 ]; then 
    echo "⚠️  Questo script richiede privilegi root. Esecuzione in corso..."
    exec sudo bash "$0"
fi

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

# Funzione per gestire errori
handle_error() {
    log_msg "❌ ERRORE: $1"
    exit 1
}

# Aspetta che la rete sia disponibile
log_msg "⏳ Attendo connessione WiFi per $TIMEOUT_SECONDS secondi..."
sleep 5

# Controlla se connesso a una WiFi nota (ha indirizzo IP valido)
check_wifi_connected() {
    # Verifica se wlan0 ha un indirizzo IP (diverso dal nostro hotspot IP)
    IP=$(ip addr show $INTERFACE 2>/dev/null | grep "inet " | awk '{print $2}' | cut -d/ -f1 | grep -v "^$")
    
    if [ -z "$IP" ]; then
        return 1  # No IP assigned
    fi
    
    # Se ha l'IP dell'hotspot, non è connesso a una WiFi nota
    if [ "$IP" = "$HOTSPOT_IP" ]; then
        return 1
    fi
    
    return 0  # Ha un IP valido, è connesso
}

# Se connesso a WiFi nota, esci
if check_wifi_connected; then
    IP=$(ip addr show $INTERFACE 2>/dev/null | grep "inet " | awk '{print $2}' | cut -d/ -f1)
    log_msg "✅ Connesso a WiFi nota (IP: $IP). WiFi Fallback disattivato."
    exit 0
fi

# Conta i tentativi
for i in $(seq 1 $(($TIMEOUT_SECONDS / 5))); do
    log_msg "🔍 Tentativo $i: Ricerca connessione WiFi..."
    
    if check_wifi_connected; then
        IP=$(ip addr show $INTERFACE 2>/dev/null | grep "inet " | awk '{print $2}' | cut -d/ -f1)
        log_msg "✅ WiFi connesso al tentativo $i (IP: $IP)"
        exit 0
    fi
    
    sleep 5
done

# Se arriviamo qui, non c'è connessione WiFi: attiva hotspot
log_msg "❌ Nessuna connessione WiFi nota disponibile. Attivazione hotspot..."

# Verifica che hostapd e dnsmasq siano installati
if ! command -v hostapd &> /dev/null; then
    handle_error "hostapd non è installato. Esegui auto_install.sh per installarlo."
fi

if ! command -v dnsmasq &> /dev/null; then
    handle_error "dnsmasq non è installato. Esegui auto_install.sh per installarlo."
fi

# Pulisci interfaccia da configurazioni precedenti
log_msg "🧹 Pulizia interfaccia $INTERFACE..."
ip addr flush dev $INTERFACE 2>/dev/null || true
ip link set $INTERFACE down 2>/dev/null || true
sleep 1
ip link set $INTERFACE up 2>/dev/null || true
sleep 1

# Configura indirizzo IP statico per hotspot
log_msg "🔧 Configurazione indirizzo IP $HOTSPOT_IP..."
ip addr add $HOTSPOT_IP/24 dev $INTERFACE 2>/dev/null || {
    log_msg "⚠️  Tentativo di replace indirizzo IP..."
    ip addr replace $HOTSPOT_IP/24 dev $INTERFACE
}
# Crea configurazione hostapd
log_msg "📝 Creazione configurazione hostapd..."
tee /etc/hostapd/hostapd_fallback.conf > /dev/null <<EOF
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
tee /etc/dnsmasq_fallback.conf > /dev/null <<EOF
interface=$INTERFACE
dhcp-range=192.168.50.50,192.168.50.150,255.255.255.0,24h
dhcp-option=option:router,$HOTSPOT_IP
dhcp-option=option:dns-server,8.8.8.8,8.8.4.4
address=/#/$HOTSPOT_IP
EOF

# Verifica e configura il modulo wireless
log_msg "🔍 Verifica modulo wireless..."
if ! ip link show $INTERFACE > /dev/null 2>&1; then
    handle_error "Interfaccia $INTERFACE non trovata!"
fi

# Avvia hostapd
log_msg "🚀 Avvio hostapd..."
systemctl stop hostapd 2>/dev/null || true
systemctl stop dnsmasq 2>/dev/null || true
sleep 1

if ! hostapd -B /etc/hostapd/hostapd_fallback.conf; then
    handle_error "Errore avvio hostapd. Verifica configurazione."
fi
log_msg "✅ hostapd avviato"

sleep 1

# Avvia dnsmasq
log_msg "🚀 Avvio dnsmasq..."
if ! dnsmasq -C /etc/dnsmasq_fallback.conf; then
    handle_error "Errore avvio dnsmasq. Verifica configurazione."
fi
log_msg "✅ Hotspot attivato con successo!"
log_msg "📡 SSID: $HOTSPOT_SSID"
log_msg "🌐 Accedi a: http://$HOTSPOT_IP"
log_msg "📋 Log disponibile in: $LOG_FILE"

exit 0
