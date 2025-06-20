#!/bin/bash

# Instalar dependencias
pip install -r requirements.txt

# Mensaje de verificación
echo "¡Build completado exitosamente!"

# Iniciar la aplicación con worker class correcta
exec gunicorn --bind 0.0.0.0:$PORT --worker-class gunicorn.workers.ggevent.GeventWorker --workers 4 fameviz_panel:app
