#!/bin/bash

# Instalar dependencias
pip install -r requirements.txt

# Mensaje de verificación
echo "¡Build completado exitosamente!"

# Iniciar la aplicación
exec gunicorn --bind 0.0.0.0:$PORT --worker-class gevent --workers 4 fameviz_panel:app
