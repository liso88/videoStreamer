#!/bin/bash
# WiFi Fallback: Se non riesce a connettersi, attiva hotspot con NetworkManager
# Versione NetworkManager nativa - Semplificata e robusta

# NON usare set -e perché alcuni comandi possono fallire normalmente
# set -e

INTERFACE="wlan0"
HOTSPOT_SSID="videoStreamer"
HOTSPOT_IP="192.168.50.1"
HOTSPOT_CONNECTION="Hotspot-Fallback"
WAIT_TIME=30
LOG_FILE="/var/log/wifi_fallback.log"

# Crea log file se non esiste
touch $LOG_FILE 2>/dev/null || LOG_FILE="/tmp/wifi_fallback.log"

# Funzione per log
log_msg() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg" | tee -a $LOG_FILE
}

log_msg "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_msg "  WiFi Fallback Script Avviato"
log_msg "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Verifica che lo script sia eseguito come root
if [ "$EUID" -ne 0 ]; then 
    log_msg "❌ Questo script deve essere eseguito come root"
    exit 1
fi

# Verifica NetworkManager
if ! command -v nmcli &> /dev/null; then
    log_msg "❌ NetworkManager non trovato. Installalo con: sudo apt install network-manager"
    exit 1
fi

# Controlla se l'interfaccia esiste
if ! ip link show $INTERFACE &> /dev/null; then
    log_msg "❌ Interfaccia $INTERFACE non trovata"
    ip link show | grep -E "^[0-9]+" | tee -a $LOG_FILE
    exit 1
fi

log_msg "✅ Interfaccia $INTERFACE trovata"
log_msg "✅ NetworkManager disponibile"

# Funzione per verificare se ci sono connessioni WiFi attive
has_wifi_connection() {
    # Verifica con NetworkManager se c'è una connessione WiFi attiva (escluso hotspot)
    local active=$(nmcli -t -f NAME,TYPE,STATE connection show --active 2>/dev/null | grep "802-11-wireless:activated" | grep -v "$HOTSPOT_CONNECTION" || true)
    if [ -n "$active" ]; then
        return 0
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

# Attendi avvio NetworkManager
log_msg "⏳ Attesa avvio NetworkManager..."
for i in {1..15}; do
    if systemctl is-active --quiet NetworkManager; then
        log_msg "✅ NetworkManager attivo"
        break
    fi
    sleep 1
done

# Attendi connessione WiFi
log_msg "⏳ Attendo connessione WiFi per $WAIT_TIME secondi..."

connected=false
for i in $(seq 1 $WAIT_TIME); do
    # Verifica se connesso via WiFi
    if has_wifi_connection &> /dev/null; then
        log_msg "✅ Rilevata connessione WiFi attiva"
        
        # Verifica anche internet
        if check_internet; then
            log_msg "✅ Internet disponibile. Hotspot non necessario."
            connected=true
            break
        else
            log_msg "⚠️  WiFi connesso ma senza internet (tentativo $i/$WAIT_TIME)"
        fi
    else
        if [ $((i % 10)) -eq 0 ]; then
            log_msg "⏳ Nessuna connessione WiFi (${i}s/${WAIT_TIME}s)"
        fi
    fi
    
    sleep 1
done

# Se connesso, esci
if [ "$connected" = true ]; then
    log_msg "✅ Sistema connesso a WiFi. Script terminato."
    # Rimuovi marker se presente
    rm -f /tmp/hotspot_active
    exit 0
fi

# Se arriviamo qui, non c'è connessione: attiva hotspot
log_msg "❌ Nessuna connessione WiFi disponibile dopo ${WAIT_TIME}s"
log_msg "🚀 Attivazione modalità Hotspot con NetworkManager..."

# Verifica se il profilo hotspot esiste già
if nmcli connection show "$HOTSPOT_CONNECTION" &> /dev/null; then
    log_msg "ℹ️  Profilo hotspot esistente trovato"
    
    # Verifica se è già attivo
    if nmcli -t -f NAME,STATE connection show --active | grep -q "^${HOTSPOT_CONNECTION}:activated$"; then
        log_msg "✅ Hotspot già attivo"
        touch /tmp/hotspot_active
        exit 0
    fi
    
    log_msg "🔄 Attivazione profilo hotspot esistente..."
else
    log_msg "📝 Creazione nuovo profilo hotspot..."
    
    # Crea profilo hotspot con NetworkManager
    if nmcli connection add \
        type wifi \
        ifname $INTERFACE \
        con-name "$HOTSPOT_CONNECTION" \
        autoconnect no \
        ssid "$HOTSPOT_SSID" \
        mode ap \
        802-11-wireless.band bg \
        ipv4.method shared \
        ipv4.addresses $HOTSPOT_IP/24 \
        >> $LOG_FILE 2>&1; then
        log_msg "✅ Profilo hotspot creato con successo"
    else
        log_msg "❌ Errore creazione profilo hotspot"
        tail -n 10 $LOG_FILE
        exit 1
    fi
fi

# Disattiva eventuali connessioni WiFi attive su wlan0
log_msg "🔧 Disattivazione connessioni WiFi esistenti su $INTERFACE..."
active_connections=$(nmcli -t -f NAME,DEVICE connection show --active | grep "$INTERFACE" | cut -d: -f1)
if [ -n "$active_connections" ]; then
    echo "$active_connections" | while read conn; do
        if [ "$conn" != "$HOTSPOT_CONNECTION" ]; then
            log_msg "   Disattivazione: $conn"
            nmcli connection down "$conn" >> $LOG_FILE 2>&1 || true
        fi
    done
    sleep 2
fi

# Attiva l'hotspot
log_msg "🚀 Attivazione hotspot: $HOTSPOT_SSID..."
if nmcli connection up "$HOTSPOT_CONNECTION" >> $LOG_FILE 2>&1; then
    log_msg "✅ Hotspot attivato con successo"
    sleep 3
    
    # IMPORTANTE: Disabilita power management per evitare che la rete sparisca
    log_msg "🔧 Disabilitazione power management su $INTERFACE..."
    if iw dev $INTERFACE set power_save off >> $LOG_FILE 2>&1; then
        log_msg "✅ Power management disabilitato (metodo iw)"
    else
        log_msg "⚠️  Comando iw non riuscito, provo con iwconfig..."
        if iwconfig $INTERFACE power off >> $LOG_FILE 2>&1; then
            log_msg "✅ Power management disabilitato (metodo iwconfig)"
        else
            log_msg "⚠️  Impossibile disabilitare power management"
        fi
    fi
    
    # Verifica stato power management
    if command -v iw &> /dev/null; then
        pm_status=$(iw dev $INTERFACE get power_save 2>/dev/null || echo "N/A")
        log_msg "ℹ️  Power save status: $pm_status"
    fi
    
    # Verifica che sia effettivamente attivo
    if nmcli -t -f NAME,STATE connection show --active | grep -q "^${HOTSPOT_CONNECTION}:activated$"; then
        log_msg "✅ Hotspot verificato e funzionante"
    else
        log_msg "⚠️  Hotspot attivato ma verifica fallita"
    fi
else
    log_msg "❌ Errore attivazione hotspot"
    log_msg "   Log degli ultimi errori:"
    tail -n 20 $LOG_FILE
    exit 1
fi

# Crea file marker per indicare che hotspot è attivo
touch /tmp/hotspot_active
log_msg "✅ Marker hotspot creato: /tmp/hotspot_active"

# Mostra riepilogo finale
log_msg ""
log_msg "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_msg "✅ HOTSPOT WiFi ATTIVO!"
log_msg "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_msg "📡 SSID:     $HOTSPOT_SSID"
log_msg "🔓 Password: NESSUNA (rete aperta)"
log_msg "🌐 IP:       $HOTSPOT_IP"
log_msg "🌐 URL:      http://$HOTSPOT_IP"
log_msg "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_msg ""
log_msg "ℹ️  Puoi ora connetterti alla rete '$HOTSPOT_SSID'"
log_msg "ℹ️  Accedi all'interfaccia web su: http://$HOTSPOT_IP"
log_msg "ℹ️  Usa l'interfaccia per configurare la connessione WiFi"
log_msg ""
log_msg "ℹ️  Per disattivare l'hotspot manualmente:"
log_msg "   sudo nmcli connection down $HOTSPOT_CONNECTION"
log_msg "   sudo rm /tmp/hotspot_active"
log_msg ""
log_msg "⚙️  Per eliminare il profilo hotspot:"
log_msg "   sudo nmcli connection delete $HOTSPOT_CONNECTION"
log_msg ""
log_msg "Script completato con successo"

exit 0