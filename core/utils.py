from cryptography.fernet import Fernet
import os
from django.conf import settings

def get_fernet():
    key = os.environ.get('ENCRYPTION_KEY')
    if not key:
        raise ValueError("No se encontró la ENCRYPTION_KEY en el archivo .env")
    return Fernet(key)

def encrypt_text(text):
    if not text:
        return None
    f = get_fernet()
    return f.encrypt(text.encode()).decode()

def decrypt_text(encrypted_text):
    if not encrypted_text:
        return None
    f = get_fernet()
    try:
        return f.decrypt(encrypted_text.encode()).decode()
    except Exception:
        return "Error al desencriptar"
    
def encrypt_bytes(data_bytes):
    f = get_fernet() # Ahora: Usa la misma lógica que el resto
    return f.encrypt(data_bytes)

def decrypt_bytes(encrypted_data_bytes):
    f = get_fernet() # Ahora: Usa la misma lógica que el resto
    return f.decrypt(encrypted_data_bytes)