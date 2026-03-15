# Usa una imagen oficial de Python ligera
FROM python:3.12-slim

# Variables de entorno para Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Crea un usuario sin privilegios para mayor seguridad
RUN adduser --disabled-password --gecos "" vorak_user

# Define el directorio de trabajo
WORKDIR /app

# Instala las dependencias primero (aprovecha la caché de Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia el código de la aplicación
COPY . .

# Crea la carpeta para la base de datos y ajusta permisos
RUN mkdir -p /app/data && chown -R vorak_user:vorak_user /app

# Cambia al usuario sin privilegios
USER vorak_user

# Ejecuta la aplicación usando Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--workers", "1", "--threads", "4", "app:app"]