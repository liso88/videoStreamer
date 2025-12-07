#!/bin/bash
# ==================================================
# Funzioni helper comuni per script bash
# Uso: source bash_helpers.sh
# ==================================================

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Contatore step
STEP_COUNT=0
TOTAL_STEPS=0

# ==================================================
# HELPER: Inizializza contatore step
# ==================================================
init_steps() {
    TOTAL_STEPS=$1
    STEP_COUNT=0
}

# ==================================================
# HELPER: Stampa step formattato
# ==================================================
print_step() {
    local message=$1
    ((STEP_COUNT++))
    echo -e "${BLUE}[${STEP_COUNT}/${TOTAL_STEPS}]${NC} ${message}"
}

# ==================================================
# HELPER: Stampa successo
# ==================================================
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# ==================================================
# HELPER: Stampa errore
# ==================================================
print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# ==================================================
# HELPER: Stampa avviso
# ==================================================
print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# ==================================================
# HELPER: Stampa header
# ==================================================
print_header() {
    echo -e "${BLUE}===============================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}===============================================${NC}"
    echo ""
}

# ==================================================
# HELPER: Verifica che non sia root
# ==================================================
check_not_root() {
    if [ "$EUID" -eq 0 ]; then 
        print_error "Non eseguire questo script come root!"
        echo "Usa: bash $(basename $0)"
        exit 1
    fi
}

# ==================================================
# HELPER: Esegui comando con error checking
# ==================================================
run_cmd() {
    local cmd=$1
    local error_msg=${2:-"Comando fallito: $cmd"}
    
    if ! eval "$cmd"; then
        print_error "$error_msg"
        exit 1
    fi
}

# ==================================================
# HELPER: Esegui comando sudo
# ==================================================
run_sudo() {
    local cmd=$1
    local error_msg=${2:-"Comando sudo fallito"}
    
    if ! eval "sudo $cmd"; then
        print_error "$error_msg"
        exit 1
    fi
}

# ==================================================
# HELPER: Scarica file con verifica
# ==================================================
download_file() {
    local url=$1
    local output=$2
    local error_msg=${3:-"Download fallito"}
    
    if ! wget -q "$url" -O "$output"; then
        print_error "$error_msg: $url"
        exit 1
    fi
}

# ==================================================
# HELPER: Estrai archivio
# ==================================================
extract_archive() {
    local file=$1
    local dest=${2:-.}
    local error_msg=${3:-"Estrazione fallita"}
    
    if [[ "$file" == *.tar.gz ]]; then
        tar -xzf "$file" -C "$dest"
    elif [[ "$file" == *.tar.bz2 ]]; then
        tar -xjf "$file" -C "$dest"
    elif [[ "$file" == *.zip ]]; then
        unzip -q "$file" -d "$dest"
    else
        print_error "Formato archivio non supportato: $file"
        return 1
    fi
}

# ==================================================
# HELPER: Crea file systemd service
# ==================================================
create_systemd_service() {
    local service_name=$1
    local description=$2
    local exec_start=$3
    local user=${4:-$USER}
    local working_dir=${5:-$HOME}
    
    local service_file="/etc/systemd/system/${service_name}.service"
    
    sudo tee "$service_file" > /dev/null <<EOF
[Unit]
Description=$description
After=network.target

[Service]
Type=simple
User=$user
WorkingDirectory=$working_dir
ExecStart=$exec_start
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable "${service_name}.service"
    print_success "Service $service_name creato e abilitato"
}

# ==================================================
# HELPER: Crea file da heredoc con sudo
# ==================================================
create_file_sudo() {
    local file=$1
    local content=$3
    shift 2
    
    sudo tee "$file" > /dev/null "$@" <<EOF
$content
EOF
}

# ==================================================
# HELPER: Verifica dipendenza comando
# ==================================================
check_command() {
    local cmd=$1
    if ! command -v "$cmd" &> /dev/null; then
        print_error "Comando richiesto non trovato: $cmd"
        exit 1
    fi
}

# ==================================================
# HELPER: Cleanup e exit
# ==================================================
cleanup_exit() {
    local exit_code=${1:-0}
    if [ $exit_code -eq 0 ]; then
        print_header "INSTALLAZIONE COMPLETATA ✓"
    else
        print_error "INSTALLAZIONE FALLITA!"
    fi
    exit $exit_code
}

export -f print_step print_success print_error print_warning print_header
export -f check_not_root run_cmd run_sudo download_file extract_archive
export -f create_systemd_service create_file_sudo check_command cleanup_exit
export -f init_steps
