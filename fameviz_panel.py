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
import asyncio
import os
import logging
import time

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Almacenamiento temporal en memoria
verification_store = {}
SESSION_TTL = 300  # 5 minutos para códigos

def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

async def send_telegram_code_async(api_id, api_hash, phone):
    """Envía el código de verificación por Telegram (SMS)"""
    try:
        logger.info(f"Intentando enviar SMS a: {phone}")
        client = TelegramClient(None, int(api_id), api_hash)
        await client.connect()
        
        # FORZAR SMS SIEMPRE
        sent_code = await client.send_code_request(phone, force_sms=True)
        logger.info(f"Código SMS enviado a {phone}")
        
        return client, sent_code.phone_code_hash
    except Exception as e:
        logger.error(f"ERROR AL ENVIAR SMS: {str(e)}")
        raise

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        api_id = request.form.get('api_id', '').strip()
        api_hash = request.form.get('api_hash', '').strip()
        
        # Validación básica
        if not phone.startswith('+') or not api_id or not api_hash:
            return render_template('index.html', error='Datos inválidos')
        
        try:
            client, phone_code_hash = run_async(send_telegram_code_async(api_id, api_hash, phone))
            
            # Guardar datos en sesión
            session['phone'] = phone
            session['api_id'] = api_id
            session['api_hash'] = api_hash
            session['phone_code_hash'] = phone_code_hash
            session['client_session'] = client.session.save()  # Guardar solo la sesión
            session['timestamp'] = time.time()
            
            logger.info(f"Datos guardados para: {phone}")
            return redirect('/verify')
            
        except Exception as e:
            logger.error(f"ERROR EN INDEX: {str(e)}")
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
                logger.info(f"Reenviando SMS a: {phone}")
                client, phone_code_hash = run_async(send_telegram_code_async(
                    session['api_id'], 
                    session['api_hash'], 
                    phone
                ))
                session['phone_code_hash'] = phone_code_hash
                session['timestamp'] = time.time()
                return render_template('verify.html', success='¡Nuevo código enviado!')
            except Exception as e:
                logger.error(f"ERROR REENVIANDO SMS: {str(e)}")
                return render_template('verify.html', error=f'Error: {str(e)}')
        
        # Manejar código
        user_code = request.form.get('code', '').strip()
        if not user_code or len(user_code) != 5:
            return render_template('verify.html', error='Código inválido (5 dígitos)')
        
        try:
            logger.info(f"Verificando código para: {phone}")
            
            # Crear cliente y restaurar sesión
            client = TelegramClient(None, int(session['api_id']), session['api_hash'])
            client.session = TelegramClient.StringSession(session['client_session'])
            run_async(client.connect())
            
            # Verificar código
            run_async(client.sign_in(
                phone=phone,
                code=user_code,
                phone_code_hash=session['phone_code_hash']
            ))
            
            # Guardar sesión autenticada
            session['authenticated'] = True
            return redirect('/panel')
            
        except SessionPasswordNeededError:
            return render_template('verify.html', error='Cuenta con 2FA no soportada')
        except Exception as e:
            logger.error(f"ERROR VERIFICANDO CÓDIGO: {str(e)}")
            return render_template('verify.html', error=f'Error: {str(e)}')
    
    return render_template('verify.html')

@app.route('/panel')
def panel():
    if not session.get('authenticated'):
        return redirect('/')
    return render_template('panel.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)
