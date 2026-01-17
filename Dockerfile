# Dockerfile
FROM python:3.10-slim

# Instalar dependencias del sistema necesarias para Postgres
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Configurar directorio de trabajo
WORKDIR /app

# Copiar requirements e instalar librerías
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código del proyecto
COPY . .

# Comando para correr Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "vault_backend.wsgi:application"]