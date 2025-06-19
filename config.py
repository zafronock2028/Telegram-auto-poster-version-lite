import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'una_clave_secreta_muy_segura'
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
    SESSION_TTL = 300  # 5 minutos para códigos de verificación
