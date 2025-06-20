from flask import Flask, render_template, request, session, redirect, url_for
from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError, 
    PhoneCodeInvalidError, 
    PhoneCodeExpiredError,
    ApiIdInvalidError  # Nuevo: para manejar errores de API
)
import random
import time
import asyncio
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'fallback_secret_key')

# Almacenamiento temporal en memoria
verification_store = {}
SESSION_TTL = 300  # 5 minutos para códigos

def generate_verification_code():
    return str(random.randint(100000, 999999))

async def send_telegram_code(phone, api_id, api_hash, code):
    """Envía el código de verificación por Telegram"""
    try:
        client = TelegramClient(
            session=None,
            api_id=int(api_id),
            api_hash=api_hash
        )
        await client.connect()
        
        # Envía el código al propio número (usando el cliente)
        await client.send_code_request(phone)
        
        # Guardamos el cliente en la sesión para futura verificación
        return client
    except ApiIdInvalidError:
        raise ValueError("Credenciales de API inválidas. Verifica tu API ID y API Hash en my.telegram.org")
    except Exception as e:
        raise RuntimeError(f"Error de Telegram: {str(e)}")

async def sign_in_with_code(client, phone, code):
    """Inicia sesión con el código recibido"""
    try:
        await client.sign_in(
            phone=phone,
            code=code
        )
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
        phone = request.form.get('phone')
        api_id = request.form.get('api_id')
        api_hash = request.form.get('api_hash')
        ref_link = request.form.get('ref_link')
        
        # Validar número de teléfono
        if not phone.startswith('+'):
            return render_template('index.html', 
                                  error='El número debe incluir código de país (ej: +584123456789)')
        
        if not phone or not api_id or not api_hash:
            return render_template('index.html', 
                                  error='Por favor complete todos los campos requeridos')
        
        verification_code = generate_verification_code()
        
        # Guardar datos temporalmente
        verification_store[phone] = {
            'phone': phone,
            'api_id': api_id,
            'api_hash': api_hash,
            'ref_link': ref_link,
            'verification_code': verification_code,
            'timestamp': time.time()
        }
        
        try:
            # Intenta enviar el código
            client = asyncio.run(send_telegram_code(phone, api_id, api_hash, verification_code))
            
            # Guardar cliente temporal para verificación
            verification_store[phone]['client'] = client
            
            session['verification_phone'] = phone
            return redirect(url_for('verify_code'))
            
        except Exception as e:
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
        return render_template('verify.html', 
                              error='La sesión ha expirado. Por favor inicie de nuevo', 
                              phone=phone)
    
    if request.method == 'POST':
        if request.form.get('resend'):
            # Generar nuevo código
            new_code = generate_verification_code()
            user_data['verification_code'] = new_code
            user_data['timestamp'] = time.time()
            
            try:
                # Reenviar usando el mismo cliente
                await user_data['client'].send_code_request(phone)
                return render_template('verify.html', 
                                      success='¡Nuevo código enviado!', 
                                      phone=phone)
            except Exception as e:
                return render_template('verify.html', 
                                      error=f'Error al reenviar código: {str(e)}', 
                                      phone=phone)
        
        user_code = request.form.get('verification_code')
        if not user_code or len(user_code) != 6:
            return render_template('verify.html', 
                                  error='Código inválido (debe tener 6 dígitos)', 
                                  phone=phone)
        
        try:
            # Verificar el código
            session_string = asyncio.run(sign_in_with_code(
                user_data['client'],
                phone,
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
            
            # Limpiar almacenamiento temporal
            del verification_store[phone]
            
            # Redirigir al panel
            return redirect(url_for('panel'))
            
        except Exception as e:
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
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
