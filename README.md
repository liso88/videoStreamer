# Raspberry Pi Zero 2W - Video Streaming Manager

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi-red.svg)](https://www.raspberrypi.org/)
[![Python](https://img.shields.io/badge/Python-3.7%2B-blue.svg)](https://www.python.org/)

Trasforma il tuo Raspberry Pi Zero 2W in un convertitore **Video Analogico → Camera IP** con interfaccia web completa per la gestione degli stream.



## Caratteristiche Principali

- **Dual Streaming**: MJPEG (HTTP) e RTSP (H.264) simultanei o indipendenti
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
http://[IP_RASPBERRY]
```

**Credenziali di default:**
- Username: `admin`
- Password: `admin`

 **IMPORTANTE**: Cambia la password immediatamente dopo il primo accesso!



### 5. Modalità Access Point (WiFi Hotspot)

Il dispositivo include una **modalità hotspot WiFi automatica**: se non riesce a connettersi a una rete WiFi entro 30 secondi dal boot, attiva automaticamente un access point WiFi aperto (senza password) per consentire l'accesso all'interfaccia di configurazione.

- **SSID**: `videoStreamer` (rete WiFi aperta, nessuna password)
- **IP Hotspot**: `192.168.50.1`
- **Accesso**: Connettiti a `videoStreamer` e apri `http://192.168.50.1` nel browser

Questo permette di configurare la rete WiFi anche se il dispositivo non ha accesso alla rete locale.



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
**Con autenticazione (abilitata di default):**
```
URL RTSP autenticato: rtsp://stream:stream@[IP]:8554/video
```

**Visualizza con VLC:**
```bash
vlc rtsp://192.168.1.100:8554/video
```

**Visualizza con VLC:**

```bash

# Con autenticazione

vlc rtsp://stream:stream@192.168.1.100:8554/video


# Oppure VLC richiederà le credenziali automaticamente

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
| Porta | Servizio | Descrizione |
|-------|----------|-------------|
| 80 | Nginx (Reverse Proxy) | Accesso web all'interfaccia principale |
| 8090 | Flask Backend | API e logica applicativa |
| 8080 | MJPG Streamer | Stream video MJPEG (motion JPEG) |
| 8554 | MediaMTX (RTSP) | Stream video RTSP (Real Time Streaming Protocol) |
| 8888 | MediaMTX HLS | Stream HLS (HTTP Live Streaming) opzionale |
| 22 | SSH | Accesso remoto via terminale |

**Credenziali Default:**
- Username: `admin`
- Password: `admin`
- **Cambiarle immediatamente dopo il primo accesso!**


## Mettere su porta 80

Configura Nginx come reverse proxy su porta 80

Crea un nuovo file di configurazione, ad esempio:
```bash
sudo nano /etc/nginx/sites-available/stream-manager
```

Metti dentro:

```bash
server {
    listen 80;
    listen [::]:80;

    server_name _;

    # Se vuoi servire qualcosa tipo /, puntiamo a Flask
    location / {
        proxy_pass http://127.0.0.1:8090;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

```
Salva e chiudi.

Poi abilita il sito e disabilita il default (opzionale ma consigliato):

```bash
sudo ln -s /etc/nginx/sites-available/stream-manager /etc/nginx/sites-enabled/stream-manager
sudo rm /etc/nginx/sites-enabled/default  # se non ti serve
```

Controlla che la configurazione sia ok:

```bash
sudo nginx -t

sudo systemctl reload nginx
```


## Licenza

Questo progetto è rilasciato sotto licenza MIT - vedi il file [LICENSE](LICENSE) per dettagli.

---

## Changelog

### Version  v2.20251231 
- Auto port 80
- cleaned code stream
- Improved Hotspot modality

### Version  v2.20251208 

- Modalità Access Point
- Riavvio Dispositivo
- Fix cambio password
- Fix selezione rete
- Fix autoinstall
- Rimozione funzioni obsolete
- Fix Sovrapposizione porte
  
### Version  v1.20251203 - Security Update 

- Autenticazione stream MJPEG con HTTP Basic
- Autenticazione stream RTSP con MediaMTX
- Gestione credenziali dall'interfaccia web
- Protezione abilitata di default

### Version v1.20251130.

- Configurazione persistente (JSON)
- Supporto file video come sorgente stream
- Selezione sorgente per MJPG e RTSP indipendenti
- Riavvio stream singoli (MJPG/RTSP)
- Riavvio completo servizio stream-manager
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


