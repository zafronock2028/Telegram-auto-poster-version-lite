from flask import Flask, render_template, request, session, redirect, url_for
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

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'fallback_secret_key_1234567890')

# Almacenamiento temporal en memoria
verification_store = {}
SESSION_TTL = 300  # 5 minutos para códigos

def generate_verification_code():
    return str(random.randint(100000, 999999))

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
        return await client.send_code_request(phone)
    except ApiIdInvalidError:
        raise ValueError("Credenciales de API inválidas. Verifica tu API ID y API Hash en my.telegram.org")
    except PhoneNumberInvalidError:
        raise ValueError("Número de teléfono inválido. Asegúrate de incluir el código de país (ej: +584123456789)")
    except FloodWaitError as e:
        raise ValueError(f"Demasiados intentos. Por favor espera {e.seconds} segundos antes de intentar nuevamente")
    except Exception as e:
        raise RuntimeError(f"Error de Telegram: {str(e)}")

async def sign_in_with_code(client, code):
    """Inicia sesión con el código recibido"""
    try:
        await client.sign_in(code=code)
        return client.session.save()
    except SessionPasswordNeededError:
        raise ValueError("Se requiere verificación en dos pasos (contraseña adicional)")
    except PhoneCodeInvalidError:
        raise ValueError("Código inválido")
    except PhoneCodeExpiredError:
        raise ValueError("Código expirado")
    except Exception as e:
        raise RuntimeError(f"Error al iniciar sesión: {str(e)}")

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
        
        if not api_id:
            errors.append("API ID es requerido")
        
        if not api_hash:
            errors.append("API Hash es requerido")
        
        if errors:
            return render_template('index.html', error=" | ".join(errors))
        
        try:
            # Crear cliente y enviar código
            client = asyncio.run(create_telegram_client(api_id, api_hash))
            asyncio.run(send_telegram_code(client, phone))
            
            # Guardar datos temporalmente
            verification_store[phone] = {
                'phone': phone,
                'api_id': api_id,
                'api_hash': api_hash,
                'ref_link': ref_link,
                'client': client,
                'timestamp': time.time()
            }
            
            session['verification_phone'] = phone
            return redirect(url_for('verify_code'))
            
        except Exception as e:
            logger.error(f"Error al enviar código: {str(e)}")
            return render_template('index.html', error=f'Error al enviar código: {str(e)}')
    
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
            await user_data['client'].disconnect()
        except:
            pass
        del verification_store[phone]
        return render_template('verify.html', 
                              error='La sesión ha expirado. Por favor inicie de nuevo', 
                              phone=phone)
    
    if request.method == 'POST':
        if request.form.get('resend'):
            try:
                # Reenviar código
                asyncio.run(send_telegram_code(user_data['client'], phone))
                user_data['timestamp'] = time.time()
                return render_template('verify.html', 
                                      success='¡Nuevo código enviado!', 
                                      phone=phone)
            except Exception as e:
                logger.error(f"Error al reenviar código: {str(e)}")
                return render_template('verify.html', 
                                      error=f'Error al reenviar código: {str(e)}', 
                                      phone=phone)
        
        user_code = request.form.get('verification_code', '').strip()
        if not user_code or len(user_code) != 6 or not user_code.isdigit():
            return render_template('verify.html', 
                                  error='Código inválido (debe tener 6 dígitos)', 
                                  phone=phone)
        
        try:
            # Verificar el código
            session_string = asyncio.run(sign_in_with_code(
                user_data['client'],
                user_code
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
                await user_data['client'].disconnect()
            except:
                pass
            del verification_store[phone]
            
            # Redirigir al panel
            return redirect(url_for('panel'))
            
        except Exception as e:
            logger.error(f"Error de verificación: {str(e)}")
            return render_template('verify.html', 
                                  error=f'Error de verificación: {str(e)}', 
                                  phone=phone)
    
    return render_template('verify.html', phone=phone)

@app.route('/panel')
def panel():
    if 'user_data' not in session:
        return redirect(url_for('index'))
    
    # Aquí va la lógica de tu panel de control
    return render_template('panel.html', user=session['user_data'])

@app.route('/logout')
def logout():
    # Limpiar todas las sesiones
    for phone in list(verification_store.keys()):
        try:
            client = verification_store[phone]['client']
            asyncio.run(client.disconnect())
        except:
            pass
    verification_store.clear()
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
