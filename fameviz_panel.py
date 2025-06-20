from flask import Flask, render_template, request, session, redirect, url_for
from telethon import TelegramClient
from telethon.sync import sync  # Importar sync para manejar operaciones asíncronas
from telethon.errors import (
    SessionPasswordNeededError, 
    PhoneCodeInvalidError, 
    PhoneCodeExpiredError,
    ApiIdInvalidError,
    PhoneNumberInvalidError,
    FloodWaitError
)
import os
import logging
import time
import sys

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))

# Almacenamiento temporal en memoria
SESSION_TTL = 300  # 5 minutos para códigos

def send_telegram_code(api_id, api_hash, phone):
    """Envía el código de verificación por Telegram (SMS)"""
    try:
        logger.info(f"Enviando SMS a: {phone}")
        
        # Usamos sync para manejar la operación asíncrona
        client = sync(TelegramClient)(
            session=None,
            api_id=int(api_id),
            api_hash=api_hash
        )
        
        # FORZAR SMS SIEMPRE
        result = client.send_code_request(phone, force_sms=True)
        logger.info(f"Resultado de envío de SMS: {result}")
        
        return client, result.phone_code_hash
    except FloodWaitError as e:
        logger.error(f"FloodWait: Debes esperar {e.seconds} segundos")
        raise Exception(f"Demasiados intentos. Espera {e.seconds} segundos.")
    except PhoneNumberInvalidError:
        raise Exception("Número de teléfono inválido.")
    except Exception as e:
        logger.exception("Error crítico al enviar SMS")
        raise Exception(f"Error al enviar SMS: {str(e)}")

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        api_id = request.form.get('api_id', '').strip()
        api_hash = request.form.get('api_hash', '').strip()
        
        # Validación básica
        if not phone.startswith('+') or not api_id.isdigit() or not api_hash:
            return render_template('index.html', error='Datos inválidos. Asegúrate de usar un número con código de país (+...) y API válida.')
        
        try:
            client, phone_code_hash = send_telegram_code(api_id, api_hash, phone)
            
            # Guardar datos en sesión
            session['phone'] = phone
            session['api_id'] = api_id
            session['api_hash'] = api_hash
            session['phone_code_hash'] = phone_code_hash
            session['client_session'] = client.session.save()  # Guardar solo la sesión
            session['timestamp'] = time.time()
            
            return redirect('/verify')
            
        except Exception as e:
            return render_template('index.html', error=f'Error: {str(e)}')
    
    return render_template('index.html')

@app.route('/verify', methods=['GET', 'POST'])
def verify_code():
    # Verificar sesión
    if 'phone' not in session or time.time() - session.get('timestamp', 0) > SESSION_TTL:
        return redirect('/')
    
    phone = session['phone']
    
    if request.method == 'POST':
        # Manejar reenvío
        if 'resend' in request.form:
            try:
                client, phone_code_hash = send_telegram_code(
                    session['api_id'], 
                    session['api_hash'], 
                    phone
                )
                session['phone_code_hash'] = phone_code_hash
                session['timestamp'] = time.time()
                return render_template('verify.html', success='¡Nuevo código enviado!')
            except Exception as e:
                return render_template('verify.html', error=f'Error: {str(e)}')
        
        # Manejar código
        user_code = request.form.get('code', '').strip()
        if not user_code or len(user_code) != 5 or not user_code.isdigit():
            return render_template('verify.html', error='Código inválido. Debe tener 5 dígitos.')
        
        try:
            # Crear cliente y restaurar sesión usando sync
            client = sync(TelegramClient)(
                session=None,
                api_id=int(session['api_id']),
                api_hash=session['api_hash']
            )
            
            # Restaurar sesión
            client.session = TelegramClient.StringSession(session['client_session'])
            client.connect()
            
            # Verificar código usando sign_in de forma síncrona
            client.sign_in(
                phone=phone,
                code=user_code,
                phone_code_hash=session['phone_code_hash']
            )
            
            # Guardar sesión autenticada
            session['authenticated'] = True
            return redirect('/panel')
            
        except SessionPasswordNeededError:
            return render_template('verify.html', error='Tu cuenta tiene verificación en dos pasos (2FA). Esta función no está soportada actualmente.')
        except PhoneCodeInvalidError:
            return render_template('verify.html', error='Código inválido. Intenta nuevamente.')
        except PhoneCodeExpiredError:
            return render_template('verify.html', error='Código expirado. Solicita uno nuevo.')
        except Exception as e:
            logger.exception("Error en verificación de código")
            return render_template('verify.html', error=f'Error: {str(e)}')
    
    return render_template('verify.html')

@app.route('/panel')
def panel():
    if not session.get('authenticated'):
        return redirect('/')
    return render_template('panel.html', user=session['phone'])

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
