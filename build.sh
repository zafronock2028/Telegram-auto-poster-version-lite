#!/bin/bash

# Instalar dependencias
pip install -r requirements.txt

# Mensaje de verificación
echo "¡Build completado!"

# Iniciar la aplicación con 1 solo worker para evitar problemas
exec gunicorn --bind 0.0.0.0:$PORT --workers 1 fameviz_panel:app
