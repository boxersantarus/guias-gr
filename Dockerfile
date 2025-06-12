FROM python:3.9-slim

# Instalar ZBar y otras dependencias
RUN apt-get update && apt-get install -y libzbar-dev

# Crear directorio de trabajo
WORKDIR /app

# Copiar archivos de la aplicación
COPY . /app

# Instalar dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Iniciar la aplicación
CMD ["gunicorn", "app:app"]
