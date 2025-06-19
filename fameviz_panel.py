from flask import Flask, render_template, request, session, redirect, url_for
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError
import random
import json
import time

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_fuerte'

# Almacenamiento temporal en memoria (sin Redis)
verification_store = {}
SESSION_TTL = 300  # 5 minutos para códigos

def generate_verification_code():
    return str(random.randint(100000, 999999))

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Obtener datos del formulario
        phone = request.form.get('phone')
        api_id = request.form.get('api_id')
        api_hash = request.form.get('api_hash')
        ref_link = request.form.get('ref_link')
        
        # Validar datos básicos
        if not phone or not api_id or not api_hash:
            return render_template('index.html', error='Por favor complete todos los campos requeridos')
        
        # Generar código de verificación
        verification_code = generate_verification_code()
        
        # Guardar datos temporalmente en memoria
        verification_store[phone] = {
            'phone': phone,
            'api_id': api_id,
            'api_hash': api_hash,
            'ref_link': ref_link,
            'verification_code': verification_code,
            'timestamp': time.time()
        }
        
        try:
            # Crear cliente de Telegram
            client = TelegramClient(None, int(api_id), api_hash)
            
            # Conectar y enviar código de verificación
            await client.connect()
            await client.send_message(phone, f"🔑 Tu código de verificación para Famelees es: {verification_code}\n\n⚠️ Válido por 5 minutos")
            await client.disconnect()
            
            # Redirigir a la página de verificación
            session['verification_phone'] = phone
            return redirect(url_for('verify_code'))
            
        except Exception as e:
            return render_template('index.html', error=f'Error al enviar código: {str(e)}')
    
    return render_template('index.html')

@app.route('/verify', methods=['GET', 'POST'])
def verify_code():
    phone = session.get('verification_phone')
    if not phone:
        return redirect(url_for('index'))
    
    # Verificar expiración de sesión
    if phone not in verification_store or time.time() - verification_store[phone]['timestamp'] > SESSION_TTL:
        return render_template('verify.html', error='La sesión ha expirado. Por favor inicie de nuevo', phone=phone)
    
    user_data = verification_store[phone]
    
    if request.method == 'POST':
        # Verificar si se solicita reenvío de código
        if 'resend' in request.form:
            # Generar nuevo código
            new_code = generate_verification_code()
            user_data['verification_code'] = new_code
            user_data['timestamp'] = time.time()
            verification_store[phone] = user_data
            
            try:
                # Reenviar el nuevo código
                client = TelegramClient(None, int(user_data['api_id']), user_data['api_hash'])
                await client.connect()
                await client.send_message(phone, f"🔄 Tu nuevo código de verificación es: {new_code}\n\n⚠️ Válido por 5 minutos")
                await client.disconnect()
                
                return render_template('verify.html', success='¡Nuevo código enviado!', phone=phone)
            
            except Exception as e:
                return render_template('verify.html', error=f'Error al reenviar código: {str(e)}', phone=phone)
        
        # Procesar verificación de código normal
        user_code = request.form.get('verification_code')
        if not user_code or len(user_code) != 6:
            return render_template('verify.html', error='Código inválido', phone=phone)
        
        # Verificar el código
        if user_code != user_data['verification_code']:
            return render_template('verify.html', error='Código incorrecto', phone=phone)
        
        try:
            # Crear sesión de Telegram
            client = TelegramClient(None, int(user_data['api_id']), user_data['api_hash'])
            await client.connect()
            
            # Verificar el código
            await client.sign_in(user_data['phone'], code=user_code)
            
            # Guardar datos de sesión
            session['user_data'] = {
                'phone': user_data['phone'],
                'api_id': user_data['api_id'],
                'api_hash': user_data['api_hash'],
                'ref_link': user_data.get('ref_link', ''),
                'session_string': client.session.save() if client.session else ''
            }
            
            await client.disconnect()
            
            # Eliminar datos temporales
            if phone in verification_store:
                del verification_store[phone]
            
            # Redirigir al panel de control
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
    # Puedes acceder a los datos del usuario con session['user_data']
    
    return render_template('panel.html', user=session['user_data'])

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
