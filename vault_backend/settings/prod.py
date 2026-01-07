from .base import *

DEBUG = False
# Leemos la IP desde el archivo .env
VPS_IP = os.getenv("VPS_IP")

# Si por alguna razón no existe la variable, usamos una lista vacía o fallamos
if VPS_IP:
    ALLOWED_HOSTS = [VPS_IP, 'localhost', '127.0.0.1']
    CSRF_TRUSTED_ORIGINS = [f'http://{VPS_IP}']
else:
    # Fallback por seguridad o para debug
    ALLOWED_HOSTS = ['localhost', '127.0.0.1']
    CSRF_TRUSTED_ORIGINS = []
