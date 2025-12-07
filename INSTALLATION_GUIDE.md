# Raspberry Pi Stream Manager - Guida Installazione Ottimizzata

## 📋 Prerequisiti

- Raspberry Pi 4/5 con Raspberry Pi OS Bookworm
- Connessione SSH ✓
- ~1GB spazio libero
- Utente con sudo privileges

---

## 🚀 Installazione Rapida

### Step 1: Clone Repository
```bash
# Connettiti via SSH
ssh pi@raspberrypi

# Scarica/prepara i file
cd ~
git clone https://github.com/tuouser/videoStreamer.git
cd videoStreamer
```

### Step 2: Esegui Install Script
```bash
# L'unico comando che serve!
bash auto_install.sh
```

**Cosa fa automaticamente:**
- ✅ Aggiorna il sistema
- ✅ Installa dipendenze (cmake, ffmpeg, python3)
- ✅ Compila mjpg-streamer
- ✅ Scarica e configura MediaMTX
- ✅ Crea servizio web Flask
- ✅ Configura cloud-init (preserve hostname)
- ✅ Configura permessi sudo
- ✅ Avvia tutti i servizi

---

## 📱 Accesso Interfaccia Web

Dopo l'installazione:

```
🌐 URL:              http://<IP-RASPBERRY>:5000
🔐 Username:         admin
🔐 Password:         admin  (CAMBIATE SUBITO!)
```

### Features Disponibili:

1. **🎥 Gestione Stream**
   - Avvia/ferma MJPG streamer
   - Avvia/ferma RTSP server
   - Configurazione risoluzioni
   - Gestione bitrate

2. **🌐 Rete (Network Config)**
   - Cambia hostname del dispositivo
   - Configura IP statico
   - Configura DHCP
   - Visualizza info di rete

3. **🔐 Sicurezza**
   - Cambia password
   - Disabilita autenticazione (⚠️ sconsigliato)

---

## 🔧 Comandi Utili

### Monitoraggio Servizi
```bash
# Status servizi
sudo systemctl status stream-manager
sudo systemctl status mediamtx

# Visualizza log in real-time
sudo journalctl -u stream-manager -f
sudo journalctl -u mediamtx -f
```

### Gestione Manuale
```bash
# Riavvia servizi
sudo systemctl restart stream-manager
sudo systemctl restart mediamtx

# Ferma servizi
sudo systemctl stop stream-manager
sudo systemctl stop mediamtx

# Abilita/disabilita auto-start
sudo systemctl enable stream-manager
sudo systemctl disable stream-manager
```

### Cambio Password da CLI
```bash
cd ~/stream_manager
python3 change_password.py
```

---

## 📡 Stream URLs

Una volta avviato:

### MJPG Stream (HTTP)
```
http://<IP>:8080
```
Con autenticazione:
```
http://username:password@<IP>:8080
```

### RTSP Stream
```
rtsp://<IP>:8554/video
```
Con autenticazione:
```
rtsp://username:password@<IP>:8554/video
```

---

## 🛠️ Troubleshooting

### Script non esegue? Permessi
```bash
# Rendi script eseguibile
chmod +x auto_install.sh
chmod +x bash_helpers.sh

# Esegui di nuovo
bash auto_install.sh
```

### Port 8080 già in uso?
```bash
# Libera il port
sudo systemctl stop mediamtx
sudo lsof -i :8080
sudo kill -9 <PID>
```

### Hostname non persiste?
```bash
# Verifica cloud-init config
cat /etc/cloud/cloud.cfg | grep preserve_hostname
# Deve essere: preserve_hostname: true

# Se non è presente, aggiungi:
sudo vi /etc/cloud/cloud.cfg
# Aggiungi: preserve_hostname: true
```

### Connessione SSH non funziona?
```bash
# Verifica SSH è avviato
sudo systemctl status ssh

# Riavvia SSH
sudo systemctl restart ssh

# Abilita SSH all'avvio
sudo systemctl enable ssh
```

---

## 🌐 RaspAP Setup (Opzionale)

Se vuoi configurare hotspot WiFi automatico:

```bash
# Esegui script RaspAP
bash setup_raspap_autohotspot_optimized.sh
```

**Funzionamento:**
- Se Raspberry ha internet → hotspot disabilitato
- Se Raspberry offline → hotspot attivo

Accedi a: `http://10.3.141.1/`

---

## 🔐 Sicurezza Consigli

⚠️ **IMPORTANTE - Fare subito:**

1. **Cambia password di default**
   ```bash
   cd ~/stream_manager
   python3 change_password.py
   ```

2. **Cambia username SSH**
   ```bash
   # Crea nuovo utente
   sudo useradd -m -s /bin/bash newuser
   sudo usermod -aG sudo newuser
   
   # Disabilita utente 'pi'
   sudo usermod -L pi
   ```

3. **Configura firewall**
   ```bash
   sudo apt install ufw
   sudo ufw default deny incoming
   sudo ufw default allow outgoing
   sudo ufw allow 22    # SSH
   sudo ufw allow 5000  # Web
   sudo ufw allow 8080  # MJPG
   sudo ufw allow 8554  # RTSP
   sudo ufw enable
   ```

4. **Disabilita accesso root**
   ```bash
   sudo passwd -l root
   ```

5. **Usa SSH keys**
   ```bash
   # Su client (non Raspberry)
   ssh-keygen -t ed25519
   ssh-copy-id -i ~/.ssh/id_ed25519.pub pi@raspberrypi
   
   # Su Raspberry
   sudo nano /etc/ssh/sshd_config
   # Imposta: PasswordAuthentication no
   sudo systemctl restart ssh
   ```

---

## 📊 Monitoraggio Performance

### Log dei Servizi
```bash
# Ultime 100 linee di log
sudo journalctl -u stream-manager -n 100

# Log degli ultimi 30 minuti
sudo journalctl -u stream-manager --since "30 minutes ago"

# Log di errori solamente
sudo journalctl -u stream-manager -p err
```

### Utilizzo Risorse
```bash
# CPU e memoria in real-time
top

# Spazio disco
df -h

# Processi Python
ps aux | grep python3
```

---

## 🔄 Aggiornamenti

### Aggiorna Sistema
```bash
sudo apt update
sudo apt upgrade -y
sudo apt dist-upgrade -y
```

### Aggiorna Applicazione
```bash
# Scarica nuovo app.py da GitHub
cd ~/stream_manager
wget -O app.py https://raw.githubusercontent.com/tuouser/videoStreamer/main/app.py

# Riavvia servizio
sudo systemctl restart stream-manager
```

---

## 🐛 Debug Mode

### Abilita debug logging
```bash
# Modifica app.py
sudo nano ~/stream_manager/app.py

# Aggiungi all'inizio:
import logging
logging.basicConfig(level=logging.DEBUG)

# Riavvia
sudo systemctl restart stream-manager
```

### Esegui script in debug mode
```bash
# Mostra ogni comando eseguito
bash -x auto_install.sh

# O aggiungi all'inizio dello script:
set -x
```

---

## 📞 Support

### Comandi Help
```bash
# Info sistema
uname -a
hostnamectl
hostname -I

# Info Python
python3 --version
pip3 list

# Info Flask
cd ~/stream_manager
python3 -c "import flask; print(flask.__version__)"
```

### Backup Configurazione
```bash
# Copia config
sudo cp -r /etc/mediamtx ~/backup_mediamtx
sudo cp /etc/hostname ~/backup_hostname
sudo cp -r ~/.config ~/backup_config
```

### Restore da Backup
```bash
# Ripristina config
sudo cp -r ~/backup_mediamtx /etc/
sudo systemctl restart mediamtx
```

---

## 📈 Performance Tuning

### Aumenta memoria per stream
```bash
# Modifica stream_config.json
nano ~/stream_manager/stream_config.json

# Aumenta framerate/bitrate
"framerate": 30,      # Da 10 a 30
"bitrate": "2000k",   # Da 500k a 2000k
"quality": 95         # Da 75 a 95
```

### Ottimizza CPU
```bash
# Riduci CPU overhead
"resolution": "640x480"   # Da 320x240 a 640x480

# Usa hardware encoding (se disponibile)
# Vedi documentazione mjpg-streamer
```

### Memoria disponibile
```bash
# Vedi memoria RAM disponibile
free -h

# Abilita swap se necessario
sudo dd if=/dev/zero of=/swapfile bs=1G count=2
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

---

## ✅ Checklist Post-Installazione

- [ ] Script terminato senza errori
- [ ] Accedi a web interface: `http://<IP>:5000`
- [ ] Cambia password di default
- [ ] Accedi per testare autenticazione
- [ ] Visualizza pagina Network
- [ ] Visualizza pagina Stream
- [ ] Prova a cambiare hostname
- [ ] Verifica hostname dopo reboot
- [ ] Prova a configurare IP statico
- [ ] Riavvia Raspberry: `sudo reboot`
- [ ] Verifica servizi rimangono avviati post-reboot
- [ ] Verifica MJPG stream: `http://<IP>:8080`
- [ ] Verifica RTSP stream (da VLC): `rtsp://<IP>:8554/video`
- [ ] Setup RaspAP hotspot (opzionale)
- [ ] Configura firewall (importante!)

---

## 🎉 Completato!

Congratulazioni! Il tuo Raspberry Pi Stream Manager è pronto per l'uso in produzione.

Per support o issues: GitHub Issues (se disponibile)

**Happy streaming!** 🎬

---

## 📚 File di Riferimento

- `app.py` - Flask backend (1180 LOC)
- `templates/index.html` - Web interface (1450 LOC)
- `bash_helpers.sh` - Helper functions (180 LOC)
- `auto_install.sh` - Installation script (180 LOC)
- `change_hostname.sh` - Hostname management (48 LOC)
- `CODE_REVIEW.md` - Code quality report
- `BASH_OPTIMIZATION_REPORT.md` - Optimization details
- `OPTIMIZATION_SUMMARY.md` - Complete summary
