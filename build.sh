#!/bin/bash

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno si es necesario
if [ -z "$REDIS_URL" ]; then
    export REDIS_URL="redis://localhost:6379"
    echo "Advertencia: REDIS_URL no está definida, usando valor por defecto"
fi

# Iniciar la aplicación
exec gunicorn --bind 0.0.0.0:$PORT fameviz_panel:app
