#!/usr/bin/env python3
"""
Script per cambiare username e password del Stream Manager
"""

import json
import hashlib
import os
import getpass

# Usa il percorso dinamico per qualsiasi utente (non hardcoded)
HOME_DIR = os.path.expanduser('~')
AUTH_FILE = os.path.join(HOME_DIR, 'stream_auth.json')

def load_auth():
    """Carica le credenziali"""
    if os.path.exists(AUTH_FILE):
        with open(AUTH_FILE, 'r') as f:
            return json.load(f)
    return None

def save_auth(auth_data):
    """Salva le credenziali"""
    with open(AUTH_FILE, 'w') as f:
        json.dump(auth_data, f, indent=2)

def main():
    print("=" * 50)
    print("  Stream Manager - Cambio Credenziali")
    print("=" * 50)
    print()
    
    auth = load_auth()
    if not auth:
        print("❌ File di autenticazione non trovato!")
        print("   Posizione attesa:", AUTH_FILE)
        return
    
    print(f"Username attuale: {auth.get('username', 'N/A')}")
    print(f"Autenticazione: {'Attiva' if auth.get('enabled', True) else 'Disattivata'}")
    print()
    
    # Cambio username
    print("Nuovo username (lascia vuoto per non cambiare):")
    new_username = input("> ").strip()
    if new_username:
        auth['username'] = new_username
        print(f"✅ Username cambiato in: {new_username}")
    
    # Cambio password
    print("\nNuova password (lascia vuoto per non cambiare):")
    new_password = getpass.getpass("> ")
    if new_password:
        print("Conferma password:")
        confirm_password = getpass.getpass("> ")
        
        if new_password == confirm_password:
            auth['password'] = hashlib.sha256(new_password.encode()).hexdigest()
            print("✅ Password cambiata con successo!")
        else:
            print("❌ Le password non corrispondono. Password non cambiata.")
    
    # Abilita/Disabilita autenticazione
    print("\nVuoi disabilitare l'autenticazione? (s/n - non consigliato):")
    disable = input("> ").lower().strip()
    if disable == 's':
        auth['enabled'] = False
        print("⚠️  Autenticazione DISABILITATA!")
    else:
        auth['enabled'] = True
        print("✅ Autenticazione attiva")
    
    # Salva
    save_auth(auth)
    print("\n✅ Modifiche salvate!")
    print("\nRiavvia il servizio per applicare le modifiche:")
    print("   sudo systemctl restart stream-manager")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Operazione annullata.")
    except Exception as e:
        print(f"\n❌ Errore: {e}")
