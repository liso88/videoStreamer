# 🎥 Raspberry Pi Zero 2W - Video Streaming Manager

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi-red.svg)](https://www.raspberrypi.org/)
[![Python](https://img.shields.io/badge/Python-3.7%2B-blue.svg)](https://www.python.org/)

Trasforma il tuo Raspberry Pi Zero 2W in un potente convertitore **Video Analogico → Camera IP** con interfaccia web completa per la gestione degli stream.


## Caratteristiche Principali

- **Dual Streaming**: MJPEG (HTTP) e RTSP (H.264) simultanei o indipendenti
- **Interfaccia Web**: Dashboard moderna e responsive per gestione completa
- **Multi-Source**: Supporto per dispositivi video USB e file video in loop
- **Sicurezza**: Autenticazione integrata con gestione password
- **Avvio Automatico**: Configurazione persistente con boot automatico
- **Monitoraggio**: CPU, memoria e temperatura in tempo reale
- **Video Loop**: Carica video locali per streaming continuo
- **Auto-restart**: Riavvio stream e servizi dall'interfaccia web

## Requisiti Hardware

| Componente | Specifiche |
|------------|------------|
| **Raspberry Pi** | Zero 2W (o superiore) |
| **Adattatore Video** | RCA/Composito to USB (driver UVC)  - oppure webcam |
| **MicroSD** | 16GB minimo, 32GB consigliata (Classe 10) |
| **Connettività** | WiFi integrato o adattatore USB-Ethernet |

## Installazione Rapida

### 1. Prepara il Raspberry Pi

```bash
# Scarica Raspberry Pi OS Lite (64-bit)
# Usa Raspberry Pi Imager per configurare:
# - Username e password
# - WiFi
# - SSH abilitato
```

### 2. Clona il Repository

```bash
git clone https://github.com/liso88/videoStreamer.git
```

### 3. Esegui l'Installazione Automatica

```bash
chmod +x auto_install.sh
./auto_install.sh
```

L'installazione richiede circa **10-15 minuti** e configura automaticamente:
- mjpg-streamer
- FFmpeg
- MediaMTX (server RTSP)
- Flask e dipendenze Python
- Servizi systemd per avvio automatico

### 4. Accedi all'Interfaccia Web

Apri il browser e vai su:
```
http://[IP_RASPBERRY]:5000
```

**Credenziali di default:**
- Username: `admin`
- Password: `admin`

 **IMPORTANTE**: Cambia la password immediatamente dopo il primo accesso!



## Configurazioni Consigliate

### Configurazione Leggera (Consigliata per Pi Zero 2W)
```yaml
MJPG Streamer:
  Risoluzione: 640x480
  Framerate: 15 fps
  Qualità: 85
  Avvio automatico: ✓
  
RTSP: Disattivato
```

### Configurazione Qualità
```yaml
RTSP Stream:
  Risoluzione: 640x480
  Framerate: 25 fps
  Bitrate: 1 Mbps
  Avvio automatico: ✓
  
MJPG: Disattivato
```

### Configurazione Video Loop
```yaml
Sorgente: File Video
Video: demo.mp4 (in ~/stream_manager/videos/)
Loop: Attivo
Risoluzione: 640x480
Framerate: 25 fps
```


### Da Terminale

```bash
# Stato servizi
sudo systemctl status stream-manager
sudo systemctl status mediamtx

# Riavvia servizi
sudo systemctl restart stream-manager
sudo systemctl restart mediamtx

# Log in tempo reale
sudo journalctl -u stream-manager -f

# Ferma/Avvia manualmente
sudo systemctl stop stream-manager
sudo systemctl start stream-manager
```

## Accesso agli Stream

### MJPEG Stream (HTTP)
```
Stream diretto:     http://[IP]:8080/?action=stream
Singola immagine:   http://[IP]:8080/?action=snapshot
Interfaccia:        http://[IP]:8080
```

### RTSP Stream (H.264)
```
URL RTSP: rtsp://[IP]:8554/video
```

**Visualizza con VLC:**
```bash
vlc rtsp://192.168.1.100:8554/video
```

## Integrazione

### MJPEG
```yaml
camera:
  - platform: mjpeg
    name: "Camera Analogica"
    mjpeg_url: http://192.168.1.100:8080/?action=stream
    still_image_url: http://192.168.1.100:8080/?action=snapshot
```

### RTSP (FFmpeg)
```yaml
camera:
  - platform: ffmpeg
    name: "Camera Analogica RTSP"
    input: rtsp://192.168.1.100:8554/video
```

## Funzionalità Video Loop

### Da Terminale
```bash
# Crea directory video
mkdir -p ~/stream_manager/videos

# Copia o scarica video
cp mio_video.mp4 ~/stream_manager/videos/

# Crea video di test con FFmpeg
ffmpeg -f lavfi -i testsrc=duration=10:size=640x480:rate=25 \
       -f lavfi -i sine=frequency=1000:duration=10 \
       ~/stream_manager/videos/test_pattern.mp4
```

## Password

### Cambio Password

**Da Interfaccia Web:**
1. Clicca su "⚙️ Impostazioni"
2. Inserisci nuova password
3. Salva e rieffettua il login

**Da Terminale:**
```bash
cd ~/stream_manager
python3 change_password.py
```

### Reset Password Dimenticata
```bash
cd ~/stream_manager
cat > stream_auth.json <<EOF
{
  "username": "admin",
  "password": "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918",
  "enabled": true
}
EOF
sudo systemctl restart stream-manager
```

## Risoluzione Problemi

### Interfaccia Web Non Risponde
```bash
# Verifica stato servizio
sudo systemctl status stream-manager

# Controlla log
sudo journalctl -u stream-manager -n 50

# Riavvia servizio
sudo systemctl restart stream-manager
```

### Dispositivo Video Non Rilevato
```bash
# Verifica dispositivi
ls -l /dev/video*
v4l2-ctl --list-devices

# Verifica USB
lsusb
dmesg | grep video
```


### Stream Si Interrompe
- Verifica alimentazione (usa alimentatore ufficiale 5V 2.5A)
- Controlla memoria: `free -h`
- Verifica log: `sudo journalctl -u stream-manager -f`

Per altri problemi, consulta la [Guida Completa](DOCUMENTATION.md#risoluzione-problemi).



## Backup e Ripristino

### Backup Configurazione
```bash
# Backup file configurazione
mkdir -p ~/backup
cp ~/stream_config.json ~/backup/
cp ~/stream_auth.json ~/backup/

# Copia sul PC
scp user@raspberry:/home/user/backup/*.json ./
```

### Backup Completo SD Card
```bash
# Da PC con lettore SD (Linux/Mac)
sudo dd if=/dev/sdb of=raspberry_backup.img bs=4M status=progress
gzip raspberry_backup.img
```

### Ripristino
```bash
# Copia configurazione sul Raspberry
scp backup/*.json user@raspberry:~/

# Riavvia servizio
ssh user@raspberry "sudo systemctl restart stream-manager"
```



## Porte Utilizzate:
- 5000: Interfaccia web (Flask)
- 8080: Stream MJPEG (mjpg-streamer)
- 8554: Stream RTSP (MediaMTX)
- 8000: RTP (MediaMTX)
- 8001: RTCP (MediaMTX)

**Credenziali Default:**
- Username: `admin`
- Password: `admin`
- ⚠️ **Cambiarle immediatamente dopo il primo accesso!**

## Licenza

Questo progetto è rilasciato sotto licenza MIT - vedi il file [LICENSE](LICENSE) per dettagli.

---

## 📋 Changelog


### Version v1.20251130.

- Configurazione persistente (JSON)
- Supporto file video come sorgente stream
- Selezione sorgente per MJPG e RTSP indipendenti
- Riavvio stream singoli (MJPG/RTSP)
- Riavvio completo servizio stream-manager

**Bug Fix:**
- Risolto problema path hardcoded con username 'pi'
- Risolto caricamento configurazione al boot


### Version v1.20251128 (Rilascio Iniziale).

**Funzionalità:**
- Streaming MJPEG su HTTP (mjpg-streamer)
- Streaming RTSP con codec H.264 (FFmpeg + MediaMTX)
- Interfaccia web
- Autenticazione con login (username/password)
- Dashboard con monitoraggio sistema (CPU, RAM, temperatura)
- Gestione dispositivi video USB (compatibili UVC)
- Avvio/Stop stream da interfaccia web
- Sistema di autenticazione con password hash (SHA-256)

**Configurazione:**
- Avvio automatico configurabile per stream
- Gestione porte personalizzabili
- Parametri video regolabili (risoluzione, framerate, qualità, bitrate)
- Supporto username dinamici (non solo 'pi')


---
**Autore:** Tommaso  
**Data Rilascio:** 30 Novembre 2024  
**Versione:** 1.0 (Tommaso v1.20251130)

