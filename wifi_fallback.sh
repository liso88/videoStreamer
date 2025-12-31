#!/bin/bash
# WiFi Fallback: Se non riesce a connettersi, diventa hotspot
# Versione corretta completa - Sostituisce il file originale

set -e

INTERFACE="wlan0"
HOTSPOT_SSID="videoStreamer"
HOTSPOT_IP="192.168.50.1"
WAIT_TIME=30
LOG_FILE="/var/log/wifi_fallback.log"

# Crea log file se non esiste
touch $LOG_FILE 2>/dev/null || LOG_FILE="/tmp/wifi_fallback.log"

# Funzione per log
log_msg() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg" | tee -a $LOG_FILE
}

log_msg "===== WiFi Fallback Script Avviato ====="

# Verifica che lo script sia eseguito come root
if [ "$EUID" -ne 0 ]; then 
    log_msg "❌ Questo script deve essere eseguito come root"
    exit 1
fi

# Controlla se l'interfaccia esiste
if ! ip link show $INTERFACE &> /dev/null; then
    log_msg "❌ Interfaccia $INTERFACE non trovata"
    ip link show | grep -E "^[0-9]+" | tee -a $LOG_FILE
    exit 1
fi

log_msg "✅ Interfaccia $INTERFACE trovata"

# Funzione per verificare se ci sono connessioni WiFi attive
has_wifi_connections() {
    # Verifica se wlan0 ha un IP e una connessione attiva
    if ip addr show $INTERFACE | grep -q "inet "; then
        return 0
    fi
    
    # Verifica con NetworkManager
    if command -v nmcli &> /dev/null; then
        if nmcli -t -f TYPE,STATE connection show --active 2>/dev/null | grep -q "802-11-wireless:activated"; then
            return 0
        fi
    fi
    
    return 1
}

# Funzione per verificare connettività internet
check_internet() {
    # Prova prima con Google DNS
    if timeout 3 ping -c 1 -W 1 8.8.8.8 &> /dev/null; then
        return 0
    fi
    
    # Prova con Cloudflare
    if timeout 3 ping -c 1 -W 1 1.1.1.1 &> /dev/null; then
        return 0
    fi
    
    return 1
}

# Aspetta che NetworkManager si avvii (se presente)
if command -v nmcli &> /dev/null; then
    log_msg "⏳ Attesa avvio NetworkManager..."
    for i in {1..15}; do
        if systemctl is-active --quiet NetworkManager; then
            log_msg "✅ NetworkManager attivo"
            break
        fi
        sleep 1
    done
fi

# Attendi connessione WiFi
log_msg "⏳ Attendo connessione WiFi per $WAIT_TIME secondi..."

connected=false
for i in $(seq 1 $WAIT_TIME); do
    # Verifica se connesso via WiFi
    if has_wifi_connections; then
        log_msg "✅ Rilevata connessione WiFi attiva"
        
        # Verifica anche internet
        if check_internet; then
            log_msg "✅ Internet disponibile. Hotspot non necessario."
            connected=true
            break
        else
            log_msg "⚠️  WiFi connesso ma no internet (tentativo $i/$WAIT_TIME)"
        fi
    else
        if [ $((i % 5)) -eq 0 ]; then
            log_msg "⏳ Nessuna connessione WiFi (${i}s/${WAIT_TIME}s)"
        fi
    fi
    
    sleep 1
done

# Se connesso, esci
if [ "$connected" = true ]; then
    log_msg "✅ Connessione stabile. Script terminato."
    exit 0
fi

# Se arriviamo qui, non c'è connessione: attiva hotspot
log_msg "❌ Timeout: Nessuna connessione WiFi disponibile"
log_msg "🚀 Attivazione modalità Hotspot..."

# Verifica dipendenze
if ! command -v hostapd &> /dev/null; then
    log_msg "❌ ERRORE: hostapd non installato"
    log_msg "   Installa con: sudo apt install hostapd"
    exit 1
fi

if ! command -v dnsmasq &> /dev/null; then
    log_msg "❌ ERRORE: dnsmasq non installato"
    log_msg "   Installa con: sudo apt install dnsmasq"
    exit 1
fi

log_msg "✅ Dipendenze verificate (hostapd, dnsmasq)"

# Ferma eventuali istanze precedenti
log_msg "🛑 Pulizia processi precedenti..."
killall hostapd 2>/dev/null || true
killall dnsmasq 2>/dev/null || true
sleep 2

# Disabilita gestione NetworkManager su wlan0 (se presente)
if command -v nmcli &> /dev/null; then
    log_msg "🔧 Disattivazione gestione NetworkManager su $INTERFACE..."
    nmcli device set $INTERFACE managed no 2>/dev/null || true
    sleep 2
fi

# Porta su l'interfaccia
log_msg "🔧 Attivazione interfaccia $INTERFACE..."
ip link set $INTERFACE down 2>/dev/null || true
sleep 1
ip link set $INTERFACE up 2>/dev/null || true
sleep 2

# Rimuovi eventuali IP precedenti
log_msg "🔧 Pulizia configurazione IP precedente..."
ip addr flush dev $INTERFACE 2>/dev/null || true

# Configura indirizzo IP statico per hotspot
log_msg "🔧 Configurazione indirizzo IP $HOTSPOT_IP/24..."
if ip addr add ${HOTSPOT_IP}/24 dev $INTERFACE 2>&1 | tee -a $LOG_FILE; then
    log_msg "✅ Indirizzo IP configurato"
else
    log_msg "⚠️  Indirizzo IP già presente o errore"
fi

# Verifica configurazione IP
ip addr show $INTERFACE | grep inet | tee -a $LOG_FILE

# Crea directory per configurazioni
mkdir -p /etc/hostapd 2>/dev/null || true

# Crea configurazione hostapd
log_msg "📝 Creazione configurazione hostapd..."
cat > /etc/hostapd/hostapd_fallback.conf <<EOF
interface=$INTERFACE
driver=nl80211
ssid=$HOTSPOT_SSID
hw_mode=g
channel=6
wmm_enabled=1
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
# Rete aperta (nessuna password)
EOF

if [ -f /etc/hostapd/hostapd_fallback.conf ]; then
    log_msg "✅ File hostapd_fallback.conf creato"
    cat /etc/hostapd/hostapd_fallback.conf | tee -a $LOG_FILE
else
    log_msg "❌ Errore creazione hostapd_fallback.conf"
    exit 1
fi

# Crea configurazione dnsmasq
log_msg "📝 Creazione configurazione dnsmasq..."
cat > /etc/dnsmasq_fallback.conf <<EOF
interface=$INTERFACE
bind-interfaces
dhcp-range=192.168.50.50,192.168.50.150,255.255.255.0,24h
dhcp-option=option:router,$HOTSPOT_IP
dhcp-option=option:dns-server,$HOTSPOT_IP,8.8.8.8
address=/#/$HOTSPOT_IP
no-hosts
log-queries
log-dhcp
EOF

if [ -f /etc/dnsmasq_fallback.conf ]; then
    log_msg "✅ File dnsmasq_fallback.conf creato"
    cat /etc/dnsmasq_fallback.conf | tee -a $LOG_FILE
else
    log_msg "❌ Errore creazione dnsmasq_fallback.conf"
    exit 1
fi

# Avvia hostapd
log_msg "🚀 Avvio hostapd..."
log_msg "   Comando: hostapd -B /etc/hostapd/hostapd_fallback.conf"

if hostapd -B /etc/hostapd/hostapd_fallback.conf >> $LOG_FILE 2>&1; then
    log_msg "✅ hostapd avviato con successo"
    sleep 3
    
    # Verifica che il processo sia attivo
    if pgrep -x hostapd > /dev/null; then
        log_msg "✅ Processo hostapd in esecuzione (PID: $(pgrep -x hostapd))"
    else
        log_msg "❌ hostapd non è in esecuzione!"
        log_msg "   Log hostapd:"
        tail -n 20 $LOG_FILE
        exit 1
    fi
else
    log_msg "❌ Errore avvio hostapd"
    log_msg "   Log degli ultimi errori:"
    tail -n 20 $LOG_FILE
    
    # Ripristina NetworkManager
    if command -v nmcli &> /dev/null; then
        nmcli device set $INTERFACE managed yes 2>/dev/null || true
    fi
    exit 1
fi

# Avvia dnsmasq
log_msg "🚀 Avvio dnsmasq..."
log_msg "   Comando: dnsmasq -C /etc/dnsmasq_fallback.conf"

if dnsmasq -C /etc/dnsmasq_fallback.conf >> $LOG_FILE 2>&1; then
    log_msg "✅ dnsmasq avviato con successo"
    sleep 2
    
    # Verifica che il processo sia attivo
    if pgrep -x dnsmasq > /dev/null; then
        log_msg "✅ Processo dnsmasq in esecuzione (PID: $(pgrep -x dnsmasq))"
    else
        log_msg "❌ dnsmasq non è in esecuzione!"
        killall hostapd 2>/dev/null || true
        exit 1
    fi
else
    log_msg "❌ Errore avvio dnsmasq"
    log_msg "   Log degli ultimi errori:"
    tail -n 20 $LOG_FILE
    
    # Ferma hostapd e ripristina
    killall hostapd 2>/dev/null || true
    if command -v nmcli &> /dev/null; then
        nmcli device set $INTERFACE managed yes 2>/dev/null || true
    fi
    exit 1
fi

# Abilita IP forwarding (opzionale, per condivisione internet via eth0)
log_msg "🔧 Abilitazione IP forwarding..."
echo 1 > /proc/sys/net/ipv4/ip_forward 2>/dev/null || true

# Crea file marker per indicare che hotspot è attivo
touch /tmp/hotspot_active
log_msg "✅ Marker hotspot creato: /tmp/hotspot_active"

# Mostra riepilogo finale
log_msg ""
log_msg "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_msg "✅ HOTSPOT WiFi ATTIVO E FUNZIONANTE!"
log_msg "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_msg "📡 SSID:     $HOTSPOT_SSID"
log_msg "🔓 Password: NESSUNA (rete aperta)"
log_msg "🌐 IP:       $HOTSPOT_IP"
log_msg "🌐 URL:      http://$HOTSPOT_IP"
log_msg "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_msg ""
log_msg "ℹ️  Per disattivare l'hotspot:"
log_msg "   sudo killall hostapd dnsmasq"
log_msg "   sudo nmcli device set wlan0 managed yes"
log_msg "   sudo rm /tmp/hotspot_active"
log_msg ""
log_msg "Script completato con successo"

exit 0