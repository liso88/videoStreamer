#!/bin/bash

# Script che fa login, poi chiama /api/service/restart
# Uso: ./restart_rtsp.sh

BASE_URL="http://localhost"
LOG_FILE="/home/tommaso/videoStreamer/logs/rtsp_restart.log"
COOKIES="/tmp/rtsp_cookies.txt"

# Crea la cartella logs se non esiste
mkdir -p /home/tommaso/videoStreamer/logs

# Credenziali
USERNAME="tommaso"
PASSWORD="tommaso"

# Log
echo "[$(date '+%Y-%m-%d %H:%M:%S')] === Riavvio Servizio ===" >> $LOG_FILE

# 1. LOGIN (crea sessione)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Login..." >> $LOG_FILE
curl -s -X POST "$BASE_URL/login" \
    -c "$COOKIES" \
    -d "username=$USERNAME&password=$PASSWORD" \
    > /dev/null 2>&1

sleep 1

# 2. Chiama /api/service/restart (con sessione)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] POST /api/service/restart" >> $LOG_FILE
RESPONSE=$(curl -s -X POST "$BASE_URL/api/service/restart" \
    -b "$COOKIES")
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Risposta: $RESPONSE" >> $LOG_FILE

# Pulisci i cookie
rm -f "$COOKIES"

sleep 2

echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✓ Riavvio completato" >> $LOG_FILE
