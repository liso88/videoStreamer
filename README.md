# Raspberry Pi Zero 2W – Convertitore Video Analogico → Camera IP  
Guida Completa di Installazione e Configurazione

## 📑 Indice (GitHub Friendly)

- [1. Hardware Necessario](#1-hardware-necessario)
- [2. Preparazione Sistema](#2-preparazione-sistema)
- [3. Installazione Automatica](#3-installazione-automatica)
- [4. Primo Accesso e Configurazione](#4-primo-accesso-e-configurazione)
- [5. Gestione Password e Sicurezza](#5-gestione-password-e-sicurezza)
- [6. Configurazione Avvio Automatico](#6-configurazione-avvio-automatico)
- [7. Utilizzo dell'Interfaccia Web](#7-utilizzo-dellinterfaccia-web)
- [8. Accesso agli Stream](#8-accesso-agli-stream)
- [9. Comandi Utili](#9-comandi-utili)
- [10. Risoluzione Problemi](#10-risoluzione-problemi)
- [11. Backup e Ripristino](#11-backup-e-ripristino)
- [Configurazioni Consigliate](#configurazioni-consigliate)
- [Supporto e Risorse](#supporto-e-risorse)
- [Changelog e Note Versione](#changelog-e-note-versione)

---

================================================================================

INDICE
------
1. Hardware Necessario
2. Preparazione Sistema
3. Installazione Automatica
4. Primo Accesso e Configurazione
5. Gestione Password e Sicurezza
6. Configurazione Avvio Automatico
7. Utilizzo dell'Interfaccia Web
8. Accesso agli Stream
9. Comandi Utili
10. Risoluzione Problemi
11. Backup e Ripristino

================================================================================
1. HARDWARE NECESSARIO
================================================================================

- Raspberry Pi Zero 2W
- Adattatore Video USB (RCA/Composito to USB)
- MicroSD Card (minimo 16GB, consigliata 32GB Classe 10)
- Alimentatore ufficiale Raspberry Pi (5V 2.5A)
- Cavo micro-USB per alimentazione
- Connessione WiFi o adattatore USB-Ethernet (opzionale)

================================================================================
2. PREPARAZIONE SISTEMA
================================================================================

2.1 INSTALLAZIONE RASPBERRY PI OS
----------------------------------
1. Scarica Raspberry Pi Imager da: https://www.raspberrypi.com/software/
2. Installa Raspberry Pi OS Lite (64-bit) sulla microSD
3. Durante l'installazione configura:
   - Nome utente: pi
   - Password: (scegli una password)
   - WiFi: inserisci SSID e password
   - Abilita SSH

2.2 PRIMO AVVIO
---------------
1. Inserisci la microSD nel Raspberry Pi
2. Collega l'adattatore video USB
3. Accendi il Raspberry Pi
4. Trova l'indirizzo IP del Raspberry:
   - Dal router
   - Oppure usa: sudo nmap -sn 192.168.1.0/24

2.3 CONNESSIONE SSH
-------------------
Da terminale (Linux/Mac) o PowerShell (Windows):

    ssh [TUO_USERNAME]@[IP_RASPBERRY]

Esempio: ssh tommaso@192.168.1.100

NOTA: Sostituisci [TUO_USERNAME] con l'username che hai configurato
durante l'installazione di Raspberry Pi OS (es. pi, tommaso, etc.)

================================================================================
3. INSTALLAZIONE AUTOMATICA
================================================================================

3.1 PREPARAZIONE FILE
---------------------
Sul tuo computer, crea una cartella e salva questi 3 file:
- install.sh          (script di installazione)
- app.py              (applicazione web)
- change_password.py  (utility cambio password)

3.2 COPIA FILE SUL RASPBERRY
----------------------------
Opzione A - Da terminale Linux/Mac:

    scp install.sh app.py change_password.py [TUO_USERNAME]@[IP_RASPBERRY]:~/

Opzione B - Da Windows (PowerShell):

    scp install.sh app.py change_password.py [TUO_USERNAME]@[IP_RASPBERRY]:/home/[TUO_USERNAME]/

Opzione C - Con WinSCP (Windows):
1. Apri WinSCP
2. Connetti a: sftp://[IP_RASPBERRY]
3. Username: [TUO_USERNAME], Password: (tua password)
4. Copia i 3 file nella tua home directory

NOTA: Sostituisci [TUO_USERNAME] con il tuo username effettivo

3.3 ESECUZIONE INSTALLAZIONE
-----------------------------
Connettiti via SSH e esegui:

    cd ~
    chmod +x install.sh
    bash install.sh

Lo script installerà automaticamente:
- mjpg-streamer (streaming MJPEG)
- FFmpeg (conversione video)
- MediaMTX (server RTSP)
- Flask e dipendenze Python
- Interfaccia web di gestione
- Servizi systemd per avvio automatico

Tempo stimato: 10-15 minuti

3.4 VERIFICA INSTALLAZIONE
---------------------------
Controlla che i servizi siano attivi:

    sudo systemctl status stream-manager
    sudo systemctl status mediamtx

Dovresti vedere: "active (running)" per entrambi.

================================================================================
4. PRIMO ACCESSO E CONFIGURAZIONE
================================================================================

4.1 ACCESSO ALL'INTERFACCIA WEB
--------------------------------
1. Apri il browser
2. Vai su: http://[IP_RASPBERRY]:5000
3. Login con credenziali di default:
   - Username: admin
   - Password: admin

⚠️ IMPORTANTE: CAMBIA IMMEDIATAMENTE LA PASSWORD!

4.2 CAMBIO PASSWORD (METODO WEB)
---------------------------------
1. Clicca su "⚙️ Impostazioni" in alto a destra
2. Compila i campi:
   - Nuovo Username: (opzionale, lascia vuoto per mantenere "admin")
   - Nuova Password: (scegli una password forte)
   - Conferma Password: (ripeti la password)
3. Clicca "💾 Salva Impostazioni"
4. Verrai disconnesso automaticamente
5. Effettua nuovamente il login con le nuove credenziali

4.3 VERIFICA DISPOSITIVO VIDEO
-------------------------------
Nell'interfaccia web, controlla che venga rilevato /dev/video0
Se non viene rilevato:

    ssh [TUO_USERNAME]@[IP_RASPBERRY]
    ls -l /dev/video*
    v4l2-ctl --list-devices

Se il dispositivo ha un numero diverso (es. /dev/video1), 
selezionalo dal menu a tendina nell'interfaccia.

================================================================================
5. GESTIONE PASSWORD E SICUREZZA
================================================================================

5.1 CAMBIO PASSWORD DA TERMINALE
---------------------------------
Connettiti via SSH:

    cd ~/stream_manager
    python3 change_password.py

Segui le istruzioni a schermo per:
- Cambiare username
- Cambiare password
- Abilitare/disabilitare autenticazione

Dopo il cambio, riavvia il servizio:

    sudo systemctl restart stream-manager

5.2 RESET PASSWORD DIMENTICATA
-------------------------------
Se dimentichi la password, ricrea le credenziali di default:

    cd ~/stream_manager
    cat > stream_auth.json <<EOF
    {
      "username": "admin",
      "password": "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918",
      "enabled": true
    }
    EOF
    sudo systemctl restart stream-manager

Poi accedi con admin/admin e cambia subito la password.

5.3 RACCOMANDAZIONI SICUREZZA
------------------------------
✓ Usa password di almeno 12 caratteri
✓ Mix di maiuscole, minuscole, numeri e simboli
✓ Non usare parole del dizionario
✓ Non condividere le credenziali
✓ Fai backup del file stream_auth.json
✗ Non disabilitare l'autenticazione
✗ Non esporre l'interfaccia direttamente su Internet

================================================================================
6. CONFIGURAZIONE AVVIO AUTOMATICO
================================================================================

6.1 CONFIGURAZIONE MJPG STREAMER
---------------------------------
1. Accedi all'interfaccia web
2. Sezione "MJPG Streamer":
   - Dispositivo Video: /dev/video0
   - Risoluzione: 640x480 (consigliata per Pi Zero 2W)
   - Framerate: 15 fps
   - Qualità: 85
   - Porta HTTP: 8080
   - ✓ Spunta "Avvio automatico al boot"
3. Clicca "💾 Salva Config"

6.2 CONFIGURAZIONE RTSP STREAM
-------------------------------
1. Sezione "RTSP Stream (FFmpeg)":
   - Dispositivo Video: /dev/video0
   - Risoluzione: 640x480
   - Framerate: 25 fps
   - Bitrate: 1000k (1 Mbps)
   - Porta RTSP: 8554
   - ✓ Spunta "Avvio automatico al boot" (opzionale)
3. Clicca "💾 Salva Config"

⚠️ IMPORTANTE: Sul Pi Zero 2W evita di avviare MJPG e RTSP contemporaneamente
per non sovraccaricare la CPU. Scegli uno solo per l'avvio automatico.

6.3 TEST AVVIO AUTOMATICO
--------------------------
Riavvia il Raspberry per testare:

    sudo reboot

Dopo il riavvio (circa 30-40 secondi):
1. L'interfaccia web sarà disponibile su porta 5000
2. Gli stream configurati si avvieranno automaticamente
3. Verifica lo stato dall'interfaccia web

================================================================================
7. UTILIZZO DELL'INTERFACCIA WEB
================================================================================

7.1 DASHBOARD
-------------
Mostra in tempo reale:
- Stato CPU (%)
- Utilizzo Memoria (%)
- Temperatura (°C)
- Stato MJPG Streamer (In Esecuzione / Fermo)
- Stato RTSP Stream (In Esecuzione / Fermo)

7.2 GESTIONE MJPG STREAMER
---------------------------
Pulsanti disponibili:
- ▶ Avvia: Avvia lo streaming MJPEG
- ⏹ Ferma: Ferma lo streaming
- 💾 Salva Config: Salva la configurazione (incluso avvio automatico)

URL Stream: http://[IP_RASPBERRY]:8080

7.3 GESTIONE RTSP STREAM
-------------------------
Pulsanti disponibili:
- ▶ Avvia: Avvia lo streaming RTSP
- ⏹ Ferma: Ferma lo streaming
- 💾 Salva Config: Salva la configurazione

URL Stream: rtsp://[IP_RASPBERRY]:8554/video

7.4 IMPOSTAZIONI
----------------
Click su "⚙️ Impostazioni":
- Cambia username
- Cambia password
- Disabilita autenticazione (sconsigliato)

7.5 LOGOUT
----------
Click su "🚪 Esci" per terminare la sessione

================================================================================
8. ACCESSO AGLI STREAM
================================================================================

8.1 STREAM MJPEG
----------------
Visualizzazione Web (Browser):
- URL principale: http://[IP_RASPBERRY]:8080
- Stream diretto: http://[IP_RASPBERRY]:8080/?action=stream
- Singola immagine: http://[IP_RASPBERRY]:8080/?action=snapshot

Esempio HTML per embedding:
    <img src="http://192.168.1.100:8080/?action=stream" />

8.2 STREAM RTSP
---------------
Visualizzazione con VLC:
1. Apri VLC
2. Media → Apri flusso di rete
3. URL: rtsp://[IP_RASPBERRY]:8554/video
4. Play

Da riga di comando:
    vlc rtsp://[IP_RASPBERRY]:8554/video
    ffplay rtsp://[IP_RASPBERRY]:8554/video

8.3 INTEGRAZIONE HOME ASSISTANT
--------------------------------
Aggiungi al file configuration.yaml:

    camera:
      - platform: mjpeg
        name: "Camera Analogica"
        mjpeg_url: http://[IP_RASPBERRY]:8080/?action=stream
        still_image_url: http://[IP_RASPBERRY]:8080/?action=snapshot

Oppure per RTSP:

    camera:
      - platform: ffmpeg
        name: "Camera Analogica RTSP"
        input: rtsp://[IP_RASPBERRY]:8554/video

8.4 INTEGRAZIONE FRIGATE NVR
-----------------------------
Nel file config.yml di Frigate:

    cameras:
      camera_analogica:
        ffmpeg:
          inputs:
            - path: rtsp://[IP_RASPBERRY]:8554/video
              roles:
                - detect
                - record

================================================================================
9. COMANDI UTILI
================================================================================

9.1 GESTIONE SERVIZI
---------------------
Stato servizi:
    sudo systemctl status stream-manager
    sudo systemctl status mediamtx

Riavvia servizi:
    sudo systemctl restart stream-manager
    sudo systemctl restart mediamtx

Ferma servizi:
    sudo systemctl stop stream-manager
    sudo systemctl stop mediamtx

Avvia servizi:
    sudo systemctl start stream-manager
    sudo systemctl start mediamtx

Disabilita avvio automatico:
    sudo systemctl disable stream-manager
    sudo systemctl disable mediamtx

Abilita avvio automatico:
    sudo systemctl enable stream-manager
    sudo systemctl enable mediamtx

9.2 VISUALIZZAZIONE LOG
------------------------
Log in tempo reale:
    sudo journalctl -u stream-manager -f
    sudo journalctl -u mediamtx -f

Ultimi 100 log:
    sudo journalctl -u stream-manager -n 100
    sudo journalctl -u mediamtx -n 100

Log degli errori:
    sudo journalctl -u stream-manager -p err

9.3 VERIFICA DISPOSITIVI VIDEO
-------------------------------
Lista dispositivi:
    ls -l /dev/video*

Informazioni dispositivo:
    v4l2-ctl --list-devices
    v4l2-ctl -d /dev/video0 --list-formats
    v4l2-ctl -d /dev/video0 --all

9.4 MONITORAGGIO SISTEMA
-------------------------
Utilizzo CPU e memoria:
    htop

Temperatura CPU:
    vcgencmd measure_temp

Velocità CPU:
    vcgencmd measure_clock arm

Informazioni sistema:
    uname -a
    cat /proc/cpuinfo

9.5 GESTIONE PROCESSI STREAM
-----------------------------
Verifica processi attivi:
    ps aux | grep mjpg
    ps aux | grep ffmpeg
    ps aux | grep mediamtx

Termina manualmente processi:
    sudo pkill -f mjpg_streamer
    sudo pkill -f ffmpeg
    sudo pkill mediamtx

================================================================================
10. RISOLUZIONE PROBLEMI
================================================================================

10.1 L'INTERFACCIA WEB NON SI APRE
-----------------------------------
Problema: http://[IP]:5000 non risponde

Soluzione:
1. Verifica che il servizio sia attivo:
   sudo systemctl status stream-manager

2. Se non è attivo, avvialo:
   sudo systemctl start stream-manager

3. Controlla i log per errori:
   sudo journalctl -u stream-manager -n 50

4. Verifica la porta:
   sudo netstat -tulpn | grep 5000

5. Verifica il firewall:
   sudo ufw status

10.2 DISPOSITIVO VIDEO NON RILEVATO
------------------------------------
Problema: /dev/video0 non esiste

Soluzione:
1. Verifica che l'adattatore USB sia collegato
2. Controlla i dispositivi:
   lsusb
   ls -l /dev/video*

3. Verifica driver:
   dmesg | grep video
   dmesg | grep uvc

4. Prova a scollegare e ricollegare l'adattatore USB

5. Se il dispositivo appare come /dev/video1 o altro numero,
   selezionalo dal menu dell'interfaccia web

10.3 STREAM NON SI AVVIA
-------------------------
Problema: Lo stream non parte quando clicco "Avvia"

Soluzione MJPG:
1. Verifica il dispositivo:
   v4l2-ctl -d /dev/video0 --list-formats

2. Prova manualmente:
   mjpg_streamer -i "input_uvc.so -d /dev/video0 -r 640x480 -f 15" \
                 -o "output_http.so -p 8080"

3. Controlla i log:
   sudo journalctl -u stream-manager -f

Soluzione RTSP:
1. Verifica MediaMTX:
   sudo systemctl status mediamtx

2. Verifica FFmpeg:
   ps aux | grep ffmpeg

3. Test manuale FFmpeg:
   ffmpeg -f v4l2 -i /dev/video0 -f mpegts -

10.4 QUALITÀ VIDEO SCARSA
--------------------------
Problema: Video sfocato o a scatti

Soluzione:
1. Aumenta la risoluzione (es. 800x600 o 1280x720)
2. Aumenta il bitrate RTSP (es. 2000k invece di 1000k)
3. Aumenta la qualità MJPG (es. 95 invece di 85)
4. Riduci il framerate se la CPU è al limite
5. Usa RTSP invece di MJPG per qualità superiore

10.5 CPU AL 100%
----------------
Problema: Il Raspberry è lento, CPU sempre al massimo

Soluzione:
1. Non avviare MJPG e RTSP contemporaneamente
2. Riduci risoluzione (es. 320x240 o 640x480)
3. Riduci framerate (es. 10-15 fps invece di 25-30)
4. Per RTSP, usa preset "ultrafast" (già configurato)
5. Monitora la temperatura:
   vcgencmd measure_temp
   Se supera 80°C, aggiungi un dissipatore

10.6 STREAM SI INTERROMPE
--------------------------
Problema: Lo stream parte ma si ferma dopo pochi secondi

Soluzione:
1. Verifica alimentazione (usa alimentatore ufficiale 5V 2.5A)
2. Controlla i log:
   sudo journalctl -u stream-manager -f

3. Verifica la memoria:
   free -h

4. Riavvia il servizio:
   sudo systemctl restart stream-manager

10.7 NON RIESCO A FARE LOGIN
-----------------------------
Problema: "Username o password non validi"

Soluzione:
1. Verifica di usare le credenziali corrette
2. Se le hai dimenticate, resetta (vedi sezione 5.2)
3. Controlla che il file auth esista:
   ls -l ~/stream_manager/stream_auth.json

4. Se necessario, ricrea il file credenziali di default

10.8 AVVIO AUTOMATICO NON FUNZIONA
-----------------------------------
Problema: Dopo il reboot gli stream non partono

Soluzione:
1. Verifica che l'avvio automatico sia abilitato nell'interfaccia
2. Controlla la configurazione:
   cat ~/stream_manager/stream_config.json
   Cerca "autostart": true

3. Verifica i servizi systemd:
   sudo systemctl is-enabled stream-manager
   sudo systemctl is-enabled mediamtx

4. Controlla i log di avvio:
   sudo journalctl -u stream-manager --since "5 minutes ago"

================================================================================
11. BACKUP E RIPRISTINO
================================================================================

11.1 BACKUP CONFIGURAZIONE
---------------------------
Salva questi file importanti:

    # Crea directory backup
    mkdir -p ~/backup
    
    # Backup configurazione stream
    cp ~/stream_config.json ~/backup/
    
    # Backup credenziali
    cp ~/stream_auth.json ~/backup/
    
    # Copia i backup sul tuo computer
    # Da terminale locale (sostituisci [TUO_USERNAME]):
    scp [TUO_USERNAME]@[IP_RASPBERRY]:~/backup/*.json ./

11.2 RIPRISTINO CONFIGURAZIONE
-------------------------------
Copia i file di backup sul Raspberry:

    # Dal tuo computer (sostituisci [TUO_USERNAME])
    scp stream_config.json stream_auth.json [TUO_USERNAME]@[IP_RASPBERRY]:~/
    
    # Sul Raspberry
    sudo systemctl restart stream-manager

11.3 BACKUP COMPLETO SD CARD
-----------------------------
Da computer con lettore SD (Linux/Mac):

    # Inserisci la SD card
    # Trova il device (es. /dev/sdb)
    lsblk
    
    # Crea immagine backup
    sudo dd if=/dev/sdb of=raspberry_backup.img bs=4M status=progress
    
    # Comprimi (opzionale)
    gzip raspberry_backup.img

Da Windows, usa Win32DiskImager o Etcher.

11.4 RIPRISTINO DA BACKUP SD
-----------------------------
    # Scrivi l'immagine su una nuova SD
    sudo dd if=raspberry_backup.img of=/dev/sdb bs=4M status=progress

11.5 REINSTALLAZIONE RAPIDA
----------------------------
Se devi reinstallare tutto:

    # Rimuovi installazione corrente
    rm -rf ~/stream_manager
    sudo systemctl disable stream-manager
    sudo systemctl disable mediamtx
    sudo rm /etc/systemd/system/stream-manager.service
    sudo rm /etc/systemd/system/mediamtx.service
    
    # Riesegui installazione
    bash install.sh

================================================================================
CONFIGURAZIONI CONSIGLIATE PER RASPBERRY PI ZERO 2W
================================================================================

CONFIGURAZIONE LEGGERA (consigliata):
--------------------------------------
MJPG Streamer:
- Risoluzione: 640x480
- Framerate: 15 fps
- Qualità: 85
- Avvio automatico: ON

RTSP: Disattivato

CONFIGURAZIONE QUALITÀ:
-----------------------
RTSP Stream:
- Risoluzione: 640x480
- Framerate: 25 fps
- Bitrate: 1000k
- Avvio automatico: ON

MJPG: Disattivato

CONFIGURAZIONE BILANCIATA:
--------------------------
Usa MJPG per l'interfaccia web e visualizzazione rapida
Usa RTSP solo quando serve qualità superiore o recording
NON avviare entrambi automaticamente

================================================================================
SUPPORTO E RISORSE
================================================================================

Documentazione:
- mjpg-streamer: https://github.com/jacksonliam/mjpg-streamer
- MediaMTX: https://github.com/bluenviron/mediamtx
- FFmpeg: https://ffmpeg.org/documentation.html

Forum e Community:
- Raspberry Pi Forum: https://forums.raspberrypi.com
- Reddit r/raspberry_pi: https://reddit.com/r/raspberry_pi

Verifica stato sistema:
    http://[IP_RASPBERRY]:5000

Log in tempo reale:
    sudo journalctl -u stream-manager -f

================================================================================
CHANGELOG E NOTE VERSIONE
================================================================================

Versione: 1.0
Data: 2024

Funzionalità:
✓ Streaming MJPEG su HTTP
✓ Streaming RTSP con H.264
✓ Interfaccia web responsive
✓ Autenticazione con login
✓ Avvio automatico configurabile
✓ Monitoraggio sistema in tempo reale
✓ Gestione multi-dispositivo video
✓ Configurazione persistente

Requisiti:
- Raspberry Pi Zero 2W o superiore
- Raspberry Pi OS (64-bit) Lite o Desktop
- Adattatore video USB compatibile Linux (driver UVC)
- Connessione di rete (WiFi o Ethernet)

================================================================================
FINE DELLA GUIDA
================================================================================

Per domande o problemi non coperti in questa guida, controlla i log:
    sudo journalctl -u stream-manager -n 100

Buona visione con il tuo stream!