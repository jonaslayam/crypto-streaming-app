# Usamos una imagen base ligera de Python
FROM python:3.12-slim

# Establecemos el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiamos primero el archivo de requisitos para aprovechar la caché de Docker
COPY processor/requirements.txt .

# Instalamos las dependencias.
# --no-cache-dir: reduce el tamaño de la imagen final.
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el contenido de processor a la raíz de /app
COPY processor/ .

# Copiamos la carpeta database al contenedor
COPY database/ ./database/

# Comando por defecto para ejecutar la aplicación cuando el contenedor se inicie
CMD ["python", "main.py"]
