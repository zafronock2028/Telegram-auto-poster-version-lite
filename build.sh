#!/bin/bash

# Actualizar pip y herramientas de compilación
python -m pip install --upgrade pip wheel setuptools

# Instalar dependencias
pip install -r requirements.txt
