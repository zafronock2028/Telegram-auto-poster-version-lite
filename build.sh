#!/bin/bash

# Instalar dependencias
pip install -r requirements.txt

# Mensaje de verificación
echo "¡Build completado!"

# Iniciar la aplicación
exec gunicorn --bind 0.0.0.0:$PORT --worker-class gunicorn.workers.ggevent.GeventWorker --workers 1 fameviz_panel:app
