from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError, 
    PhoneCodeInvalidError, 
    PhoneCodeExpiredError,
    ApiIdInvalidError,
    PhoneNumberInvalidError,
    FloodWaitError
)
import random
import time
import asyncio
import os
import logging
import threading
import re

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'fallback_secret_key_1234567890')

# Almacenamiento temporal en memoria
verification_store = {}
SESSION_TTL = 300  # 5 minutos para códigos

# Bucle de eventos por hilo
thread_local = threading.local()

def get_event_loop():
    if not hasattr(thread_local, "loop"):
        thread_local.loop = asyncio.new_event_loop()
    return thread_local.loop

def run_async(coro):
    loop = get_event_loop()
    return loop.run_until_complete(coro)

async def create_telegram_client(api_id, api_hash):
    """Crea y conecta un cliente de Telegram"""
    client = TelegramClient(
        session=None,
        api_id=int(api_id),
        api_hash=api_hash
    )
    await client.connect()
    return client

async def send_telegram_code(client, phone):
    """Envía el código de verificación por Telegram"""
    try:
        logger.info(f"Enviando código a: {phone}")
        
        # Forzar SMS en Render
        if 'RENDER' in os.environ:
            logger.info("Forzando SMS en entorno Render")
            return await client.send_code_request(phone, force_sms=True)
        
        # Intentar primero con método normal
        try:
            return await client.send_code_request(phone)
        except Exception as e:
            logger.warning(f"Error con método normal: {str(e)}. Reintentando con SMS...")
            return await client.send_code_request(phone, force_sms=True)
            
    except ApiIdInvalidError:
        error_msg = "Credenciales de API inválidas. Verifica tu API ID y API Hash en my.telegram.org"
        logger.error(error_msg)
        raise ValueError(error_msg)
    except PhoneNumberInvalidError:
        error_msg = "Número de teléfono inválido. Asegúrate de incluir el código de país (ej: +584123456789)"
        logger.error(error_msg)
        raise ValueError(error_msg)
    except FloodWaitError as e:
        error_msg = f"Demasiados intentos. Por favor espera {e.seconds} segundos antes de intentar nuevamente"
        logger.error(error_msg)
        raise ValueError(error_msg)
    except Exception as e:
        error_msg = f"Error de Telegram al enviar código: {str(e)}"
        logger.exception(error_msg)
        raise RuntimeError(error_msg)

async def sign_in_with_code(client, code, phone_code_hash):
    """Inicia sesión con el código recibido"""
    try:
        await client.sign_in(phone=client._phone, code=code, phone_code_hash=phone_code_hash)
        return client.session.save()
    except SessionPasswordNeededError:
        # Guardar en sesión que se requiere 2FA
        session['requires_2fa'] = True
        raise ValueError("Se requiere verificación en dos pasos (contraseña adicional)")
    except PhoneCodeInvalidError:
        raise ValueError("Código inválido")
    except PhoneCodeExpiredError:
        raise ValueError("Código expirado")
    except Exception as e:
        raise RuntimeError(f"Error al iniciar sesión: {str(e)}")

async def sign_in_with_2fa(client, password):
    """Inicia sesión con contraseña 2FA"""
    try:
        await client.sign_in(password=password)
        return client.session.save()
    except Exception as e:
        raise RuntimeError(f"Error en verificación 2FA: {str(e)}")

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        api_id = request.form.get('api_id', '').strip()
        api_hash = request.form.get('api_hash', '').strip()
        ref_link = request.form.get('ref_link', '').strip()
        
        # Validar campos
        errors = []
        if not phone:
            errors.append("El número de teléfono es requerido")
        elif not phone.startswith('+'):
            errors.append("El número debe incluir código de país (ej: +584123456789)")
        elif not re.match(r'^\+\d{8,15}$', phone):
            errors.append("Número de teléfono inválido")
        
        if not api_id:
            errors.append("API ID es requerido")
        elif not api_id.isdigit():
            errors.append("API ID debe ser numérico")
        
        if not api_hash:
            errors.append("API Hash es requerido")
        
        if errors:
            return render_template('index.html', error=" | ".join(errors))
        
        try:
            # Crear cliente y enviar código
            client = run_async(create_telegram_client(api_id, api_hash))
            sent_code = run_async(send_telegram_code(client, phone))
            
            # Guardar datos temporalmente
            verification_store[phone] = {
                'phone': phone,
                'api_id': api_id,
                'api_hash': api_hash,
                'ref_link': ref_link,
                'client': client,
                'phone_code_hash': sent_code.phone_code_hash,
                'timestamp': time.time()
            }
            
            session['verification_phone'] = phone
            return redirect(url_for('verify_code'))
            
        except Exception as e:
            logger.error(f"Error al enviar código: {str(e)}")
            return render_template('index.html', error=f'Error al iniciar sesión: {str(e)}')
    
    return render_template('index.html')

@app.route('/verify', methods=['GET', 'POST'])
def verify_code():
    phone = session.get('verification_phone')
    if not phone or phone not in verification_store:
        return redirect(url_for('index'))
    
    user_data = verification_store[phone]
    
    # Verificar expiración
    if time.time() - user_data['timestamp'] > SESSION_TTL:
        try:
            run_async(user_data['client'].disconnect())
        except:
            pass
        del verification_store[phone]
        return render_template('verify.html', 
                              error='La sesión ha expirado. Por favor inicie de nuevo', 
                              phone=phone)
    
    if request.method == 'POST':
        # Manejar reenvío de código
        if request.form.get('resend'):
            try:
                # Reenviar código
                sent_code = run_async(send_telegram_code(user_data['client'], phone))
                user_data['phone_code_hash'] = sent_code.phone_code_hash
                user_data['timestamp'] = time.time()
                return render_template('verify.html', 
                                      success='¡Nuevo código enviado!', 
                                      phone=phone)
            except Exception as e:
                logger.error(f"Error al reenviar código: {str(e)}")
                return render_template('verify.html', 
                                      error=f'Error al reenviar código: {str(e)}', 
                                      phone=phone)
        
        # Manejar verificación 2FA si es necesario
        if session.get('requires_2fa'):
            password = request.form.get('password')
            if not password:
                return render_template('verify.html', 
                                      error='Contraseña 2FA requerida', 
                                      phone=phone,
                                      requires_2fa=True)
            
            try:
                session_string = run_async(sign_in_with_2fa(
                    user_data['client'],
                    password
                ))
                
                # Guardar en sesión
                session['user_data'] = {
                    'phone': phone,
                    'api_id': user_data['api_id'],
                    'api_hash': user_data['api_hash'],
                    'ref_link': user_data.get('ref_link', ''),
                    'session_string': session_string
                }
                
                # Limpiar y desconectar cliente
                try:
                    run_async(user_data['client'].disconnect())
                except:
                    pass
                del verification_store[phone]
                session.pop('requires_2fa', None)
                
                # Redirigir al panel
                return redirect(url_for('panel'))
                
            except Exception as e:
                logger.error(f"Error 2FA: {str(e)}")
                return render_template('verify.html', 
                                      error=f'Error en verificación 2FA: {str(e)}', 
                                      phone=phone,
                                      requires_2fa=True)
        
        # Manejar código normal
        user_code = request.form.get('verification_code', '').strip()
        # Validar que el código sea de 5 dígitos
        if not user_code or len(user_code) != 5 or not user_code.isdigit():
            return render_template('verify.html', 
                                  error='Código inválido (debe tener 5 dígitos)', 
                                  phone=phone)
        
        try:
            # Verificar el código
            session_string = run_async(sign_in_with_code(
                user_data['client'],
                user_code,
                user_data['phone_code_hash']
            ))
            
            # Guardar en sesión
            session['user_data'] = {
                'phone': phone,
                'api_id': user_data['api_id'],
                'api_hash': user_data['api_hash'],
                'ref_link': user_data.get('ref_link', ''),
                'session_string': session_string
            }
            
            # Limpiar y desconectar cliente
            try:
                run_async(user_data['client'].disconnect())
            except:
                pass
            del verification_store[phone]
            
            # Redirigir al panel
            return redirect(url_for('panel'))
            
        except Exception as e:
            logger.error(f"Error de verificación: {str(e)}")
            
            # Verificar si es error de 2FA
            if "Se requiere verificación en dos pasos" in str(e):
                return render_template('verify.html', 
                                      error=str(e), 
                                      phone=phone,
                                      requires_2fa=True)
            
            return render_template('verify.html', 
                                  error=f'Error de verificación: {str(e)}', 
                                  phone=phone)
    
    return render_template('verify.html', phone=phone)

@app.route('/panel')
def panel():
    if 'user_data' not in session:
        return redirect(url_for('index'))
    
    # Aquí va la lógica de tu panel de control
    # EJEMPLO: datos dummy para pruebas
    return render_template('panel.html', 
                          user=session['user_data'],
                          publicando=False,
                          now=time.ctime(),
                          estado="Listo para publicar",
                          detalles=["Sistema inicializado ✅"],
                          total_grupos=15,
                          textos=enumerate(TEXTOS_PREDEFINIDOS),
                          imagenes=["imagen1.png", "imagen2.jpg"],
                          referral=session['user_data'].get('ref_link', ''),
                          mensaje_pub="Mensaje de prueba")

# Importar textos predefinidos
try:
    from fameviz_textos import TEXTOS_PREDEFINIDOS
except ImportError:
    TEXTOS_PREDEFINIDOS = ["Texto predeterminado {{codigo}}"]

@app.route('/logout')
def logout():
    # Limpiar todas las sesiones
    for phone in list(verification_store.keys()):
        try:
            client = verification_store[phone]['client']
            run_async(client.disconnect())
        except:
            pass
    verification_store.clear()
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
