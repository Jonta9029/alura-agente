# Stage 1: Build dependencies
FROM python:3.11-slim as builder

WORKDIR /app

# Instalar dependencias del sistema necesarias para construir librerías de Python si hiciera falta
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Instalar dependencias en una carpeta local de wheels
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Final runtime image
FROM python:3.11-slim as runner

WORKDIR /app

# Crear un usuario no privilegiado para ejecutar la aplicación de forma segura
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -m -s /bin/bash appuser

# Copiar las dependencias instaladas en la fase anterior
COPY --from=builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

# Copiar el código fuente del proyecto
COPY --chown=appuser:appgroup src/ ./src/
COPY --chown=appuser:appgroup data/ ./data/

# Crear carpeta de logs y base de datos con permisos para el usuario
RUN mkdir -p logs && \
    touch alura_agente.db && \
    chown -R appuser:appgroup /app

# Cambiar al usuario no priviligiado
USER appuser

# Exponer el puerto de FastAPI
EXPOSE 8000

# Healthcheck de Docker para verificar la disponibilidad del servicio
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/api/health || exit 1

# Comando por defecto para arrancar la API con Uvicorn en producción
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
