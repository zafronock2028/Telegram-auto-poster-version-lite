# fameviz_panel.py
import os
import re
import time
import asyncio
import logging
from flask import Flask, render_template, request, redirect, url_for, session, send_file
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.types import ChatBannedRights

# Configuración inicial
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'fameviz_secret_key_2024'
app.config['SESSION_FILE'] = 'fameviz_session.txt'
app.config['REFERRAL_FILE'] = 'referral_link.txt'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['FAMEVIZ_IMAGES'] = 'static/fameviz_images'
app.config['HISTORIAL_GRUPOS'] = 'grupos_unidos.txt'
app.config['HISTORIAL_PUBLICACIONES'] = 'historial_publicaciones.txt'

# Palabras prohibidas para validación
PALABRAS_PROHIBIDAS = [
    'binance', 'amazon', 'otro', 'oferta', 'crypto', 'bitcoin', 'ethereum',
    'nft', 'forex', 'trading', 'inversión', 'comision', 'cripto', 'cryptomoneda',
    'coinbase', 'kucoin', 'paypal', 'airtm', 'payoneer', 'transferencia', 'cambio'
]

# Crear directorios necesarios
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['FAMEVIZ_IMAGES'], exist_ok=True)

# Variables globales
estado_actual = "Inactivo"
progreso_detalles = []
mensaje_publicacion = ""
imagen_publicacion = ""
publicando = False
panel_activo = True

# Textos predefinidos (se cargan desde fameviz_textos.py)
from fameviz_textos import TEXTOS_PREDEFINIDOS

# Funciones auxiliares
def cargar_referral():
    if os.path.exists(app.config['REFERRAL_FILE']):
        with open(app.config['REFERRAL_FILE'], 'r') as f:
            return f.read().strip()
    return ""

def cargar_grupos_publicables():
    grupos = []
    if not os.path.exists(app.config['HISTORIAL_GRUPOS']):
        return grupos
        
    try:
        with open(app.config['HISTORIAL_GRUPOS'], 'r', encoding='utf-8') as f:
            for line in f.readlines():
                partes = line.strip().split(' | ')
                if len(partes) < 3:
                    continue
                nombre, enlace, estado = partes[0], partes[1], partes[2]
                if estado in ["Unido", "Ya estaba unido", "Solicitud enviada"]:
                    grupos.append((nombre, enlace))
        return grupos
    except Exception as e:
        logger.error(f"Error cargando grupos publicables: {e}")
        return []

def guardar_publicacion(grupo, estado):
    with open(app.config['HISTORIAL_PUBLICACIONES'], 'a', encoding='utf-8') as f:
        f.write(f"{grupo[0]} | {grupo[1]} | {estado} | {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

async def verificar_permisos(client, grupo):
    try:
        full = await client(GetFullChannelRequest(grupo))
        rights = full.full_chat.default_banned_rights
        return not rights.send_messages and not rights.send_media
    except Exception as e:
        logger.error(f"Error verificando permisos: {e}")
        return False

def validar_texto(texto):
    texto = texto.lower()
    for palabra in PALABRAS_PROHIBIDAS:
        if palabra in texto:
            return False
    return True

def obtener_imagenes_disponibles():
    imagenes = []
    for file in os.listdir(app.config['FAMEVIZ_IMAGES']):
        if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
            imagenes.append(file)
    return imagenes

# Funciones principales
async def publicar_en_grupos_internal():
    global estado_actual, progreso_detalles, mensaje_publicacion, imagen_publicacion, publicando, panel_activo
    
    try:
        if not panel_activo:
            return
        
        publicando = True
        progreso_detalles = []
        estado_actual = "Preparando publicación..."
        progreso_detalles.append("Iniciando proceso de publicación...")
        
        # Validar texto final
        if not validar_texto(mensaje_publicacion):
            progreso_detalles.append("❌ ERROR: El texto contiene palabras prohibidas")
            estado_actual = "Publicación bloqueada - Contenido no permitido"
            publicando = False
            return
            
        # Verificar sesión
        if not os.path.exists(app.config['SESSION_FILE']):
            progreso_detalles.append("❌ Error: Sesión no configurada")
            estado_actual = "Error: Sesión no configurada"
            publicando = False
            return
            
        session_str = open(app.config['SESSION_FILE']).read().strip()
        client = TelegramClient(StringSession(session_str), "", "")
        await client.start()
        
        grupos = cargar_grupos_publicables()
        total_publicados = 0
        total_grupos = len(grupos)
        
        if total_grupos == 0:
            estado_actual = "No hay grupos disponibles para publicar"
            progreso_detalles.append("⚠️ No se encontraron grupos válidos para publicar")
            publicando = False
            return
        
        # Publicación optimizada
        for i, grupo in enumerate(grupos):
            if not publicando:
                break
                
            nombre, enlace = grupo
            username = enlace.split('/')[-1]
            
            estado_actual = f"Publicando ({i+1}/{total_grupos}): {nombre[:20]}..."
            
            try:
                entity = await client.get_entity(username)
                
                # Verificar permisos
                if not await verificar_permisos(client, entity):
                    guardar_publicacion(grupo, "Sin permisos")
                    progreso_detalles.append(f"🚫 Sin permisos en: {nombre}")
                    continue
                
                # Enviar publicación
                if imagen_publicacion and os.path.exists(imagen_publicacion):
                    await client.send_file(entity, imagen_publicacion, caption=mensaje_publicacion)
                else:
                    await client.send_message(entity, mensaje_publicacion)
                
                guardar_publicacion(grupo, "Publicado")
                progreso_detalles.append(f"📢 Publicado en: {nombre}")
                total_publicados += 1
                
                # Espera entre publicaciones
                if i < len(grupos) - 1 and publicando:
                    espera = 10
                    await asyncio.sleep(espera)
                    
            except Exception as e:
                guardar_publicacion(grupo, f"Error: {type(e).__name__}")
                progreso_detalles.append(f"❌ Error en {nombre}: {str(e)}")
        
        await client.disconnect()
        estado_actual = f"Publicación completada: {total_publicados}/{total_grupos} grupos"
        progreso_detalles.append("✅ Publicación completada correctamente")
    except Exception as e:
        estado_actual = f"Error en publicación: {str(e)}"
        progreso_detalles.append(f"❌❌ ERROR EN PUBLICACIÓN: {str(e)}")
    finally:
        publicando = False

# Rutas Flask
@app.route('/', methods=['GET', 'POST'])
def index():
    # Si ya tiene sesión configurada, ir al panel
    if os.path.exists(app.config['SESSION_FILE']) and os.path.exists(app.config['REFERRAL_FILE']):
        return redirect(url_for('panel'))
    
    # Mostrar formulario inicial
    if request.method == 'POST':
        telefono = request.form.get('telefono')
        api_id = request.form.get('api_id')
        api_hash = request.form.get('api_hash')
        referral = request.form.get('referral')
        
        # Validar campos
        if not all([telefono, api_id, api_hash, referral]):
            return render_template('fameviz_index.html', error="Todos los campos son obligatorios")
        
        if 'fameviz' not in referral.lower():
            return render_template('fameviz_index.html', error="Enlace de referido no válido")
        
        # Guardar datos de sesión temporalmente
        session['telefono'] = telefono
        session['api_id'] = api_id
        session['api_hash'] = api_hash
        session['referral'] = referral
        
        # Guardar referral
        with open(app.config['REFERRAL_FILE'], 'w') as f:
            f.write(referral)
        
        # Intentar crear sesión
        return redirect(url_for('crear_sesion'))
    
    return render_template('fameviz_index.html', error=None)

@app.route('/crear_sesion', methods=['GET', 'POST'])
def crear_sesion():
    if 'telefono' not in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        codigo = request.form.get('codigo')
        
        try:
            client = TelegramClient(
                StringSession(),
                int(session['api_id']),
                session['api_hash']
            )
            
            client.connect()
            
            if not client.is_user_authorized():
                client.sign_in(session['telefono'], codigo)
            
            # Guardar sesión
            session_str = client.session.save()
            with open(app.config['SESSION_FILE'], 'w') as f:
                f.write(session_str)
            
            client.disconnect()
            return redirect(url_for('panel'))
            
        except Exception as e:
            return render_template('fameviz_verificacion.html', error=str(e))
    
    return render_template('fameviz_verificacion.html', error=None)

@app.route('/panel', methods=['GET', 'POST'])
def panel():
    global mensaje_publicacion, imagen_publicacion, publicando, estado_actual, progreso_detalles
    
    # Verificar sesión
    if not (os.path.exists(app.config['SESSION_FILE']) and os.path.exists(app.config['REFERRAL_FILE'])):
        return redirect(url_for('index'))
    
    referral = cargar_referral()
    imagenes = obtener_imagenes_disponibles()
    grupos = cargar_grupos_publicables()
    
    if request.method == 'POST':
        # Configurar publicación
        if 'configurar_publicacion' in request.form:
            try:
                texto_idx = int(request.form.get("texto_pred"))
                imagen_nombre = request.form.get("imagen_pred")
                
                # Obtener texto y reemplazar {{codigo}}
                texto = TEXTOS_PREDEFINIDOS[texto_idx]
                mensaje_publicacion = texto.replace('{{codigo}}', referral)
                
                # Validar texto
                if not validar_texto(mensaje_publicacion):
                    progreso_detalles.append("❌ ERROR: El texto contiene palabras prohibidas")
                    return render_template(
                        'fameviz_panel.html',
                        estado=estado_actual,
                        detalles=progreso_detalles,
                        mensaje_pub=mensaje_publicacion,
                        imagen_pub=imagen_publicacion,
                        publicando=publicando,
                        textos=TEXTOS_PREDEFINIDOS,
                        imagenes=imagenes,
                        total_grupos=len(grupos),
                        referral=referral,
                        error="El texto contiene palabras prohibidas"
                    )
                
                # Configurar imagen
                if imagen_nombre:
                    imagen_publicacion = os.path.join(app.config['FAMEVIZ_IMAGES'], imagen_nombre)
                else:
                    imagen_publicacion = ""
                
                progreso_detalles.append("✅ Configuración de publicación guardada")
                
            except Exception as e:
                progreso_detalles.append(f"❌ Error configurando publicación: {str(e)}")
        
        # Iniciar publicación
        elif 'iniciar_publicacion' in request.form:
            if mensaje_publicacion:
                import threading
                threading.Thread(target=lambda: asyncio.run(publicar_en_grupos_internal())).start()
            else:
                progreso_detalles.append("❌ Error: Mensaje de publicación vacío")
        
        # Detener publicación
        elif 'detener_publicacion' in request.form:
            publicando = False
            estado_actual = "Publicación detenida"
            progreso_detalles.append("⏹️ Publicación detenida por el usuario")
        
        return redirect(url_for('panel'))
    
    return render_template(
        'fameviz_panel.html',
        estado=estado_actual,
        detalles=progreso_detalles,
        mensaje_pub=mensaje_publicacion,
        imagen_pub=imagen_publicacion,
        publicando=publicando,
        textos=TEXTOS_PREDEFINIDOS,
        imagenes=imagenes,
        total_grupos=len(grupos),
        referral=referral,
        error=None
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
