#!/bin/bash

# Instalar dependencias
pip install -r requirements.txt

# Iniciar la aplicación
exec gunicorn --bind 0.0.0.0:$PORT fameviz_panel:app
