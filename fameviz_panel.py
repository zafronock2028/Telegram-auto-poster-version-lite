from flask import Flask, render_template, request, session, redirect, url_for
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError
import random
import time
import asyncio

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_fuerte'  # Asegúrate de cambiar esto por tu clave real

# Almacenamiento temporal en memoria
verification_store = {}
SESSION_TTL = 300  # 5 minutos para códigos

def generate_verification_code():
    return str(random.randint(100000, 999999))

async def send_telegram_code(phone, api_id, api_hash, code):
    """Envía el código de verificación por Telegram (función asíncrona)"""
    client = TelegramClient(None, int(api_id), api_hash)
    await client.connect()
    await client.send_message(phone, f"🔑 Tu código de verificación para Famelees es: {code}\n\n⚠️ Válido por 5 minutos")
    await client.disconnect()

async def verify_telegram_login(phone, api_id, api_hash, code):
    """Verifica el código de Telegram (función asíncrona)"""
    client = TelegramClient(None, int(api_id), api_hash)
    await client.connect()
    await client.sign_in(phone, code)
    session_string = client.session.save() if client.session else ''
    await client.disconnect()
    return session_string

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        phone = request.form.get('phone')
        api_id = request.form.get('api_id')
        api_hash = request.form.get('api_hash')
        ref_link = request.form.get('ref_link')
        
        if not phone or not api_id or not api_hash:
            return render_template('index.html', error='Por favor complete todos los campos requeridos')
        
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
            # Ejecutar la función asíncrona desde un contexto síncrono
            asyncio.run(send_telegram_code(phone, api_id, api_hash, verification_code))
            
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
        return render_template('verify.html', error='La sesión ha expirado. Por favor inicie de nuevo', phone=phone)
    
    if request.method == 'POST':
        if request.form.get('resend'):
            # Generar nuevo código
            new_code = generate_verification_code()
            user_data['verification_code'] = new_code
            user_data['timestamp'] = time.time()
            
            try:
                asyncio.run(send_telegram_code(phone, user_data['api_id'], user_data['api_hash'], new_code))
                return render_template('verify.html', success='¡Nuevo código enviado!', phone=phone)
            except Exception as e:
                return render_template('verify.html', error=f'Error al reenviar código: {str(e)}', phone=phone)
        
        user_code = request.form.get('verification_code')
        if not user_code or len(user_code) != 6:
            return render_template('verify.html', error='Código inválido', phone=phone)
        
        if user_code != user_data['verification_code']:
            return render_template('verify.html', error='Código incorrecto', phone=phone)
        
        try:
            session_string = asyncio.run(verify_telegram_login(
                phone,
                user_data['api_id'],
                user_data['api_hash'],
                user_code
            ))
            
            session['user_data'] = {
                'phone': user_data['phone'],
                'api_id': user_data['api_id'],
                'api_hash': user_data['api_hash'],
                'ref_link': user_data.get('ref_link', ''),
                'session_string': session_string
            }
            
            del verification_store[phone]
            return redirect(url_for('panel'))
            
        except PhoneCodeInvalidError:
            return render_template('verify.html', error='Código inválido', phone=phone)
        except PhoneCodeExpiredError:
            return render_template('verify.html', error='Código expirado', phone=phone)
        except SessionPasswordNeededError:
            return render_template('verify.html', error='Se requiere verificación en dos pasos adicional', phone=phone)
        except Exception as e:
            return render_template('verify.html', error=f'Error de verificación: {str(e)}', phone=phone)
    
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
