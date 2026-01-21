# vault_backend/settings/prod.py
from .base import *

VPS_IP = os.getenv("VPS_IP")

if not VPS_IP:
    raise ValueError("Falta configurar la variable VPS_IP en el archivo .env")

ALLOWED_HOSTS = [VPS_IP, 'localhost', '127.0.0.1']

CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "capacitor://localhost",
    "http://localhost",
    f"http://{VPS_IP}:8091", 
]

CSRF_TRUSTED_ORIGINS = [
    f'http://{VPS_IP}:8090',
    # También es vital agregarlo aquí para permitir el POST del login
    f"http://{VPS_IP}:8091", 
]

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

