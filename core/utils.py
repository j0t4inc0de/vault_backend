from cryptography.fernet import Fernet
import os
from django.conf import settings

def get_fernet():
    # Obtenemos la llave del entorno. 
    # Si no existe, usamos una por defecto SOLO para evitar errores, 
    # pero en producción esto debe estar configurado.
    key = os.environ.get('ENCRYPTION_KEY')
    if not key:
        raise ValueError("No se encontró la ENCRYPTION_KEY en el archivo .env")
    return Fernet(key)

def encrypt_text(text):
    if not text:
        return None
    f = get_fernet()
    # Fernet necesita bytes, así que convertimos el texto a bytes
    return f.encrypt(text.encode()).decode()

def decrypt_text(encrypted_text):
    if not encrypted_text:
        return None
    f = get_fernet()
    try:
        # Desencriptamos y convertimos de vuelta a texto
        return f.decrypt(encrypted_text.encode()).decode()
    except Exception:
        return "Error al desencriptar"