# vault_backend/settings/prod.py
from .base import *

DEBUG = False
VPS_IP = os.getenv("VPS_IP")

if not VPS_IP:
    raise ValueError("Falta configurar la variable VPS_IP en el archivo .env")

ALLOWED_HOSTS = [VPS_IP, 'localhost', '127.0.0.1']

CSRF_TRUSTED_ORIGINS = [f'http://{VPS_IP}:8090']

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'


CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",      # Tu Vue en desarrollo (Vite)
    "http://127.0.0.1:5173",
    "capacitor://localhost",      # Para la App Móvil (Android/iOS)
    "http://localhost",           # A veces requerido por Android
]