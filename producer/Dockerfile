FROM python:3.11-slim

WORKDIR /app

# 1. Copiamos los requerimientos desde la nueva ruta relativa
COPY producer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2. Copiamos el contenido de producer a la raíz de /app
COPY producer/ .

# 3. COPIA CRÍTICA: Traemos la carpeta database al contenedor
COPY database/ ./database/

# Creamos el archivo para el healthcheck
RUN touch /tmp/producer_healthy

CMD ["python", "main.py"]