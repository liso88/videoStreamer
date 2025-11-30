#!/usr/bin/env python3
"""
Raspberry Pi Video Streaming Manager
Gestisce mjpg-streamer e FFmpeg/MediaMTX tramite interfaccia web
"""

from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for
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
import os
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
        # Sorgente = file video
        full_config = load_config()
        video_config = full_config.get('video', {})
        video_path = video_config.get('path', '')

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
            #così metto il webserver di esempio
            #'-o', f"output_http.so -p {config['port']} -w /usr/local/share/mjpg-streamer/www"
            '-o', f"output_http.so -p {config['port']} -n"

        ]
    else:
        # Sorgente = dispositivo video USB
        mjpg_cmd = [
            '/usr/local/bin/mjpg_streamer',
            '-i', f"input_uvc.so -d {config['device']} -r {config['resolution']} "
                  f"-f {config['framerate']} -q {config['quality']}",
           # '-o', f"output_http.so -p {config['port']} -w /usr/local/share/mjpg-streamer/www"
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
        # Usa video file come sorgente
        video_config = load_config().get('video', {})
        video_path = video_config.get('path', '')
        
        if not os.path.exists(video_path):
            raise Exception(f"Video non trovato: {video_path}")
        
        loop_option = ['-stream_loop', '-1'] if video_config.get('loop', True) else []
        
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

# Template HTML Login
LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - Stream Manager</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .login-container {
            background: white;
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            width: 100%;
            max-width: 400px;
        }
        .login-header {
            text-align: center;
            margin-bottom: 30px;
        }
        .login-header h1 {
            color: #333;
            margin-bottom: 10px;
        }
        .login-header p {
            color: #666;
            font-size: 14px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        .form-group label {
            display: block;
            margin-bottom: 8px;
            color: #555;
            font-weight: 500;
        }
        .form-group input {
            width: 100%;
            padding: 12px;
            border: 2px solid #e5e7eb;
            border-radius: 8px;
            font-size: 16px;
            transition: border-color 0.3s;
        }
        .form-group input:focus {
            outline: none;
            border-color: #667eea;
        }
        .btn-login {
            width: 100%;
            padding: 14px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            transition: background 0.3s;
        }
        .btn-login:hover {
            background: #5568d3;
        }
        .error-message {
            background: #fee;
            color: #c33;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 20px;
            text-align: center;
        }
        .info-box {
            background: #f0f9ff;
            border-left: 4px solid #667eea;
            padding: 15px;
            margin-top: 20px;
            border-radius: 5px;
        }
        .info-box p {
            color: #555;
            font-size: 13px;
            margin: 5px 0;
        }
        .info-box strong {
            color: #667eea;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <div class="login-header">
            <h1>🎥 Stream Manager</h1>
            <p>Accedi per gestire i tuoi stream</p>
        </div>
        
        {% if error %}
        <div class="error-message">
            {{ error }}
        </div>
        {% endif %}
        
        <form method="POST">
            <div class="form-group">
                <label>Username</label>
                <input type="text" name="username" required autofocus>
            </div>
            
            <div class="form-group">
                <label>Password</label>
                <input type="password" name="password" required>
            </div>
            
            <button type="submit" class="btn-login">Accedi</button>
        </form>
        
        <div class="info-box">
            <p><strong>ℹ️ Credenziali di default:</strong></p>
            <p>Username: <strong>admin</strong></p>
            <p>Password: <strong>admin</strong></p>
            <p style="margin-top: 10px; font-size: 12px;">
                ⚠️ Cambia la password dopo il primo accesso!
            </p>
        </div>
    </div>
</body>
</html>
'''

# Template HTML
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Raspberry Pi Stream Manager</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        .header {
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            margin-bottom: 20px;
        }
        .header h1 {
            color: #333;
            margin-bottom: 10px;
        }
        .header-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        .btn-logout {
            padding: 8px 16px;
            background: #ef4444;
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 14px;
            cursor: pointer;
            text-decoration: none;
            display: inline-block;
        }
        .btn-logout:hover {
            background: #dc2626;
        }
        .btn-settings {
            padding: 8px 16px;
            background: #8b5cf6;
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 14px;
            cursor: pointer;
            text-decoration: none;
            display: inline-block;
            margin-left: 10px;
        }
        .btn-settings:hover {
            background: #7c3aed;
        }
        .system-info {
            display: flex;
            gap: 15px;
            margin-top: 15px;
        }
        .source-selector {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 15px;
        }
        .source-selector label {
            display: block;
            margin-bottom: 10px;
            font-weight: bold;
            color: #333;
        }
        .radio-group {
            display: flex;
            gap: 20px;
        }
        .radio-option {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .radio-option input[type="radio"] {
            width: auto;
        }
        .video-upload-section {
            background: #f0f9ff;
            padding: 15px;
            border-radius: 8px;
            margin-top: 10px;
            border: 2px dashed #667eea;
        }
        .video-list {
            margin-top: 10px;
            max-height: 150px;
            overflow-y: auto;
        }
        .video-item {
            padding: 8px;
            background: white;
            margin: 5px 0;
            border-radius: 5px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .info-card {
            background: #f8f9fa;
            padding: 10px 15px;
            border-radius: 8px;
            flex: 1;
        }
        .info-card label {
            font-size: 12px;
            color: #666;
            display: block;
        }
        .info-card .value {
            font-size: 20px;
            font-weight: bold;
            color: #667eea;
        }
        .stream-section {
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            margin-bottom: 20px;
        }
        .stream-section h2 {
            color: #333;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #667eea;
        }
        .status-badge {
            display: inline-block;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
            margin-left: 10px;
        }
        .status-running { background: #10b981; color: white; }
        .status-stopped { background: #ef4444; color: white; }
        .form-group {
            margin-bottom: 15px;
        }
        .form-group label {
            display: block;
            margin-bottom: 5px;
            color: #555;
            font-weight: 500;
        }
        .form-group input, .form-group select {
            width: 100%;
            padding: 10px;
            border: 2px solid #e5e7eb;
            border-radius: 8px;
            font-size: 14px;
            transition: border-color 0.3s;
        }
        .form-group input:focus, .form-group select:focus {
            outline: none;
            border-color: #667eea;
        }
        .form-row {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }
        .button-group {
            display: flex;
            gap: 10px;
            margin-top: 20px;
        }
        button {
            padding: 12px 25px;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s;
        }
        .btn-start {
            background: #10b981;
            color: white;
        }
        .btn-start:hover { background: #059669; }
        .btn-stop {
            background: #ef4444;
            color: white;
        }
        .btn-stop:hover { background: #dc2626; }
        .btn-save {
            background: #667eea;
            color: white;
        }
        .btn-save:hover { background: #5568d3; }
        .stream-preview {
            margin-top: 20px;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 8px;
        }
        .stream-url {
            background: white;
            padding: 10px;
            border-radius: 5px;
            font-family: monospace;
            margin-top: 10px;
            word-break: break-all;
        }
        .notification {
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 15px 20px;
            border-radius: 8px;
            color: white;
            font-weight: bold;
            box-shadow: 0 5px 15px rgba(0,0,0,0.3);
            z-index: 1000;
            display: none;
        }
        .notification.success { background: #10b981; }
        .notification.error { background: #ef4444; }
        .modal {
            display: none;
            position: fixed;
            z-index: 2000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.5);
        }
        .modal-content {
            background: white;
            margin: 10% auto;
            padding: 30px;
            border-radius: 15px;
            width: 90%;
            max-width: 500px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        }
        .modal-header {
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 2px solid #667eea;
        }
        .modal-header h2 {
            color: #333;
        }
        .close {
            color: #aaa;
            float: right;
            font-size: 28px;
            font-weight: bold;
            cursor: pointer;
        }
        .close:hover {
            color: #000;
        }
    </style>
</head>
<body>
    <div class="notification" id="notification"></div>
    
    <div class="container">
        <div class="header">
            <div class="header-top">
                <div>
                    <h1>🎥 Raspberry Pi Stream Manager</h1>
                    <p>Gestisci i tuoi stream video in modo semplice</p>
                </div>
                <div>
                    <a href="#" class="btn-settings" onclick="openSettingsModal(); return false;">⚙️ Impostazioni</a>
                    <a href="/logout" class="btn-logout">🚪 Esci</a>
                </div>
            </div>
            
            <div class="system-info">
                <div class="info-card">
                    <label>CPU</label>
                    <div class="value" id="cpu">--</div>
                </div>
                <div class="info-card">
                    <label>Memoria</label>
                    <div class="value" id="memory">--</div>
                </div>
                <div class="info-card">
                    <label>Temperatura</label>
                    <div class="value" id="temp">--</div>
                </div>
            </div>
        </div>

        <!-- MJPG Streamer Section -->
        <div class="stream-section">
            <h2>
                MJPG Streamer
                <span class="status-badge" id="mjpg-status">Fermo</span>
            </h2>
            
            <div class="source-selector">
                <label>🎬 Sorgente Video</label>
                <div class="radio-group">
                    <div class="radio-option">
                        <input type="radio" id="mjpg-source-device" name="mjpg-source" value="device" checked>
                        <label for="mjpg-source-device">📹 Dispositivo USB</label>
                    </div>
                    <div class="radio-option">
                        <input type="radio" id="mjpg-source-video" name="mjpg-source" value="video">
                        <label for="mjpg-source-video">🎥 File Video (Loop)</label>
                    </div>
                </div>
            </div>
            
            <form id="mjpg-form">
                <div class="form-row">
                    <div class="form-group" id="mjpg-device-group">
                        <label>Dispositivo Video</label>
                        <select name="device" id="mjpg-device">
                            {% for device in devices %}
                            <option value="{{ device }}">{{ device }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    <div class="form-group" id="mjpg-video-group" style="display:none;">
                        <label>File Video</label>
                        <select name="video_file" id="mjpg-video-file">
                            <option value="">Carica un video...</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Dispositivo Video</label>
                        <select name="device" id="mjpg-device">
                            {% for device in devices %}
                            <option value="{{ device }}">{{ device }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Risoluzione</label>
                        <select name="resolution">
                            <option value="320x240">320x240</option>
                            <option value="640x480" selected>640x480</option>
                            <option value="800x600">800x600</option>
                            <option value="1280x720">1280x720</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Framerate (fps)</label>
                        <input type="number" name="framerate" value="15" min="1" max="30">
                    </div>
                    <div class="form-group">
                        <label>Qualità (0-100)</label>
                        <input type="number" name="quality" value="85" min="0" max="100">
                    </div>
                    <div class="form-group">
                        <label>Porta HTTP</label>
                        <input type="number" name="port" value="8080" min="1024" max="65535">
                    </div>
                </div>
                
                <div class="video-upload-section" id="mjpg-upload-section" style="display:none;">
                    <label><strong>📤 Carica Video</strong></label>
                    <p style="font-size: 12px; color: #666; margin: 5px 0;">
                        Formati supportati: MP4, AVI, MKV, MOV, MPG
                    </p>
                    <input type="file" id="mjpg-video-upload" accept="video/*" style="margin-top: 10px;">
                    <button type="button" class="btn-save" onclick="uploadVideo('mjpg')" style="margin-top: 10px;">
                        ⬆️ Carica Video
                    </button>
                    
                    <div class="video-list" id="mjpg-video-list"></div>
                </div>
                
                <div class="video-upload-section" id="rtsp-upload-section" style="display:none;">
                    <label><strong>📤 Carica Video</strong></label>
                    <p style="font-size: 12px; color: #666; margin: 5px 0;">
                        Formati supportati: MP4, AVI, MKV, MOV, MPG
                    </p>
                    <input type="file" id="rtsp-video-upload" accept="video/*" style="margin-top: 10px;">
                    <button type="button" class="btn-save" onclick="uploadVideo('rtsp')" style="margin-top: 10px;">
                        ⬆️ Carica Video
                    </button>
                    
                    <div class="video-list" id="rtsp-video-list"></div>
                </div>
                
                <div class="form-group">
                    <label style="display: flex; align-items: center; gap: 10px;">
                        <input type="checkbox" name="autostart" id="mjpg-autostart" style="width: auto;">
                        <span>Avvio automatico al boot del Raspberry</span>
                    </label>
                </div>
                
                <div class="button-group">
                    <button type="button" class="btn-start" onclick="startMJPG()">▶ Avvia</button>
                    <button type="button" class="btn-stop" onclick="stopMJPG()">⏹ Ferma</button>
                    <button type="button" class="btn-save" onclick="saveMJPGConfig()">💾 Salva Config</button>
                </div>
            </form>
            
            <div class="stream-preview">
                <strong>URL Stream:</strong>
                <div class="stream-url" id="mjpg-url">http://[IP_RASPBERRY]:8080</div>
            </div>
        </div>

        <!-- RTSP Stream Section -->
        <div class="stream-section">
            <h2>
                RTSP Stream (FFmpeg)
                <span class="status-badge" id="rtsp-status">Fermo</span>
            </h2>
            
            <div class="source-selector">
                <label>🎬 Sorgente Video</label>
                <div class="radio-group">
                    <div class="radio-option">
                        <input type="radio" id="rtsp-source-device" name="rtsp-source" value="device" checked>
                        <label for="rtsp-source-device">📹 Dispositivo USB</label>
                    </div>
                    <div class="radio-option">
                        <input type="radio" id="rtsp-source-video" name="rtsp-source" value="video">
                        <label for="rtsp-source-video">🎥 File Video (Loop)</label>
                    </div>
                </div>
            </div>
            
            <form id="rtsp-form">
                <div class="form-row">
                    <div class="form-group" id="rtsp-device-group">
                        <label>Dispositivo Video</label>
                        <select name="device" id="rtsp-device">
                            {% for device in devices %}
                            <option value="{{ device }}">{{ device }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    <div class="form-group" id="rtsp-video-group" style="display:none;">
                        <label>File Video</label>
                        <select name="video_file" id="rtsp-video-file">
                            <option value="">Carica un video...</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Dispositivo Video</label>
                        <select name="device" id="rtsp-device">
                            {% for device in devices %}
                            <option value="{{ device }}">{{ device }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Risoluzione</label>
                        <select name="resolution">
                            <option value="320x240">320x240</option>
                            <option value="640x480" selected>640x480</option>
                            <option value="800x600">800x600</option>
                            <option value="1280x720">1280x720</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Framerate (fps)</label>
                        <input type="number" name="framerate" value="25" min="1" max="30">
                    </div>
                    <div class="form-group">
                        <label>Bitrate</label>
                        <select name="bitrate">
                            <option value="500k">500 kbps</option>
                            <option value="1000k" selected>1 Mbps</option>
                            <option value="2000k">2 Mbps</option>
                            <option value="4000k">4 Mbps</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Porta RTSP</label>
                        <input type="number" name="port" value="8554" min="1024" max="65535">
                    </div>
                </div>
                
                <div class="form-group">
                    <label style="display: flex; align-items: center; gap: 10px;">
                        <input type="checkbox" name="autostart" id="rtsp-autostart" style="width: auto;">
                        <span>Avvio automatico al boot del Raspberry</span>
                    </label>
                </div>
                
                <div class="button-group">
                    <button type="button" class="btn-start" onclick="startRTSP()">▶ Avvia</button>
                    <button type="button" class="btn-stop" onclick="stopRTSP()">⏹ Ferma</button>
                    <button type="button" class="btn-save" onclick="saveRTSPConfig()">💾 Salva Config</button>
                </div>
            </form>
            
            <div class="stream-preview">
                <strong>URL Stream RTSP:</strong>
                <div class="stream-url" id="rtsp-url">rtsp://[IP_RASPBERRY]:8554/video</div>
                <p style="margin-top: 10px; color: #666; font-size: 14px;">
                    💡 Usa VLC o altro player RTSP per visualizzare lo stream
                </p>
            </div>
        </div>
    </div>

    <!-- Modal Impostazioni -->
    <div id="settingsModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <span class="close" onclick="closeSettingsModal()">&times;</span>
                <h2>⚙️ Impostazioni</h2>
            </div>
            
            <form id="settings-form">
                <div class="form-group">
                    <label>Nuovo Username</label>
                    <input type="text" name="new_username" placeholder="Lascia vuoto per non cambiare">
                </div>
                
                <div class="form-group">
                    <label>Nuova Password</label>
                    <input type="password" name="new_password" placeholder="Lascia vuoto per non cambiare">
                </div>
                
                <div class="form-group">
                    <label>Conferma Password</label>
                    <input type="password" name="confirm_password" placeholder="Conferma la nuova password">
                </div>
                
                <div class="form-group">
                    <label style="display: flex; align-items: center; gap: 10px;">
                        <input type="checkbox" name="disable_auth" id="disable-auth" style="width: auto;">
                        <span>Disabilita autenticazione (non consigliato)</span>
                    </label>
                </div>
                
                <div class="button-group">
                    <button type="button" class="btn-save" onclick="saveSettings()">💾 Salva Impostazioni</button>
                </div>
            </form>
        </div>
    </div>

    <script>
        // Gestione sorgente video MJPG
        document.querySelectorAll('input[name="mjpg-source"]').forEach(radio => {
            radio.addEventListener('change', function() {
                const deviceGroup = document.getElementById('mjpg-device-group');
                const videoGroup = document.getElementById('mjpg-video-group');
                const uploadSection = document.getElementById('mjpg-upload-section');
                
                if (this.value === 'device') {
                    deviceGroup.style.display = 'block';
                    videoGroup.style.display = 'none';
                    uploadSection.style.display = 'none';
                } else {
                    deviceGroup.style.display = 'none';
                    videoGroup.style.display = 'block';
                    uploadSection.style.display = 'block';
                    loadVideoList('mjpg');
                }
            });
        });
        
        // Gestione sorgente video RTSP
        document.querySelectorAll('input[name="rtsp-source"]').forEach(radio => {
            radio.addEventListener('change', function() {
                const deviceGroup = document.getElementById('rtsp-device-group');
                const videoGroup = document.getElementById('rtsp-video-group');
                const uploadSection = document.getElementById('rtsp-upload-section');
                
                if (this.value === 'device') {
                    deviceGroup.style.display = 'block';
                    videoGroup.style.display = 'none';
                    uploadSection.style.display = 'none';
                } else {
                    deviceGroup.style.display = 'none';
                    videoGroup.style.display = 'block';
                    uploadSection.style.display = 'block';
                    loadVideoList('rtsp');
                }
            });
        });
        
        // Carica lista video
        function loadVideoList(type) {
            fetch('/api/videos/list')
                .then(r => r.json())
                .then(data => {
                    const select = document.getElementById(`${type}-video-file`);
                    const list = document.getElementById(`${type}-video-list`);
                    
                    // Aggiorna select
                    select.innerHTML = '<option value="">Seleziona un video...</option>';
                    data.videos.forEach(video => {
                        const option = document.createElement('option');
                        option.value = video.path;
                        option.textContent = video.name;
                        select.appendChild(option);
                    });
                    
                    // Aggiorna lista
                    list.innerHTML = '';
                    data.videos.forEach(video => {
                        const item = document.createElement('div');
                        item.className = 'video-item';
                        item.innerHTML = `
                            <span>🎬 ${video.name} (${video.size})</span>
                            <button onclick="deleteVideo('${video.name}')" style="background:#ef4444;color:white;border:none;padding:5px 10px;border-radius:5px;cursor:pointer;">🗑️</button>
                        `;
                        list.appendChild(item);
                    });
                });
        }
        
        // Upload video
        function uploadVideo(type) {
            const fileInput = document.getElementById(`${type}-video-upload`);
            const file = fileInput.files[0];
            
            if (!file) {
                showNotification('Seleziona un file video', 'error');
                return;
            }
            
            const formData = new FormData();
            formData.append('video', file);
            
            showNotification('Caricamento in corso...', 'success');
            
            fetch('/api/videos/upload', {
                method: 'POST',
                body: formData
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    showNotification('Video caricato con successo!', 'success');
                    fileInput.value = '';
                    loadVideoList(type);
                } else {
                    showNotification('Errore: ' + data.error, 'error');
                }
            });
        }
        
        // Elimina video
        function deleteVideo(filename) {
            if (!confirm(`Eliminare il video "${filename}"?`)) return;
            
            fetch('/api/videos/delete', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({filename: filename})
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    showNotification('Video eliminato', 'success');
                    loadVideoList('mjpg');
                    loadVideoList('rtsp');
                } else {
                    showNotification('Errore: ' + data.error, 'error');
                }
            });
        }
        
        // Aggiorna lo stato ogni 2 secondi
        setInterval(updateStatus, 2000);
        updateStatus();
        
        function updateStatus() {
            fetch('/api/status')
                .then(r => r.json())
                .then(data => {
                    // Aggiorna badge status
                    updateBadge('mjpg-status', data.mjpg_running);
                    updateBadge('rtsp-status', data.rtsp_running);
                    
                    // Aggiorna info di sistema
                    document.getElementById('cpu').textContent = data.system.cpu.toFixed(1) + '%';
                    document.getElementById('memory').textContent = data.system.memory.toFixed(1) + '%';
                    document.getElementById('temp').textContent = data.system.temperature.toFixed(1) + '°C';
                    
                    // Aggiorna URL
                    const hostname = window.location.hostname;
                    document.getElementById('mjpg-url').textContent = `http://${hostname}:${data.config.mjpg.port}`;
                    document.getElementById('rtsp-url').textContent = `rtsp://${hostname}:${data.config.rtsp.port}/video`;
                });
        }
        
        function updateBadge(id, running) {
            const badge = document.getElementById(id);
            if (running) {
                badge.textContent = 'In Esecuzione';
                badge.className = 'status-badge status-running';
            } else {
                badge.textContent = 'Fermo';
                badge.className = 'status-badge status-stopped';
            }
        }
        
        function showNotification(message, type) {
            const notif = document.getElementById('notification');
            notif.textContent = message;
            notif.className = `notification ${type}`;
            notif.style.display = 'block';
            setTimeout(() => notif.style.display = 'none', 3000);
        }
        
        function startMJPG() {
            const form = document.getElementById('mjpg-form');
            const data = new FormData(form);
            
            // Aggiungi tipo sorgente
            const sourceType = document.querySelector('input[name="mjpg-source"]:checked').value;
            data.append('source_type', sourceType);
            
            fetch('/api/mjpg/start', {
                method: 'POST',
                body: data
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    showNotification('MJPG Streamer avviato con successo!', 'success');
                    updateStatus();
                } else {
                    showNotification('Errore: ' + data.error, 'error');
                }
            });
        }
        
        function stopMJPG() {
            fetch('/api/mjpg/stop', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    showNotification('MJPG Streamer fermato', 'success');
                    updateStatus();
                });
        }
        
        function saveMJPGConfig() {
            const form = document.getElementById('mjpg-form');
            const data = new FormData(form);
            
            // Aggiungi tipo sorgente
            const sourceType = document.querySelector('input[name="mjpg-source"]:checked').value;
            data.append('source_type', sourceType);
            
            fetch('/api/mjpg/save', {
                method: 'POST',
                body: data
            })
            .then(r => r.json())
            .then(data => {
                showNotification('Configurazione salvata!', 'success');
            });
        }
        
        function startRTSP() {
            const form = document.getElementById('rtsp-form');
            const data = new FormData(form);
            
            // Aggiungi tipo sorgente
            const sourceType = document.querySelector('input[name="rtsp-source"]:checked').value;
            data.append('source_type', sourceType);
            
            fetch('/api/rtsp/start', {
                method: 'POST',
                body: data
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    showNotification('Stream RTSP avviato con successo!', 'success');
                    updateStatus();
                } else {
                    showNotification('Errore: ' + data.error, 'error');
                }
            });
        }
        
        function stopRTSP() {
            fetch('/api/rtsp/stop', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    showNotification('Stream RTSP fermato', 'success');
                    updateStatus();
                });
        }
        
        function saveRTSPConfig() {
            const form = document.getElementById('rtsp-form');
            const data = new FormData(form);
            
            // Aggiungi tipo sorgente
            const sourceType = document.querySelector('input[name="rtsp-source"]:checked').value;
            data.append('source_type', sourceType);
            
            fetch('/api/rtsp/save', {
                method: 'POST',
                body: data
            })
            .then(r => r.json())
            .then(data => {
                showNotification('Configurazione salvata!', 'success');
            });
        }
        
        function openSettingsModal() {
            document.getElementById('settingsModal').style.display = 'block';
        }
        
        function closeSettingsModal() {
            document.getElementById('settingsModal').style.display = 'none';
        }
        
        function saveSettings() {
            const form = document.getElementById('settings-form');
            const data = new FormData(form);
            
            const newPassword = data.get('new_password');
            const confirmPassword = data.get('confirm_password');
            
            if (newPassword && newPassword !== confirmPassword) {
                showNotification('Le password non corrispondono!', 'error');
                return;
            }
            
            fetch('/api/settings/save', {
                method: 'POST',
                body: data
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    showNotification('Impostazioni salvate! Effettua nuovamente il login.', 'success');
                    setTimeout(() => {
                        window.location.href = '/logout';
                    }, 2000);
                } else {
                    showNotification('Errore: ' + (data.error || 'Errore sconosciuto'), 'error');
                }
            });
        }
        
        // Carica configurazione al caricamento pagina
        window.onload = function() {
            fetch('/api/config')
                .then(r => r.json())
                .then(config => {
                    // Popola form MJPG
                    const mjpgForm = document.getElementById('mjpg-form');
                    mjpgForm.elements['device'].value = config.mjpg.device;
                    mjpgForm.elements['resolution'].value = config.mjpg.resolution;
                    mjpgForm.elements['framerate'].value = config.mjpg.framerate;
                    mjpgForm.elements['quality'].value = config.mjpg.quality;
                    mjpgForm.elements['port'].value = config.mjpg.port;
                    document.getElementById('mjpg-autostart').checked = config.mjpg.autostart || false;
                    
                    // Popola form RTSP
                    const rtspForm = document.getElementById('rtsp-form');
                    rtspForm.elements['device'].value = config.rtsp.device;
                    rtspForm.elements['resolution'].value = config.rtsp.resolution;
                    rtspForm.elements['framerate'].value = config.rtsp.framerate;
                    rtspForm.elements['bitrate'].value = config.rtsp.bitrate;
                    rtspForm.elements['port'].value = config.rtsp.port;
                    document.getElementById('rtsp-autostart').checked = config.rtsp.autostart || false;
                });
        };
    </script>
</body>
</html>
'''

@app.route('/')
@login_required
def index():
    """Pagina principale"""
    devices = get_video_devices()
    return render_template_string(HTML_TEMPLATE, devices=devices)

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
    
    return render_template_string(LOGIN_TEMPLATE, error=error)

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
        
        # Se usa video file, aggiorna il path nella config globale
        if source_type == 'video':
            full_config = load_config()
            if not video_file:
                video_file = full_config.get('video', {}).get('path', '')
            if video_file:
                full_config['video'] = full_config.get('video', {})
                full_config['video']['path'] = video_file
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
        config['video'] = config.get('video', {})
        config['video']['path'] = video_file
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
        if source_type == 'video':
            full_config = load_config()
            if not video_file:
                video_file = full_config.get('video', {}).get('path', '')
            if video_file:
                full_config['video'] = full_config.get('video', {})
                full_config['video']['path'] = video_file
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
        config['video'] = config.get('video', {})
        config['video']['path'] = video_file
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