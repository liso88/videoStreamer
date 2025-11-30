#!/usr/bin/env python3
"""
Raspberry Pi Video Streaming Manager
Gestisce mjpg-streamer e FFmpeg/MediaMTX tramite interfaccia web
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

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)  # Genera una chiave segreta casuale

# File di configurazione (dinamici per qualsiasi utente)
HOME_DIR = os.path.expanduser('~')
CONFIG_FILE = os.path.join(HOME_DIR, 'stream_config.json')
AUTH_FILE = os.path.join(HOME_DIR, 'stream_auth.json')

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
        'source_type': 'device'  # 'device' o 'video'
    },
    'rtsp': {
        'enabled': False,
        'device': '/dev/video0',
        'resolution': '640x480',
        'framerate': 25,
        'bitrate': '1000k',
        'port': 8554,
        'autostart': False,
        'source_type': 'device'  # 'device' o 'video'
    },
    'video': {
        'path': os.path.join(HOME_DIR, 'stream_manager', 'videos', 'demo.mp4'),
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
    """Carica le credenziali di autenticazione"""
    if os.path.exists(AUTH_FILE):
        with open(AUTH_FILE, 'r') as f:
            return json.load(f)
    # Credenziali di default: admin/admin
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


def get_video_files():
    """Ottiene la lista dei video disponibili"""
    video_dir = os.path.join(HOME_DIR, 'stream_manager', 'videos')
    if not os.path.exists(video_dir):
        os.makedirs(video_dir, exist_ok=True)
        return []

    video_files = []
    for f in os.listdir(video_dir):
        if f.lower().endswith(('.mp4', '.avi', '.mkv', '.mov', '.mpg', '.mpeg')):
            video_files.append(os.path.join(video_dir, f))
    return video_files


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
    """Avvia mjpg-streamer"""
    source_type = config.get('source_type', 'device')

    if source_type == 'video':
        # Sorgente = file video (specifico per MJPG)
        full_config = load_config()
        video_path = full_config.get('mjpg', {}).get('video_path', '')

        if not os.path.exists(video_path):
            raise Exception(f"Video non trovato: {video_path}")

        # Cartella per i frame JPG
        frames_dir = '/tmp/mjpg_frames'
        os.makedirs(frames_dir, exist_ok=True)

        # Pulisci JPG vecchi
        for f in os.listdir(frames_dir):
            if f.lower().endswith(('.jpg', '.jpeg')):
                try:
                    os.remove(os.path.join(frames_dir, f))
                except:
                    pass

        # Avvia FFmpeg che genera JPEG nella cartella
        fps = config.get('framerate', 15)
        quality = config.get('quality', 85)
        qscale = max(1, min(31, quality // 3))  # 1=meglio, 31=peggio

        ffmpeg_cmd = [
            'ffmpeg',
            '-stream_loop', '-1',
            '-re', '-i', video_path,
            '-vf', f'fps={fps}',
            '-q:v', str(qscale),
            os.path.join(frames_dir, 'frame_%06d.jpg')
        ]
        subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        # Avvia mjpg-streamer che guarda la cartella di JPG
        mjpg_cmd = [
            '/usr/local/bin/mjpg_streamer',
            '-i', f'input_file.so -f {frames_dir} -d 0 -r',
            '-o', f"output_http.so -p {config['port']} -n"
        ]
    else:
        # Sorgente = dispositivo video USB
        mjpg_cmd = [
            '/usr/local/bin/mjpg_streamer',
            '-i', (
                f"input_uvc.so -d {config['device']} -r {config['resolution']} "
                f"-f {config['framerate']} -q {config['quality']}"
            ),
            '-o', f"output_http.so -p {config['port']} -n"
        ]

    subprocess.Popen(
        mjpg_cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    return True



def stop_mjpg_streamer():
    """Ferma mjpg-streamer"""
    subprocess.run(['pkill', '-f', 'mjpg_streamer'],
                   stderr=subprocess.DEVNULL)
    # Pulisci anche il processo FFmpeg se presente
    subprocess.run(['pkill', '-f', 'ffmpeg.*mjpg_fifo'],
                   shell=True, stderr=subprocess.DEVNULL)
    # Rimuovi named pipe se esiste
    fifo_path = '/tmp/mjpg_fifo'
    if os.path.exists(fifo_path):
        try:
            os.remove(fifo_path)
        except:
            pass
    return True


def start_rtsp_stream(config):
    """Avvia lo streaming RTSP con FFmpeg"""
    # Prima avvia MediaMTX se non è in esecuzione
    if not is_process_running('mediamtx'):
        subprocess.Popen(['mediamtx', '/etc/mediamtx/mediamtx.yml'],
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)

    source_type = config.get('source_type', 'device')

    if source_type == 'video':
        # Usa video file come sorgente (specifico per RTSP)
        full_config = load_config()
        video_path = full_config.get('rtsp', {}).get('video_path', '')

        if not os.path.exists(video_path):
            raise Exception(f"Video non trovato: {video_path}")

        # teniamo sempre il loop attivo
        loop_option = ['-stream_loop', '-1']

        cmd = [
            'ffmpeg'
        ] + loop_option + [
            '-re',
            '-i', video_path,
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-tune', 'zerolatency',
            '-b:v', config['bitrate'],
            '-s', config['resolution'],
            '-r', str(config['framerate']),
            '-f', 'rtsp',
            f"rtsp://localhost:{config['port']}/video"
        ]
    else:
        # Usa dispositivo video USB
        cmd = [
            'ffmpeg',
            '-f', 'v4l2',
            '-input_format', 'mjpeg',
            '-video_size', config['resolution'],
            '-framerate', str(config['framerate']),
            '-i', config['device'],
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-tune', 'zerolatency',
            '-b:v', config['bitrate'],
            '-f', 'rtsp',
            f"rtsp://localhost:{config['port']}/video"
        ]

    subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)
    return True



def stop_rtsp_stream():
    """Ferma lo streaming RTSP"""
    subprocess.run(['pkill', '-f', 'ffmpeg.*rtsp'],
                   shell=True, stderr=subprocess.DEVNULL)
    subprocess.run(['pkill', 'mediamtx'],
                   stderr=subprocess.DEVNULL)
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


# ───────────────────────────
# ROUTES
# ───────────────────────────

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
    """Salva le impostazioni di autenticazione"""
    try:
        auth = load_auth()

        new_username = request.form.get('new_username', '').strip()
        new_password = request.form.get('new_password', '').strip()
        disable_auth = request.form.get('disable_auth') == 'on'

        if new_username:
            auth['username'] = new_username

        if new_password:
            auth['password'] = hashlib.sha256(new_password.encode()).hexdigest()

        auth['enabled'] = not disable_auth

        save_auth(auth)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/mjpg/start', methods=['POST'])
@login_required
def api_mjpg_start():
    """Avvia mjpg-streamer"""
    try:
        source_type = request.form.get('source_type', 'device')
        video_file = request.form.get('video_file', '')

        config = {
            'device': request.form.get('device', '/dev/video0'),
            'resolution': request.form.get('resolution', '640x480'),
            'framerate': int(request.form.get('framerate', 15)),
            'quality': int(request.form.get('quality', 85)),
            'port': int(request.form.get('port', 8080)),
            'source_type': source_type
        }

        # Se usa video file, salva il path nella sezione MJPG
        if source_type == 'video':
            full_config = load_config()
            if not video_file:
                video_file = full_config.get('mjpg', {}).get('video_path', '')
            if video_file:
                full_config['mjpg'] = full_config.get('mjpg', {})
                full_config['mjpg']['video_path'] = video_file
                save_config(full_config)


        # Ferma eventuali istanze precedenti
        stop_mjpg_streamer()

        # Avvia
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

    config['mjpg'] = {
        'device': request.form.get('device', '/dev/video0'),
        'resolution': request.form.get('resolution', '640x480'),
        'framerate': int(request.form.get('framerate', 15)),
        'quality': int(request.form.get('quality', 85)),
        'port': int(request.form.get('port', 8080)),
        'autostart': request.form.get('autostart') == 'on',
        'source_type': source_type
    }

    if source_type == 'video' and video_file:
        config['mjpg']['video_path'] = video_file
        config['video']['loop'] = True

    save_config(config)
    return jsonify({'success': True})


@app.route('/api/rtsp/start', methods=['POST'])
@login_required
def api_rtsp_start():
    """Avvia stream RTSP"""
    try:
        source_type = request.form.get('source_type', 'device')
        video_file = request.form.get('video_file', '')

        config = {
            'device': request.form.get('device', '/dev/video0'),
            'resolution': request.form.get('resolution', '640x480'),
            'framerate': int(request.form.get('framerate', 25)),
            'bitrate': request.form.get('bitrate', '1000k'),
            'port': int(request.form.get('port', 8554)),
            'source_type': source_type
        }

        # Se usa video file, aggiorna il path nella config globale
        # Se usa video file, salva il path nella sezione RTSP
        if source_type == 'video':
            full_config = load_config()
            if not video_file:
                video_file = full_config.get('rtsp', {}).get('video_path', '')
            if video_file:
                full_config['rtsp'] = full_config.get('rtsp', {})
                full_config['rtsp']['video_path'] = video_file
                save_config(full_config)


        # Ferma eventuali istanze precedenti
        stop_rtsp_stream()

        # Avvia
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
    video_dir = os.path.join(HOME_DIR, 'stream_manager', 'videos')
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

        # Verifica estensione
        allowed_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.mpg', '.mpeg'}
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in allowed_extensions:
            return jsonify({'success': False, 'error': 'Formato non supportato'})

        # Salva il file
        video_dir = os.path.join(HOME_DIR, 'stream_manager', 'videos')
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

        video_dir = os.path.join(HOME_DIR, 'stream_manager', 'videos')
        filepath = os.path.join(video_dir, filename)

        if not os.path.exists(filepath):
            return jsonify({'success': False, 'error': 'File non trovato'})

        # Verifica che sia nella directory corretta (sicurezza)
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

    config['rtsp'] = {
        'device': request.form.get('device', '/dev/video0'),
        'resolution': request.form.get('resolution', '640x480'),
        'framerate': int(request.form.get('framerate', 25)),
        'bitrate': request.form.get('bitrate', '1000k'),
        'port': int(request.form.get('port', 8554)),
        'autostart': request.form.get('autostart') == 'on',
        'source_type': source_type
    }

    if source_type == 'video' and video_file:
        config['rtsp']['video_path'] = video_file
        config['video']['loop'] = True

    save_config(config)
    return jsonify({'success': True})


def autostart_streams():
    """Avvia automaticamente gli stream configurati"""
    config = load_config()

    # Avvia MJPG se configurato per autostart
    if config.get('mjpg', {}).get('autostart', False):
        try:
            print("🚀 Avvio automatico MJPG Streamer...")
            start_mjpg_streamer(config['mjpg'])
            print("✅ MJPG Streamer avviato")
        except Exception as e:
            print(f"❌ Errore avvio MJPG: {e}")

    # Avvia RTSP se configurato per autostart
    if config.get('rtsp', {}).get('autostart', False):
        try:
            print("🚀 Avvio automatico RTSP Stream...")
            start_rtsp_stream(config['rtsp'])
            print("✅ RTSP Stream avviato")
        except Exception as e:
            print(f"❌ Errore avvio RTSP: {e}")


if __name__ == '__main__':
    # Crea configurazione di default se non esiste
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)

    # Crea credenziali di default se non esistono
    if not os.path.exists(AUTH_FILE):
        save_auth({
            'username': 'admin',
            'password': hashlib.sha256('admin'.encode()).hexdigest(),
            'enabled': True
        })
        print("⚠️  CREDENZIALI DEFAULT ATTIVE:")
        print("   Username: admin")
        print("   Password: admin")
        print("   CAMBIA LA PASSWORD DOPO IL PRIMO ACCESSO!")

    # Avvia stream configurati per l'autostart
    import time
    print("⏳ Attendo 5 secondi prima dell'avvio automatico...")
    time.sleep(5)  # Attende che il sistema sia completamente avviato
    autostart_streams()

    # Avvia il server web
    print("🌐 Avvio server web sulla porta 5000...")
    app.run(host='0.0.0.0', port=5000, debug=False)
