"""
Raspberry Pi Video Streaming Manager
Gestisce mjpg-streamer e FFmpeg/MediaMTX tramite interfaccia web
Con autenticazione per stream MJPG e RTSP
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
import subprocess
import os
import json
import psutil
import hashlib
import secrets
import re
import time

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
app.config['MAX_CONTENT_LENGTH'] = 2000 * 1024 * 1024  # 2GB limite upload

# Percorsi relativi alla cartella dell'applicazione
APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(APP_DIR, 'stream_config.json')
AUTH_FILE = os.path.join(APP_DIR, 'stream_auth.json')

# Tracker per i processi FFmpeg
rtsp_ffmpeg_process = None

# Configurazione di default
DEFAULT_CONFIG = {
    'mjpg': {
        'enabled': False,
        'device': '/dev/video0',
        'resolution': '640x480',
        'framerate': 15,
        'quality': 85,
        'port': 8080,
        'autostart': True,
        'source_type': 'device',
        'auth_enabled': True,  # Autenticazione abilitata di default
        'auth_username': 'stream',
        'auth_password': 'stream'  # Cambiare dopo l'installazione!
    },
    'rtsp': {
        'enabled': False,
        'device': '/dev/video0',
        'resolution': '640x480',
        'framerate': 25,
        'bitrate': '1000k',
        'port': 8554,
        'autostart': False,
        'source_type': 'device',
        'auth_enabled': True,  # Autenticazione abilitata di default
        'auth_username': 'stream',
        'auth_password': 'stream'  # Cambiare dopo l'installazione!
    },
    'video': {
        'path': os.path.join(APP_DIR, 'videos', 'demo.mp4'),
        'loop': True
    }
}


def load_config():
    """Carica la configurazione dal file"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return DEFAULT_CONFIG.copy()


def save_config(config):
    """Salva la configurazione su file"""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


def load_auth():
    """Carica le credenziali di autenticazione interfaccia web"""
    if os.path.exists(AUTH_FILE):
        with open(AUTH_FILE, 'r') as f:
            return json.load(f)
    return {
        'username': 'admin',
        'password': hashlib.sha256('admin'.encode()).hexdigest(),
        'enabled': True
    }


def save_auth(auth_data):
    """Salva le credenziali di autenticazione"""
    with open(AUTH_FILE, 'w') as f:
        json.dump(auth_data, f, indent=2)


def check_password(username, password):
    """Verifica username e password"""
    auth = load_auth()
    if not auth.get('enabled', True):
        return True
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    return username == auth['username'] and password_hash == auth['password']


def login_required(f):
    """Decorator per richiedere il login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth = load_auth()
        if not auth.get('enabled', True):
            return f(*args, **kwargs)
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def update_mediamtx_config(rtsp_config):
    """Aggiorna configurazione MediaMTX con autenticazione"""
    auth_enabled = rtsp_config.get('auth_enabled', False)
    username = rtsp_config.get('auth_username', 'stream')
    password = rtsp_config.get('auth_password', 'stream')
    
    # Config base
    config_content = f"""logLevel: info
logDestinations: [stdout]

rtspAddress: :{rtsp_config.get('port', 8554)}
rtpAddress: :8000
rtcpAddress: :8001
hlsAddress: :8888

"""
    
    if auth_enabled:
        # NESSUNA riga "authMethod: basic" qui
        config_content += f"""paths:
  all:
    publishUser: {username}
    publishPass: {password}
    readUser: {username}
    readPass: {password}
"""
    else:
        config_content += """paths:
  all:
"""

    # Scrivi config temporaneo e poi copia in /etc
    with open('/tmp/mediamtx.yml', 'w') as f:
        f.write(config_content)
    
    subprocess.run(
        ['sudo', 'cp', '/tmp/mediamtx.yml', '/etc/mediamtx/mediamtx.yml'],
        check=True
    )


def is_process_running(pattern):
    """Controlla se un processo che matcha il pattern regex è in esecuzione"""
    for proc in psutil.process_iter(['name', 'cmdline']):
        try:
            cmd = ' '.join(proc.info.get('cmdline') or [])
            if re.search(pattern, cmd):
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False

def start_mjpg_streamer(config):
    """Avvia mjpg-streamer con autenticazione opzionale"""
    source_type = config.get('source_type', 'device')
    auth_enabled = config.get('auth_enabled', False)
    
    print(f"[MJPG] Configurazione: source={source_type}, auth={auth_enabled}")
    
    # Prepara autenticazione se abilitata
    auth_params = ''
    if auth_enabled:
        username = config.get('auth_username', 'stream')
        password = config.get('auth_password', 'stream')
        auth_params = f'-c {username}:{password}'
        print(f"[MJPG] Autenticazione attiva: {username}:****")

    if source_type == 'video':
        # Sorgente = file video
        video_path = config.get('video_path', '')
        
        if not video_path:
            # Fallback: leggi dalla config file se non fornito
            full_config = load_config()
            video_path = full_config.get('mjpg', {}).get('video_path', '')

        if not os.path.exists(video_path):
            error_msg = f"Video non trovato: {video_path}"
            print(f"[MJPG] ❌ {error_msg}")
            raise Exception(error_msg)

        print(f"[MJPG] Usando video: {video_path}")
        
        frames_dir = '/tmp/mjpg_frames'
        os.makedirs(frames_dir, exist_ok=True)

        # Pulisci JPG vecchi
        for f in os.listdir(frames_dir):
            if f.lower().endswith(('.jpg', '.jpeg')):
                try:
                    os.remove(os.path.join(frames_dir, f))
                except:
                    pass

        fps = config.get('framerate', 15)
        quality = config.get('quality', 85)
        qscale = max(1, min(31, quality // 3))

        ffmpeg_cmd = [
            'ffmpeg',
            '-stream_loop', '-1',
            '-re', '-i', video_path,
            '-vf', f'fps={fps}',
            '-q:v', str(qscale),
            os.path.join(frames_dir, 'frame_%06d.jpg')
        ]
        
        print(f"[MJPG] Avvio FFmpeg: {' '.join(ffmpeg_cmd)}")
        subprocess.Popen(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # input_file.so: specifica la cartella dei frame
        input_params = f'input_file.so -folder {frames_dir} -d 0 -r'
        output_params = f'output_http.so -p {config["port"]} -n'
        
        if auth_params:
            output_params += f' {auth_params}'
            
        mjpg_cmd = [
            '/usr/local/bin/mjpg_streamer',
            '-i', input_params,
            '-o', output_params
        ]
    else:
        # Sorgente = dispositivo video USB
        device = config['device']
        
        if not os.path.exists(device):
            error_msg = f"Dispositivo non trovato: {device}"
            print(f"[MJPG] ❌ {error_msg}")
            raise Exception(error_msg)
            
        print(f"[MJPG] Usando dispositivo: {device}")
        
        # input_uvc.so usa -d per device, -r per resolution, -f per framerate, -q per quality
        input_params = f'input_uvc.so -d {device} -r {config["resolution"]} -f {config["framerate"]} -q {config["quality"]}'
        output_params = f'output_http.so -p {config["port"]} -n'
        
        if auth_params:
            output_params += f' {auth_params}'
        
        mjpg_cmd = [
            '/usr/local/bin/mjpg_streamer',
            '-i', input_params,
            '-o', output_params
        ]

    # Log del comando completo per debug (nascondi password nella stampa)
    cmd_display = ' '.join(mjpg_cmd)
    if auth_params:
        cmd_display = cmd_display.replace(auth_params, '-c ****:****')
    print(f"[MJPG] Comando completo: {cmd_display}")
    
    try:
        # ⚠️ Qui la differenza importante: niente shell=True, e passo la LISTA
        process = subprocess.Popen(
            mjpg_cmd,
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE
        )
        
        # Attendi un attimo per verificare se si avvia
        import time
        time.sleep(1)
        
        if process.poll() is not None:
            # Processo terminato subito, c'è un errore
            stdout, stderr = process.communicate()
            error_msg = stderr.decode() if stderr else "Processo terminato immediatamente"
            print(f"[MJPG] ❌ Errore avvio: {error_msg}")
            raise Exception(f"MJPG non si avvia: {error_msg}")
        
        print(f"[MJPG] ✅ Avviato con successo (PID: {process.pid})")
        return True
        
    except Exception as e:
        print(f"[MJPG] ❌ Eccezione: {str(e)}")
        raise


def stop_mjpg_streamer():
    """Ferma mjpg-streamer"""
    subprocess.run(['pkill', '-f', 'mjpg_streamer'], stderr=subprocess.DEVNULL)
    subprocess.run(['pkill', '-f', 'ffmpeg.*mjpg_fifo'], shell=True, stderr=subprocess.DEVNULL)
    
    fifo_path = '/tmp/mjpg_fifo'
    if os.path.exists(fifo_path):
        try:
            os.remove(fifo_path)
        except:
            pass
    return True


def start_rtsp_stream(config):
    """Avvia lo streaming RTSP con FFmpeg e autenticazione"""
    print(f"[RTSP] Configurazione: source={config.get('source_type', 'device')}, auth={config.get('auth_enabled', False)}")
    
    # Aggiorna configurazione MediaMTX con autenticazione
    try:
        update_mediamtx_config(config)
        print("[RTSP] ✅ Configurazione MediaMTX aggiornata")
    except Exception as e:
        print(f"[RTSP] ❌ Errore configurazione MediaMTX: {e}")
        raise
    
    # Riavvia MediaMTX per applicare la configurazione
    print("[RTSP] Riavvio MediaMTX...")
    result = subprocess.run(['sudo', 'systemctl', 'restart', 'mediamtx'], 
                           capture_output=True, text=True)
    if result.returncode != 0:
        error_msg = f"Errore riavvio MediaMTX: {result.stderr}"
        print(f"[RTSP] ❌ {error_msg}")
        raise Exception(error_msg)
    
    # Attendi che MediaMTX si avvii
    import time
    print("[RTSP] Attesa avvio MediaMTX...")
    time.sleep(3)
    
    # Verifica che MediaMTX sia attivo
    result = subprocess.run(['systemctl', 'is-active', 'mediamtx'], 
                           capture_output=True, text=True)
    if result.stdout.strip() != 'active':
        error_msg = "MediaMTX non si è avviato"
        print(f"[RTSP] ❌ {error_msg}")
        # Mostra log MediaMTX
        log_result = subprocess.run(['sudo', 'journalctl', '-u', 'mediamtx', '-n', '10', '--no-pager'],
                                   capture_output=True, text=True)
        print(f"[RTSP] Log MediaMTX:\n{log_result.stdout}")
        raise Exception(error_msg)
    
    print("[RTSP] ✅ MediaMTX attivo")

    source_type = config.get('source_type', 'device')
    auth_enabled = config.get('auth_enabled', False)
    username = config.get('auth_username', 'stream')
    password = config.get('auth_password', 'stream')
    port = config.get('port', 8554)
    
    # Costruisci URL RTSP con o senza autenticazione
    if auth_enabled:
        rtsp_url = f"rtsp://{username}:{password}@localhost:{port}/video"
        print(f"[RTSP] URL con auth: rtsp://{username}:****@localhost:{port}/video")
    else:
        rtsp_url = f"rtsp://localhost:{port}/video"
        print(f"[RTSP] URL senza auth: {rtsp_url}")

    if source_type == 'video':
        full_config = load_config()
        video_path = full_config.get('rtsp', {}).get('video_path', '')

        if not os.path.exists(video_path):
            error_msg = f"Video non trovato: {video_path}"
            print(f"[RTSP] ❌ {error_msg}")
            raise Exception(error_msg)

        print(f"[RTSP] Usando video: {video_path}")
        
        loop_option = ['-stream_loop', '-1']

        cmd = [
            'ffmpeg'
        ] + loop_option + [
            '-re',
            '-i', video_path,
            '-c:v', 'h264_v4l2m2m',#'libx264',
            '-preset', 'veryfast',
            '-tune', 'zerolatency',
            '-b:v', config['bitrate'],
            '-maxrate', config['bitrate'],
            '-bufsize', '2000k',
            '-s', config['resolution'],
            '-r', str(config['framerate']),
            '-c:a', 'aac',  # Codec audio AAC
            '-b:a', '64k',  # Bitrate audio
            '-f', 'rtsp',
            rtsp_url
        ]
    else:
        device = config['device']
        
        if not os.path.exists(device):
            error_msg = f"Dispositivo non trovato: {device}"
            print(f"[RTSP] ❌ {error_msg}")
            raise Exception(error_msg)
            
        print(f"[RTSP] Usando dispositivo: {device}")
        
        # FFmpeg cattura da V4L2 (video) - senza audio per velocità su Pi Zero
        cmd = [
            'ffmpeg',
            '-f', 'v4l2',
            '-video_size', config['resolution'],
            '-framerate', str(config['framerate']),
            '-i', device,
            '-c:v', 'h264_v4l2m2m', #'libx264', 'libx264', # Codec video H.264
            '-preset', 'ultrafast',  # Velocissimo per Pi Zero
        # QUALITÀ: Alziamo il bitrate da 300k a 2000k
            '-b:v', '2000k',
            '-maxrate', '2500k',
            '-bufsize', '4000k',
            
            # STABILITÀ: Un Keyframe ogni 2 secondi (25fps * 2) aiuta il riaggancio
            '-g', '50',
            
            # FILTRI MAGICI:
            # 1. yadif -> Rimuove le righe orizzontali (Deinterlacciamento)
            # 2. hqdn3d -> Toglie la "neve" (Denoise leggero)
            # 3. eq=saturation=1.3 -> Aumenta il colore del 30% (visto che era smorto)
            # 4. format=yuv420p -> Formato standard
            '-vf', 'yadif,hqdn3d=2.0:2.0:6.0:6.0,eq=saturation=1.3,format=yuv420p',
            
            '-an', # Niente audio
            '-f', 'rtsp',
    rtsp_url
        ]

    # Log comando (nascondi password)
    cmd_display = ' '.join(cmd).replace(f":{password}@", ":****@")
    print(f"[RTSP] Comando FFmpeg: {cmd_display}")
    
    try:
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL
        )
        
        # Salva il PID globale per stop successivo
        global rtsp_ffmpeg_process
        rtsp_ffmpeg_process = process
        
        # Attendi per verificare se si avvia
        time.sleep(2)
        
        if process.poll() is not None:
            # Processo terminato subito, c'è un errore
            print(f"[RTSP] ❌ Errore FFmpeg: Processo terminato immediatamente")
            rtsp_ffmpeg_process = None
            raise Exception("FFmpeg non si avvia")
        
        print(f"[RTSP] ✅ FFmpeg avviato con successo (PID: {process.pid})")
        return True
        
    except Exception as e:
        print(f"[RTSP] ❌ Eccezione: {str(e)}")
        rtsp_ffmpeg_process = None
        raise


def stop_rtsp_stream():
    """Ferma lo streaming RTSP"""
    global rtsp_ffmpeg_process
    
    print("[RTSP] 🛑 Tentativo di fermare RTSP...")
    
    # Ferma il processo FFmpeg tracciato
    if rtsp_ffmpeg_process is not None:
        try:
            print(f"[RTSP] Uccisione processo FFmpeg (PID: {rtsp_ffmpeg_process.pid})...")
            rtsp_ffmpeg_process.terminate()  # SIGTERM
            rtsp_ffmpeg_process.wait(timeout=3)
            print("[RTSP] ✅ FFmpeg terminato gracefully")
        except subprocess.TimeoutExpired:
            print("[RTSP] ⚠️  FFmpeg non ha risposto, forza kill...")
            rtsp_ffmpeg_process.kill()  # SIGKILL
            rtsp_ffmpeg_process.wait()
            print("[RTSP] ✅ FFmpeg ucciso")
        except Exception as e:
            print(f"[RTSP] ⚠️  Errore kill FFmpeg: {e}")
        finally:
            rtsp_ffmpeg_process = None
    else:
        print("[RTSP] ℹ️  Nessun processo FFmpeg tracciato")
    
    # Ferma anche MediaMTX
    try:
        subprocess.run(['sudo', 'systemctl', 'stop', 'mediamtx'], 
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        print("[RTSP] ✅ MediaMTX fermato")
    except Exception as e:
        print(f"[RTSP] ⚠️  Errore stop MediaMTX: {e}")
    
    print("[RTSP] ✅ Stream RTSP completamente fermato")
    return True


def get_video_devices():
    """Ottiene la lista dei dispositivi video disponibili"""
    devices = []
    for i in range(10):
        dev = f'/dev/video{i}'
        if os.path.exists(dev):
            devices.append(dev)
    return devices


def get_system_info():
    """Ottiene informazioni di sistema"""
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    temp = 0
    try:
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
            temp = float(f.read()) / 1000
    except:
        pass

    return {
        'cpu': cpu_percent,
        'memory': memory.percent,
        'temperature': temp
    }


def get_hostname():
    """Ottiene l'hostname attuale"""
    try:
        result = subprocess.run(['hostname'], capture_output=True, text=True)
        return result.stdout.strip()
    except:
        return "unknown"


def set_hostname(new_hostname):
    """Cambia l'hostname del Raspberry Pi"""
    try:
        # Validazione hostname
        if not re.match(r'^[a-z0-9-]{1,63}$', new_hostname, re.IGNORECASE):
            raise ValueError("Hostname non valido. Usa solo lettere, numeri e trattini")
        
        print(f"[NETWORK] 🔄 Cambio hostname in: {new_hostname}")
        
        # Usa lo script helper che ha i permessi sudoers configurati
        result = subprocess.run(
            ['sudo', '/usr/local/bin/change_hostname.sh', new_hostname],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Errore sconosciuto"
            print(f"[NETWORK] ❌ Errore: {error_msg}")
            raise ValueError(f"Errore cambio hostname: {error_msg}")
        
        print(result.stdout)
        print(f"[NETWORK] ✅ Hostname cambiato in: {new_hostname}")
        return True
    except Exception as e:
        print(f"[NETWORK] ❌ Errore cambio hostname: {e}")
        raise


def get_network_info():
    """Ottiene informazioni di rete (interfaccia, IP, configurazione)"""
    try:
        config = {}
        
        # Ottieni IP corrente da 'ip addr' (più affidabile di hostname -I)
        try:
            result = subprocess.run(['ip', 'addr', 'show'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                current_ips = []
                for line in lines:
                    # Cerca pattern "inet 192.168.1.x/24"
                    if 'inet ' in line and 'inet6' not in line:
                        parts = line.strip().split()
                        if len(parts) >= 2:
                            ip_with_mask = parts[1]
                            ip = ip_with_mask.split('/')[0]
                            if ip != '127.0.0.1':  # Escludi loopback
                                current_ips.append(ip)
                config['current_ip'] = current_ips[0] if current_ips else 'N/A'
            else:
                config['current_ip'] = 'N/A'
        except Exception as e:
            print(f"[NETWORK] ⚠️  Errore lettura IP: {e}")
            config['current_ip'] = 'N/A'
        
        # Ottieni il gateway da 'ip route show'
        try:
            result = subprocess.run(['ip', 'route', 'show'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                gateway = '--'
                for line in lines:
                    # Cerca la linea "default via 192.168.1.1 dev wlan0"
                    if line.startswith('default via'):
                        parts = line.split()
                        if len(parts) >= 3:
                            gateway = parts[2]
                            break
                config['gateway'] = gateway
            else:
                config['gateway'] = '--'
        except Exception as e:
            print(f"[NETWORK] ⚠️  Errore lettura gateway: {e}")
            config['gateway'] = '--'
        
        # Defaults
        config['mode'] = 'DHCP'
        config['interface'] = 'wlan0'
        config['dns'] = '--'
        
        # Leggi configurazione systemd-networkd
        systemd_network_dir = '/etc/systemd/network/'
        
        if os.path.exists(systemd_network_dir):
            for f in os.listdir(systemd_network_dir):
                if f.endswith('.network'):
                    filepath = os.path.join(systemd_network_dir, f)
                    try:
                        with open(filepath, 'r') as file:
                            content = file.read()
                            
                        # Estrai interfaccia dal nome del file
                        if 'static' in f:
                            config['mode'] = 'STATIC'
                            # Leggi i dettagli dal file
                            for line in content.split('\n'):
                                line = line.strip()
                                if line.startswith('Name='):
                                    config['interface'] = line.split('=')[1]
                                elif line.startswith('Address='):
                                    config['static_ip'] = line.split('=')[1]
                                elif line.startswith('Gateway='):
                                    config['gateway'] = line.split('=')[1]
                                elif line.startswith('DNS='):
                                    config['dns'] = line.split('=')[1]
                        elif 'dhcp' in f:
                            config['mode'] = 'DHCP'
                            for line in content.split('\n'):
                                line = line.strip()
                                if line.startswith('Name='):
                                    config['interface'] = line.split('=')[1]
                    except Exception as e:
                        print(f"[NETWORK] ⚠️  Errore lettura {f}: {e}")
        
        # Se nessuno trovato, prova /etc/dhcpcd.conf (metodo tradizionale Raspberry Pi)
        if config['mode'] == 'DHCP':
            dhcpcd_conf = '/etc/dhcpcd.conf'
            if os.path.exists(dhcpcd_conf):
                try:
                    with open(dhcpcd_conf, 'r') as file:
                        content = file.read()
                        # Cerca configurazione statica per l'interfaccia
                        in_interface_section = False
                        for line in content.split('\n'):
                            line = line.strip()
                            # Verifica se siamo nella sezione dell'interfaccia
                            if line.startswith(f'interface {config["interface"]}'):
                                in_interface_section = True
                                config['mode'] = 'STATIC'
                            elif in_interface_section:
                                if line.startswith('interface '):
                                    in_interface_section = False
                                elif line.startswith('static ip_address='):
                                    config['static_ip'] = line.split('=')[1]
                                elif line.startswith('static routers='):
                                    config['gateway'] = line.split('=')[1]
                                elif line.startswith('static domain_name_servers='):
                                    config['dns'] = line.split('=')[1]
                except Exception as e:
                    print(f"[NETWORK] ⚠️  Errore lettura /etc/dhcpcd.conf: {e}")
        
        # Se ancora DHCP, prova /etc/network/interfaces.d/
        if config['mode'] == 'DHCP' and not os.path.exists(systemd_network_dir):
            interfaces_dir = '/etc/network/interfaces.d/'
            if os.path.exists(interfaces_dir):
                for f in os.listdir(interfaces_dir):
                    if f.endswith('.conf') or '99-' in f:
                        filepath = os.path.join(interfaces_dir, f)
                        try:
                            with open(filepath, 'r') as file:
                                content = file.read()
                                if 'static' in content:
                                    config['mode'] = 'STATIC'
                                    for line in content.split('\n'):
                                        if line.strip().startswith('address '):
                                            config['static_ip'] = line.split()[1]
                                        elif line.strip().startswith('gateway '):
                                            config['gateway'] = line.split()[1]
                        except:
                            pass
        
        # Aggiungi il nome della rete WiFi connessa
        config['network_name'] = get_connected_network_name()
        
        return config
    except Exception as e:
        print(f"[NETWORK] ❌ Errore lettura configurazione rete: {e}")
        return {'error': str(e), 'current_ip': 'N/A', 'mode': 'DHCP', 'interface': 'wlan0', 'gateway': '--', 'dns': '--'}


def get_connected_network_name():
    """Ottiene il nome della rete WiFi connessa"""
    try:
        # Prova con iwconfig (metodo tradizionale)
        result = subprocess.run(['iwconfig', 'wlan0'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if 'ESSID:' in line:
                    # Estrai ESSID tra virgolette: ESSID:"NomeRete"
                    parts = line.split('ESSID:')
                    if len(parts) > 1:
                        essid = parts[1].strip().strip('"')
                        if essid:
                            return essid
        
        # Prova con iw (metodo più moderno)
        result = subprocess.run(['iw', 'dev', 'wlan0', 'link'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if 'SSID:' in line:
                    ssid = line.split('SSID:')[1].strip()
                    if ssid:
                        return ssid
        
        # Prova con nmcli (NetworkManager)
        try:
            result = subprocess.run(['nmcli', 'connection', 'show', '--active'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'connection.id' in line:
                        network_name = line.split(':')[1].strip() if ':' in line else ''
                        if network_name:
                            return network_name
        except:
            pass
        
        # Se nessun metodo funziona
        return '--'
    except Exception as e:
        print(f"[NETWORK] ⚠️  Errore lettura nome rete: {e}")
        return '--'


def _cidr_to_netmask(cidr):
    """Converte CIDR (es: 24) a netmask dotted decimal (es: 255.255.255.0)"""
    cidr = int(cidr)
    mask = (0xffffffff >> (32 - cidr)) << (32 - cidr)
    return '.'.join(map(str, [
        (mask >> 24) & 0xff,
        (mask >> 16) & 0xff,
        (mask >> 8) & 0xff,
        mask & 0xff
    ]))


def set_static_ip(interface, ip_address, netmask, gateway, dns):
    """Configura IP statico sia su dhcpcd che systemd-networkd (compatibilità Raspberry Pi)"""
    try:
        # Validazione indirizzi IP
        import ipaddress
        ipaddress.IPv4Address(ip_address)
        ipaddress.IPv4Address(gateway)
        if dns:
            for d in dns.split(','):
                ipaddress.IPv4Address(d.strip())
        
        netmask_decimal = _cidr_to_netmask(int(netmask))
        
        # Verifica quale backend di rete è in uso
        dhcpcd_active = False
        networkd_active = False
        
        try:
            result = subprocess.run(['sudo', 'systemctl', 'is-active', 'dhcpcd'], 
                                  capture_output=True, text=True, timeout=3)
            dhcpcd_active = result.returncode == 0
        except:
            pass
        
        try:
            result = subprocess.run(['sudo', 'systemctl', 'is-active', 'systemd-networkd'], 
                                  capture_output=True, text=True, timeout=3)
            networkd_active = result.returncode == 0
        except:
            pass
        
        print(f"[NETWORK] ℹ️  dhcpcd attivo: {dhcpcd_active}, systemd-networkd attivo: {networkd_active}")
        
        # ===== METODO 1: dhcpcd.conf (tradizionale Raspberry Pi) =====
        if dhcpcd_active:
            dhcpcd_conf = '/etc/dhcpcd.conf'
            try:
                # Leggi il file se esiste
                if os.path.exists(dhcpcd_conf):
                    with open(dhcpcd_conf, 'r') as f:
                        dhcpcd_content = f.read()
                else:
                    dhcpcd_content = ""
                
                # Rimuovi la sezione interface se esiste già
                import re
                dhcpcd_content = re.sub(
                    f'interface {interface}\n(?:.*\n)*?(?=\ninterface |$)',
                    '',
                    dhcpcd_content
                )
                
                # Aggiungi la nuova configurazione
                dhcpcd_config = f"\n# Configurazione IP statico per {interface}\ninterface {interface}\n"
                dhcpcd_config += f"    static ip_address={ip_address}/{netmask}\n"
                dhcpcd_config += f"    static routers={gateway}\n"
                dhcpcd_config += f"    static domain_name_servers={dns}\n"
                
                dhcpcd_content += dhcpcd_config
                
                # Scrivi il file temporaneo e copia con sudo
                config_file = '/tmp/dhcpcd.conf.new'
                with open(config_file, 'w') as f:
                    f.write(dhcpcd_content)
                
                subprocess.run(['sudo', 'cp', config_file, dhcpcd_conf], 
                              check=True, capture_output=True)
                print(f"[NETWORK] ✅ /etc/dhcpcd.conf aggiornato")
                
                # IMPORTANTE: Abilita il servizio
                subprocess.run(['sudo', 'systemctl', 'enable', 'dhcpcd'], 
                              capture_output=True, timeout=5)
                
                # Riavvia il servizio
                subprocess.run(['sudo', 'systemctl', 'restart', 'dhcpcd'], 
                              check=True, capture_output=True, timeout=10)
                print(f"[NETWORK] ✅ dhcpcd abilitato e riavviato")
            except Exception as e:
                print(f"[NETWORK] ❌ Errore aggiornamento dhcpcd.conf: {e}")
                raise
        
        # ===== METODO 2: systemd-networkd (Raspberry Pi Bookworm) =====
        elif networkd_active:
            try:
                systemd_config = f"""[Match]
Name={interface}

[Network]
Address={ip_address}/{netmask}
Gateway={gateway}
DNS={dns}
IPv6AcceptRA=no

[Route]
Destination=0.0.0.0/0
Gateway={gateway}
"""
                
                # Scrivi il file
                config_file = f'/tmp/99-{interface}-static.network'
                with open(config_file, 'w') as f:
                    f.write(systemd_config)
                
                # Applica il file
                target_file = f'/etc/systemd/network/99-{interface}-static.network'
                subprocess.run(['sudo', 'mkdir', '-p', '/etc/systemd/network'], 
                              capture_output=True)
                subprocess.run(['sudo', 'cp', config_file, target_file], 
                              check=True, capture_output=True)
                
                # Rimuovi eventuali configurazioni DHCP
                subprocess.run(['sudo', 'rm', '-f', f'/etc/systemd/network/99-{interface}-dhcp.network'], 
                              capture_output=True)
                
                print(f"[NETWORK] ✅ /etc/systemd/network aggiornato")
                
                # IMPORTANTE: Abilita il servizio
                subprocess.run(['sudo', 'systemctl', 'enable', 'systemd-networkd'], 
                              capture_output=True, timeout=5)
                
                # Riavvia il servizio
                subprocess.run(['sudo', 'systemctl', 'restart', 'systemd-networkd'], 
                              check=True, capture_output=True, timeout=10)
                print(f"[NETWORK] ✅ systemd-networkd abilitato e riavviato")
            except Exception as e:
                print(f"[NETWORK] ❌ Errore aggiornamento systemd-networkd: {e}")
                raise
        else:
            # Nessun servizio attivo: usa dhcpcd per compatibilità Raspberry Pi
            print(f"[NETWORK] ⚠️  Nessun servizio di rete attivo, utilizzo dhcpcd...")
            dhcpcd_conf = '/etc/dhcpcd.conf'
            try:
                # Leggi il file se esiste
                if os.path.exists(dhcpcd_conf):
                    with open(dhcpcd_conf, 'r') as f:
                        dhcpcd_content = f.read()
                else:
                    dhcpcd_content = ""
                
                # Rimuovi la sezione interface se esiste già
                import re
                dhcpcd_content = re.sub(
                    f'interface {interface}\n(?:.*\n)*?(?=\ninterface |$)',
                    '',
                    dhcpcd_content
                )
                
                # Aggiungi la nuova configurazione
                dhcpcd_config = f"\n# Configurazione IP statico per {interface}\ninterface {interface}\n"
                dhcpcd_config += f"    static ip_address={ip_address}/{netmask}\n"
                dhcpcd_config += f"    static routers={gateway}\n"
                dhcpcd_config += f"    static domain_name_servers={dns}\n"
                
                dhcpcd_content += dhcpcd_config
                
                # Scrivi il file temporaneo e copia con sudo
                config_file = '/tmp/dhcpcd.conf.new'
                with open(config_file, 'w') as f:
                    f.write(dhcpcd_content)
                
                subprocess.run(['sudo', 'cp', config_file, dhcpcd_conf], 
                              check=True, capture_output=True)
                
                # Abilita il servizio
                subprocess.run(['sudo', 'systemctl', 'enable', 'dhcpcd'], 
                              capture_output=True, timeout=5)
                subprocess.run(['sudo', 'systemctl', 'start', 'dhcpcd'], 
                              capture_output=True, timeout=5)
                print(f"[NETWORK] ✅ dhcpcd configurato e avviato")
            except Exception as e:
                print(f"[NETWORK] ❌ Errore configurazione dhcpcd: {e}")
                raise
        
        # Riavvia l'interfaccia di rete per applicare i cambiamenti
        print(f"[NETWORK] 🔄 Riavvio interfaccia {interface}...")
        try:
            subprocess.run(['sudo', 'ip', 'link', 'set', interface, 'down'], 
                          capture_output=True, timeout=5)
            time.sleep(2)
            subprocess.run(['sudo', 'ip', 'link', 'set', interface, 'up'], 
                          capture_output=True, timeout=5)
            print(f"[NETWORK] ✅ Interfaccia {interface} riavviata")
        except Exception as e:
            print(f"[NETWORK] ⚠️  Errore riavvio interfaccia: {e}")
        
        print(f"[NETWORK] ℹ️  IP statico configurato: {ip_address}/{netmask}, Gateway: {gateway}")
        return True
    except Exception as e:
        print(f"[NETWORK] ❌ Errore configurazione IP statico: {e}")
        raise



def set_dhcp(interface):
    """Configura DHCP sia su dhcpcd che systemd-networkd (compatibilità Raspberry Pi)"""
    try:
        # Verifica quale backend di rete è in uso
        dhcpcd_active = False
        networkd_active = False
        
        try:
            result = subprocess.run(['sudo', 'systemctl', 'is-active', 'dhcpcd'], 
                                  capture_output=True, text=True, timeout=3)
            dhcpcd_active = result.returncode == 0
        except:
            pass
        
        try:
            result = subprocess.run(['sudo', 'systemctl', 'is-active', 'systemd-networkd'], 
                                  capture_output=True, text=True, timeout=3)
            networkd_active = result.returncode == 0
        except:
            pass
        
        print(f"[NETWORK] ℹ️  dhcpcd attivo: {dhcpcd_active}, systemd-networkd attivo: {networkd_active}")
        
        # ===== METODO 1: dhcpcd.conf (tradizionale Raspberry Pi) =====
        if dhcpcd_active:
            dhcpcd_conf = '/etc/dhcpcd.conf'
            try:
                if os.path.exists(dhcpcd_conf):
                    with open(dhcpcd_conf, 'r') as f:
                        dhcpcd_content = f.read()
                    
                    # Rimuovi la sezione interface se esiste
                    import re
                    dhcpcd_content = re.sub(
                        f'interface {interface}\n(?:.*\n)*?(?=\ninterface |$)',
                        '',
                        dhcpcd_content
                    )
                    
                    # Scrivi il file senza la configurazione statica
                    config_file = '/tmp/dhcpcd.conf.new'
                    with open(config_file, 'w') as f:
                        f.write(dhcpcd_content)
                    
                    subprocess.run(['sudo', 'cp', config_file, dhcpcd_conf], 
                                  check=True, capture_output=True)
                    print(f"[NETWORK] ✅ /etc/dhcpcd.conf: configurazione statica rimossa")
                    
                    # IMPORTANTE: Abilita il servizio
                    subprocess.run(['sudo', 'systemctl', 'enable', 'dhcpcd'], 
                                  capture_output=True, timeout=5)
                    
                    # Riavvia il servizio
                    subprocess.run(['sudo', 'systemctl', 'restart', 'dhcpcd'], 
                                  check=True, capture_output=True, timeout=10)
                    print(f"[NETWORK] ✅ dhcpcd abilitato e riavviato")
            except Exception as e:
                print(f"[NETWORK] ❌ Errore aggiornamento dhcpcd.conf: {e}")
                raise
        
        # ===== METODO 2: systemd-networkd (Raspberry Pi Bookworm) =====
        elif networkd_active:
            try:
                # Crea configurazione per systemd-networkd
                systemd_config = f"""[Match]
Name={interface}

[Network]
DHCP=yes
IPv6AcceptRA=yes
"""
                
                # Scrivi il file
                config_file = f'/tmp/99-{interface}-dhcp.network'
                with open(config_file, 'w') as f:
                    f.write(systemd_config)
                
                # Applica il file
                target_file = f'/etc/systemd/network/99-{interface}-dhcp.network'
                subprocess.run(['sudo', 'mkdir', '-p', '/etc/systemd/network'], 
                              capture_output=True)
                subprocess.run(['sudo', 'cp', config_file, target_file], 
                              check=True, capture_output=True)
                
                # Rimuovi eventuali configurazioni statiche
                subprocess.run(['sudo', 'rm', '-f', f'/etc/systemd/network/99-{interface}-static.network'], 
                              capture_output=True)
                print(f"[NETWORK] ✅ /etc/systemd/network aggiornato")
                
                # IMPORTANTE: Abilita il servizio
                subprocess.run(['sudo', 'systemctl', 'enable', 'systemd-networkd'], 
                              capture_output=True, timeout=5)
                
                # Riavvia il servizio
                subprocess.run(['sudo', 'systemctl', 'restart', 'systemd-networkd'], 
                              check=True, capture_output=True, timeout=10)
                print(f"[NETWORK] ✅ systemd-networkd abilitato e riavviato")
            except Exception as e:
                print(f"[NETWORK] ❌ Errore aggiornamento systemd-networkd: {e}")
                raise
        else:
            # Nessun servizio attivo: usa dhcpcd per compatibilità Raspberry Pi
            print(f"[NETWORK] ⚠️  Nessun servizio di rete attivo, utilizzo dhcpcd...")
            dhcpcd_conf = '/etc/dhcpcd.conf'
            try:
                if os.path.exists(dhcpcd_conf):
                    with open(dhcpcd_conf, 'r') as f:
                        dhcpcd_content = f.read()
                    
                    # Rimuovi la sezione interface se esiste
                    import re
                    dhcpcd_content = re.sub(
                        f'interface {interface}\n(?:.*\n)*?(?=\ninterface |$)',
                        '',
                        dhcpcd_content
                    )
                    
                    # Scrivi il file senza la configurazione statica
                    config_file = '/tmp/dhcpcd.conf.new'
                    with open(config_file, 'w') as f:
                        f.write(dhcpcd_content)
                    
                    subprocess.run(['sudo', 'cp', config_file, dhcpcd_conf], 
                                  check=True, capture_output=True)
                
                # Abilita il servizio
                subprocess.run(['sudo', 'systemctl', 'enable', 'dhcpcd'], 
                              capture_output=True, timeout=5)
                subprocess.run(['sudo', 'systemctl', 'restart', 'dhcpcd'], 
                              check=True, capture_output=True, timeout=10)
                print(f"[NETWORK] ✅ dhcpcd abilitato e riavviato")
            except Exception as e:
                print(f"[NETWORK] ⚠️  Errore configurazione dhcpcd: {e}")
        
        # Riavvia l'interfaccia di rete per applicare i cambiamenti
        print(f"[NETWORK] 🔄 Riavvio interfaccia {interface}...")
        try:
            subprocess.run(['sudo', 'ip', 'link', 'set', interface, 'down'], 
                          capture_output=True, timeout=5)
            time.sleep(2)
            subprocess.run(['sudo', 'ip', 'link', 'set', interface, 'up'], 
                          capture_output=True, timeout=5)
            print(f"[NETWORK] ✅ Interfaccia {interface} riavviata")
        except Exception as e:
            print(f"[NETWORK] ⚠️  Errore riavvio interfaccia: {e}")
        
        print(f"[NETWORK] ℹ️  DHCP abilitato su {interface}")
        return True
    except Exception as e:
        print(f"[NETWORK] ❌ Errore configurazione DHCP: {e}")
        raise


# ═══════════════════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@app.route('/')
@login_required
def index():
    """Pagina principale"""
    devices = get_video_devices()
    return render_template('index.html', devices=devices)


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Pagina di login"""
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')

        if check_password(username, password):
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('index'))
        else:
            error = 'Username o password non validi'

    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    """Logout"""
    session.pop('logged_in', None)
    session.pop('username', None)
    return redirect(url_for('login'))


@app.route('/api/status')
@login_required
def api_status():
    """Restituisce lo stato corrente"""
    config = load_config()
    return jsonify({
        'mjpg_running': is_process_running('mjpg_streamer'),
        'rtsp_running': is_process_running('ffmpeg.*rtsp'),
        'system': get_system_info(),
        'config': config
    })




@app.route('/api/config')
@login_required
def api_config():
    """Restituisce la configurazione"""
    return jsonify(load_config())


@app.route('/api/settings/save', methods=['POST'])
@login_required
def api_settings_save():
    """Salva le impostazioni di autenticazione interfaccia web"""
    try:
        auth = load_auth()

        new_username = request.form.get('new_username', '').strip()
        new_password = request.form.get('new_password', '').strip()
        disable_auth_value = request.form.get('disable_auth', 'false').strip().lower()
        disable_auth = disable_auth_value == 'true'

        if new_username:
            auth['username'] = new_username

        if new_password:
            auth['password'] = hashlib.sha256(new_password.encode()).hexdigest()

        auth['enabled'] = not disable_auth

        save_auth(auth)
        print(f"[AUTH] Impostazioni salvate: username={new_username if new_username else 'invariato'}, disable_auth={disable_auth}, enabled={auth['enabled']}")
        return jsonify({'success': True})
    except Exception as e:
        print(f"[AUTH] ❌ Errore salvataggio: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/service/restart', methods=['POST'])
@login_required
def api_service_restart():
    """Riavvia il servizio stream-manager"""
    try:
        subprocess.Popen(['sudo', 'systemctl', 'restart', 'stream-manager'],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/system/reboot', methods=['POST'])
@login_required
def api_system_reboot():
    """Riavvia il sistema"""
    try:
        print(f"[SYSTEM] 🔄 Riavvio del dispositivo in corso...")
        subprocess.Popen(['sudo', 'shutdown', '-r', '+0'],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return jsonify({
            'success': True,
            'message': '🔄 Il dispositivo si riavvierà tra pochi secondi...'
        })
    except Exception as e:
        print(f"[SYSTEM] ❌ Errore riavvio: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/mjpg/start', methods=['POST'])
@login_required
def api_mjpg_start():
    """Avvia mjpg-streamer"""
    try:
        source_type = request.form.get('source_type', 'device')
        video_file = request.form.get('video_file', '')
        
        # Fix: il checkbox invia 'on' quando checked
        auth_enabled = request.form.get('auth_enabled') == 'on'
        
        config = {
            'device': request.form.get('device', '/dev/video0'),
            'resolution': request.form.get('resolution', '640x480'),
            'framerate': int(request.form.get('framerate', 15)),
            'quality': int(request.form.get('quality', 85)),
            'port': int(request.form.get('port', 8080)),
            'source_type': source_type,
            'auth_enabled': auth_enabled,
            'auth_username': request.form.get('auth_username', 'stream'),
            'auth_password': request.form.get('auth_password', 'stream')
        }

        if source_type == 'video':
            full_config = load_config()
            if not video_file:
                video_file = full_config.get('mjpg', {}).get('video_path', '')
            if video_file:
                config['video_path'] = video_file
                full_config['mjpg'] = full_config.get('mjpg', {})
                full_config['mjpg']['video_path'] = video_file
                save_config(full_config)

        stop_mjpg_streamer()
        start_mjpg_streamer(config)

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/mjpg/stop', methods=['POST'])
@login_required
def api_mjpg_stop():
    """Ferma mjpg-streamer"""
    stop_mjpg_streamer()
    return jsonify({'success': True})


@app.route('/api/mjpg/save', methods=['POST'])
@login_required
def api_mjpg_save():
    """Salva configurazione MJPG"""
    config = load_config()

    source_type = request.form.get('source_type', 'device')
    video_file = request.form.get('video_file', '')
    
    # Fix: il checkbox invia 'on' quando checked, altrimenti non invia nulla
    auth_enabled = request.form.get('auth_enabled') == 'on'

    config['mjpg'] = {
        'device': request.form.get('device', '/dev/video0'),
        'resolution': request.form.get('resolution', '640x480'),
        'framerate': int(request.form.get('framerate', 15)),
        'quality': int(request.form.get('quality', 85)),
        'port': int(request.form.get('port', 8080)),
        'autostart': request.form.get('autostart') == 'on',
        'source_type': source_type,
        'auth_enabled': auth_enabled,
        'auth_username': request.form.get('auth_username', 'stream'),
        'auth_password': request.form.get('auth_password', 'stream')
    }

    if source_type == 'video' and video_file:
        config['mjpg']['video_path'] = video_file

    save_config(config)
    return jsonify({'success': True})


@app.route('/api/rtsp/start', methods=['POST'])
@login_required
def api_rtsp_start():
    """Avvia stream RTSP"""
    try:
        source_type = request.form.get('source_type', 'device')
        video_file = request.form.get('video_file', '')
        
        # Fix: il checkbox invia 'on' quando checked
        auth_enabled = request.form.get('auth_enabled') == 'on'

        config = {
            'device': request.form.get('device', '/dev/video0'),
            'resolution': request.form.get('resolution', '640x480'),
            'framerate': int(request.form.get('framerate', 25)),
            'bitrate': request.form.get('bitrate', '1000k'),
            'port': int(request.form.get('port', 8554)),
            'source_type': source_type,
            'auth_enabled': auth_enabled,
            'auth_username': request.form.get('auth_username', 'stream'),
            'auth_password': request.form.get('auth_password', 'stream')
        }

        if source_type == 'video':
            full_config = load_config()
            if not video_file:
                video_file = full_config.get('rtsp', {}).get('video_path', '')
            if video_file:
                full_config['rtsp'] = full_config.get('rtsp', {})
                full_config['rtsp']['video_path'] = video_file
                save_config(full_config)

        stop_rtsp_stream()
        start_rtsp_stream(config)

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/rtsp/stop', methods=['POST'])
@login_required
def api_rtsp_stop():
    """Ferma stream RTSP"""
    stop_rtsp_stream()
    return jsonify({'success': True})


@app.route('/api/videos/list')
@login_required
def api_videos_list():
    """Lista dei video disponibili"""
    video_dir = os.path.join(APP_DIR, 'videos')
    if not os.path.exists(video_dir):
        os.makedirs(video_dir, exist_ok=True)
        return jsonify({'videos': []})

    videos = []
    for f in os.listdir(video_dir):
        if f.lower().endswith(('.mp4', '.avi', '.mkv', '.mov', '.mpg', '.mpeg')):
            path = os.path.join(video_dir, f)
            size = os.path.getsize(path)
            size_mb = size / (1024 * 1024)
            videos.append({
                'name': f,
                'path': path,
                'size': f"{size_mb:.1f} MB"
            })

    return jsonify({'videos': videos})


@app.route('/api/videos/upload', methods=['POST'])
@login_required
def api_videos_upload():
    """Upload di un video"""
    try:
        if 'video' not in request.files:
            return jsonify({'success': False, 'error': 'Nessun file selezionato'})

        file = request.files['video']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'Nome file vuoto'})

        allowed_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.mpg', '.mpeg'}
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in allowed_extensions:
            return jsonify({'success': False, 'error': 'Formato non supportato'})

        video_dir = os.path.join(APP_DIR, 'videos')
        os.makedirs(video_dir, exist_ok=True)

        filepath = os.path.join(video_dir, file.filename)
        file.save(filepath)

        return jsonify({'success': True, 'path': filepath})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/videos/delete', methods=['POST'])
@login_required
def api_videos_delete():
    """Elimina un video"""
    try:
        data = request.get_json()
        filename = data.get('filename', '')

        if not filename:
            return jsonify({'success': False, 'error': 'Nome file mancante'})

        video_dir = os.path.join(APP_DIR, 'videos')
        filepath = os.path.join(video_dir, filename)

        if not os.path.exists(filepath):
            return jsonify({'success': False, 'error': 'File non trovato'})

        if not filepath.startswith(video_dir):
            return jsonify({'success': False, 'error': 'Percorso non valido'})

        os.remove(filepath)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/rtsp/save', methods=['POST'])
@login_required
def api_rtsp_save():
    """Salva configurazione RTSP"""
    config = load_config()

    source_type = request.form.get('source_type', 'device')
    video_file = request.form.get('video_file', '')
    
    # Fix: il checkbox invia 'on' quando checked
    auth_enabled = request.form.get('auth_enabled') == 'on'

    config['rtsp'] = {
        'device': request.form.get('device', '/dev/video0'),
        'resolution': request.form.get('resolution', '640x480'),
        'framerate': int(request.form.get('framerate', 25)),
        'bitrate': request.form.get('bitrate', '1000k'),
        'port': int(request.form.get('port', 8554)),
        'autostart': request.form.get('autostart') == 'on',
        'source_type': source_type,
        'auth_enabled': auth_enabled,
        'auth_username': request.form.get('auth_username', 'stream'),
        'auth_password': request.form.get('auth_password', 'stream')
    }

    if source_type == 'video' and video_file:
        config['rtsp']['video_path'] = video_file
        config['rtsp']['loop'] = True

    save_config(config)
    return jsonify({'success': True})


@app.route('/api/network/info', methods=['GET'])
@login_required
def api_network_info():
    """Restituisce informazioni di rete"""
    try:
        hostname = get_hostname()
        network = get_network_info()
        return jsonify({
            'success': True,
            'hostname': hostname,
            'network': network
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/network/hostname', methods=['POST'])
@login_required
def api_network_hostname():
    """Cambia l'hostname"""
    try:
        new_hostname = request.form.get('hostname', '').strip()
        
        if not new_hostname:
            return jsonify({'success': False, 'error': 'Hostname non può essere vuoto'})
        
        set_hostname(new_hostname)
        
        return jsonify({
            'success': True,
            'message': f'Hostname cambiato in "{new_hostname}"',
            'hostname': new_hostname
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/network/ip/static', methods=['POST'])
@login_required
def api_network_static_ip():
    """Configura IP statico"""
    try:
        interface = request.form.get('interface', 'eth0').strip()
        ip_address = request.form.get('ip_address', '').strip()
        netmask = request.form.get('netmask', '24').strip()
        gateway = request.form.get('gateway', '').strip()
        dns = request.form.get('dns', '8.8.8.8').strip()
        
        if not all([interface, ip_address, gateway]):
            return jsonify({'success': False, 'error': 'Campi obbligatori: interfaccia, IP, gateway'})
        
        set_static_ip(interface, ip_address, netmask, gateway, dns)
        
        return jsonify({
            'success': True,
            'message': f'IP statico configurato: {ip_address}/{netmask}'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/network/ip/dhcp', methods=['POST'])
@login_required
def api_network_dhcp():
    """Configura DHCP"""
    try:
        interface = request.form.get('interface', 'eth0').strip()
        
        if not interface:
            return jsonify({'success': False, 'error': 'Interfaccia non specificata'})
        
        set_dhcp(interface)
        
        return jsonify({
            'success': True,
            'message': f'DHCP abilitato su {interface}'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/wifi/scan', methods=['GET'])
@login_required
def api_wifi_scan():
    """Scansiona le reti WiFi disponibili"""
    try:
        # Verifica se siamo in modalità hotspot
        is_hotspot_active = os.path.exists('/tmp/hotspot_active')
        hotspot_was_active = is_hotspot_active
        
        if is_hotspot_active:
            print(f"[WIFI] 📡 Hotspot attivo - disattivazione temporanea per scansione...")
            
            # Disattiva temporaneamente l'hotspot per permettere la scansione
            subprocess.run(['sudo', 'nmcli', 'connection', 'down', 'Hotspot-Fallback'],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            time.sleep(2)
            print(f"[WIFI] ✓ Hotspot disattivato temporaneamente")
        
        # Usa nmcli (NetworkManager) per scansione
        print(f"[WIFI] 🔍 Avvio scansione reti WiFi...")
        result = subprocess.run(['nmcli', 'dev', 'wifi', 'list', '--rescan', 'yes'], 
                              capture_output=True, text=True, timeout=20)
        
        networks = []
        
        # Parsing output nmcli - formato:
        # IN-USE  BSSID              SSID                  MODE   CHAN  RATE        SIGNAL  BARS  SECURITY
        lines = result.stdout.split('\n')
        for line in lines[1:]:  # Skip header
            if line.strip() and not line.startswith('IN-USE'):
                try:
                    # Parsing manuale basato su posizioni fisse
                    parts = line.split()
                    if len(parts) >= 6:
                        # Approccio: estrai BSSID (formato XX:XX:XX:XX:XX:XX) e signal
                        import re
                        
                        # Cerca BSSID
                        bssid_match = re.search(r'([0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2})', line)
                        if bssid_match:
                            bssid = bssid_match.group(1)
                            bssid_pos = line.find(bssid)
                            
                            # SSID è tra BSSID e MODE (Infra)
                            rest = line[bssid_pos + len(bssid):].strip()
                            
                            # Trova "Infra" per separare SSID dal resto
                            mode_pos = rest.find('Infra')
                            if mode_pos > 0:
                                ssid = rest[:mode_pos].strip()
                                rest_after_mode = rest[mode_pos:]
                                
                                
                                # Filtra SSID vuoti e il nostro hotspot
                                if ssid and ssid != '*' and ssid != 'videoStreamer':
                                    networks.append({
                                        'ssid': ssid,
                                        'bssid': bssid,
                                    })
                except Exception as parse_err:
                    print(f"[WIFI] ⚠️  Errore parsing riga: {parse_err}")
                    pass
        
        # Deduplicazione: tieni la rete con segnale più forte
        unique_networks = {}
        for net in networks:
            ssid = net['ssid']
            try:
                if ssid not in unique_networks:
                    unique_networks[ssid] = net
            except:
                if ssid not in unique_networks:
                    unique_networks[ssid] = net
        
        print(f"[WIFI] ✅ Trovate {len(unique_networks)} reti WiFi")
        
        # Riattiva l'hotspot se era attivo e non ci siamo connessi a nulla
        message = None
        if hotspot_was_active:
            if len(unique_networks) == 0:
                # Nessuna rete trovata, riattiva hotspot
                print(f"[WIFI] ⚠️  Nessuna rete trovata, riattivazione hotspot...")
                subprocess.run(['sudo', 'nmcli', 'connection', 'up', 'Hotspot-Fallback'],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
                message = "⚠️  Nessuna rete trovata. Hotspot riattivato."
            else:
                # Reti trovate, riattiva hotspot temporaneamente
                print(f"[WIFI] 🔄 Riattivazione hotspot (in attesa di connessione)...")
                subprocess.run(['sudo', 'nmcli', 'connection', 'up', 'Hotspot-Fallback'],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
                message = "ℹ️  Seleziona una rete per connetterti. L'hotspot verrà disattivato."
        
        return jsonify({
            'success': True,
            'networks': list(unique_networks.values()),
            'is_hotspot': hotspot_was_active,
            'message': message
        })
    except Exception as e:
        print(f"[WIFI] ❌ Errore scansione: {e}")
        # In caso di errore, prova a riattivare l'hotspot se era attivo
        if os.path.exists('/tmp/hotspot_active'):
            subprocess.run(['sudo', 'nmcli', 'connection', 'up', 'Hotspot-Fallback'],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/wifi/connect', methods=['POST'])
@login_required
def api_wifi_connect():
    """Connetti a una rete WiFi"""
    try:
        ssid = request.form.get('ssid', '').strip()
        password = request.form.get('password', '').strip()
        interface = request.form.get('interface', 'wlan0').strip()
        
        if not ssid:
            return jsonify({'success': False, 'error': 'SSID non specificato'})
        
        print(f"[WIFI] 🔄 Connessione a: {ssid}")
        
        # Prima rimuovi eventuali connessioni esistenti con lo stesso SSID
        print(f"[WIFI] Rimozione connessioni precedenti...")
        subprocess.run(['sudo', 'nmcli', 'connection', 'delete', ssid], 
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Usa nmcli per salvare la connessione WiFi
        if password:
            # Connessione con password WPA2
            cmd = [
                'sudo', 'nmcli', 'connection', 'add',
                'type', 'wifi',
                'ifname', interface,
                'con-name', ssid,
                'autoconnect', 'yes',
                'ssid', ssid,
                'wifi-sec.key-mgmt', 'wpa-psk',
                'wifi-sec.psk', password
            ]
            print(f"[WIFI] Comando: sudo nmcli connection add type wifi ifname {interface} con-name {ssid} ssid {ssid} wifi-sec.key-mgmt wpa-psk")
        else:
            # Connessione open (senza password)
            cmd = [
                'sudo', 'nmcli', 'connection', 'add',
                'type', 'wifi',
                'ifname', interface,
                'con-name', ssid,
                'autoconnect', 'yes',
                'ssid', ssid
            ]
            print(f"[WIFI] Comando: sudo nmcli connection add type wifi ifname {interface} con-name {ssid} ssid {ssid}")
        
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
        
        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Errore sconosciuto"
            print(f"[WIFI] ❌ Errore connessione: {error_msg}")
            return jsonify({'success': False, 'error': error_msg})
        
        print(f"[WIFI] ✅ Profilo creato: {ssid}")
        print(f"[WIFI] Output: {result.stdout.strip()}")
        
        # Attiva la connessione
        print(f"[WIFI] 🔄 Attivazione connessione...")
        activate_result = subprocess.run(
            ['sudo', 'nmcli', 'connection', 'up', ssid],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20
        )
        
        if activate_result.returncode != 0:
            error_msg = activate_result.stderr or activate_result.stdout or "Errore attivazione"
            print(f"[WIFI] ⚠️  Avviso attivazione: {error_msg}")
        else:
            print(f"[WIFI] ✅ Connessione attivata: {ssid}")
        
        # Disattiva hotspot se era attivo
        if os.path.exists('/tmp/hotspot_active'):
            print(f"[WIFI] 📡 Disattivazione hotspot...")
            subprocess.run(['sudo', 'nmcli', 'connection', 'down', 'Hotspot-Fallback'],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                os.remove('/tmp/hotspot_active')
            except:
                pass
        
        # Salva la configurazione di rete in un file per persistenza
        try:
            network_save_file = '/etc/videostreamer_wifi.conf'
            with open('/tmp/videostreamer_wifi.conf', 'w') as f:
                f.write(f"SSID={ssid}\n")
                f.write(f"PASSWORD={password}\n")
                f.write(f"INTERFACE={interface}\n")
            subprocess.run(['sudo', 'cp', '/tmp/videostreamer_wifi.conf', network_save_file],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"[WIFI] ✅ Configurazione salvata in {network_save_file}")
        except Exception as save_err:
            print(f"[WIFI] ⚠️  Avviso: non posso salvare config: {save_err}")
        
        # Avvia reboot dopo 3 secondi per applicare la configurazione
        print(f"[WIFI] 🔄 Reboot tra 3 secondi...")
        subprocess.Popen(['sudo', 'shutdown', '-r', '+0'], 
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        return jsonify({
            'success': True,
            'message': f'✅ Connessione salvata! Il dispositivo si riavvierà tra pochi secondi...'
        })
    except Exception as e:
        print(f"[WIFI] ❌ Eccezione: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/wifi/forget-all', methods=['POST'])
@login_required
def api_wifi_forget_all():
    """Cancella tutte le connessioni WiFi salvate"""
    try:
        print(f"[WIFI] 🗑️  Cancellazione di tutte le connessioni WiFi salvate...")
        
        # Cancella tutte le connessioni via nmcli
        result = subprocess.run(
            ['sudo', 'nmcli', 'connection', 'show'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10
        )
        
        connections = []
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                parts = line.split()
                if parts:
                    conn_name = parts[0]
                    if conn_name and conn_name != 'NAME':
                        connections.append(conn_name)
        
        deleted_count = 0
        for conn_name in connections:
            try:
                delete_result = subprocess.run(
                    ['sudo', 'nmcli', 'connection', 'delete', conn_name],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10
                )
                if delete_result.returncode == 0:
                    print(f"[WIFI] ✅ Eliminato profilo: {conn_name}")
                    deleted_count += 1
            except Exception as e:
                print(f"[WIFI] ⚠️  Errore eliminazione {conn_name}: {e}")
        
        # Cancella il file di configurazione se esiste
        try:
            subprocess.run(['sudo', 'rm', '-f', '/etc/videostreamer_wifi.conf'],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"[WIFI] ✅ File configurazione eliminato")
        except:
            pass
        
        # Cancella la cartella di NetworkManager
        try:
            subprocess.run(['sudo', 'rm', '-rf', '/etc/NetworkManager/system-connections/*'],
                          shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"[WIFI] ✅ Connessioni di sistema eliminate")
        except:
            pass
        
        print(f"[WIFI] ✅ Completato: {deleted_count} profili eliminati")
        return jsonify({
            'success': True,
            'message': f'✅ {deleted_count} connessioni WiFi eliminate. Tutte le reti salvate sono state rimosse.'
        })
    except Exception as e:
        print(f"[WIFI] ❌ Eccezione: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/wifi/disable-hotspot', methods=['POST'])
@login_required
def api_wifi_disable_hotspot():
    """Disattiva manualmente l'hotspot WiFi"""
    try:
        print(f"[WIFI] 🛑 Disattivazione hotspot manuale...")
        
        # Verifica se l'hotspot è attivo
        if not os.path.exists('/tmp/hotspot_active'):
            return jsonify({
                'success': False,
                'error': 'Hotspot non attivo'
            })
        
        # Disattiva l'hotspot usando NetworkManager
        subprocess.run(['sudo', 'nmcli', 'connection', 'down', 'Hotspot-Fallback'],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Rimuovi marker
        subprocess.run(['sudo', 'rm', '-f', '/tmp/hotspot_active'],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        print(f"[WIFI] ✅ Hotspot disattivato")
        return jsonify({
            'success': True,
            'message': 'Hotspot disattivato. NetworkManager cercherà connessioni WiFi salvate.'
        })
    except Exception as e:
        print(f"[WIFI] ❌ Errore: {e}")
        return jsonify({'success': False, 'error': str(e)})


def autostart_streams():
    """Avvia automaticamente gli stream configurati"""
    config = load_config()

    if config.get('mjpg', {}).get('autostart', False):
        try:
            print("🚀 Avvio automatico MJPG Streamer...")
            start_mjpg_streamer(config['mjpg'])
            print("✅ MJPG Streamer avviato")
        except Exception as e:
            print(f"❌ Errore avvio MJPG: {e}")

    if config.get('rtsp', {}).get('autostart', False):
        try:
            print("🚀 Avvio automatico RTSP Stream...")
            start_rtsp_stream(config['rtsp'])
            print("✅ RTSP Stream avviato")
        except Exception as e:
            print(f"❌ Errore avvio RTSP: {e}")


if __name__ == '__main__':
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)

    if not os.path.exists(AUTH_FILE):
        save_auth({
            'username': 'admin',
            'password': hashlib.sha256('admin'.encode()).hexdigest(),
            'enabled': True
        })
        print("⚠️  CREDENZIALI DEFAULT ATTIVE:")
        print("   Username interfaccia web: admin")
        print("   Password interfaccia web: admin")
        print("   Username stream: stream")
        print("   Password stream: stream")
        print("   CAMBIA LE PASSWORD DOPO IL PRIMO ACCESSO!")

    import time
    print("⏳ Attendo 5 secondi prima dell'avvio automatico...")
    time.sleep(5)
    autostart_streams()

    print("🌐 Avvio server web sulla porta 5000...")
    app.run(host='0.0.0.0', port=5000, debug=False)
