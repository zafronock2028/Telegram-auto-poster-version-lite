#!/bin/bash

# Instalar dependencias
pip install -r requirements.txt

# No necesitamos configuración adicional de Redis
echo "¡Sistema listo para iniciar!"

# Iniciar la aplicación
exec gunicorn --bind 0.0.0.0:$PORT fameviz_panel:app
