from .base import *

DEBUG = False
# Leemos la IP desde el archivo .env
VPS_IP = os.getenv("VPS_IP", "72.60.167.16")

# Permitimos la IP sola y la IP con el puerto
ALLOWED_HOSTS = [VPS_IP, 'localhost', '127.0.0.1']

# Importante: CSRF necesita el origen exacto (con puerto)
CSRF_TRUSTED_ORIGINS = [f'http://{VPS_IP}:8090']
