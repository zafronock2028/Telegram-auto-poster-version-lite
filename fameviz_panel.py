import os
import re
import time
import asyncio
import logging
import sys
import types

# Parche para imghdr en Python 3.13+
if sys.version_info >= (3, 13):
    try:
        from PIL import Image
        
        class ImghdrModule(types.ModuleType):
            def what(self, filepath):
                try:
                    with Image.open(filepath) as img:
                        return img.format.lower()
                except Exception:
                    # Implementación de respaldo
                    if filepath.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                        return filepath.split('.')[-1]
                    return None
        
        sys.modules['imghdr'] = ImghdrModule('imghdr')
        print("✅ Parche para imghdr aplicado")
    except ImportError:
        print("⚠️ Pillow no está instalado. Usando implementación mínima")
        class ImghdrModule(types.ModuleType):
            def what(self, filepath):
                if filepath.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                    return filepath.split('.')[-1]
                return None
        sys.modules['imghdr'] = ImghdrModule('imghdr')
else:
    import imghdr

# Ahora importamos telethon
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.types import ChatBannedRights
from flask import Flask, render_template, request, redirect, url_for, session

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

# Palabras prohibidas
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

# Textos predefinidos
TEXTOS_PREDEFINIDOS = [
    "🚀 ¿Cansado de ver videos sin ganar nada?\n💸 Hoy puedes convertir tu tiempo en dinero REAL.\n🔥 Con FAMEVIZ:\n✅ Te pagan por ver videos 📲\n✅ Ganas por invitar personas\n✅ Sistema automático 24/7\n📈 Mientras más vistas, más ganas.\n🌐 Regístrate: {{codigo}}\n📩 Ayuda: @ganaconluis",
    "🔥 Gana desde casa con videos\n💰 FameViz paga todos los días\n✅ No necesitas vender\n✅ No necesitas seguidores\n📲 Solo ver y compartir\n🌐 Únete ahora: {{codigo}}",
    "🤖 El algoritmo ya no manda...\n📢 Tú decides cuánto ganar\n💸 FameViz convierte tus vistas en dinero\n💥 Comienza hoy con tu código: {{codigo}}",
    "🎯 ¿Quieres ganar $200, $500 o más por semana?\n✅ FameViz es el sistema\n💼 Ve videos\n📣 Invita con tu link\n💵 Cobra diario\nEntra ahora 👉 {{codigo}}",
    "💸 Te pagan por ver videos\n📲 Te pagan por invitar\n✅ Sistema automático\n🔐 No necesitas saber de tecnología\n👉 Regístrate aquí: {{codigo}}",
    "🔥 Lo que haces gratis ahora…\n¡Te puede pagar!\n✅ Miras videos\n✅ Ganas dinero\n🌟 FameViz es el futuro\nRegístrate ahora 👉 {{codigo}}",
    "💥 Si ves esto, es tu señal.\nGana con FameViz hoy mismo\n📲 Te pagan por usar redes\n📈 ¡No esperes más!\n👉 Empieza ya: {{codigo}}",
    "🚨 Alerta de ingreso extra:\nFameViz paga por vistas\n💸 Tú miras, tú cobras\n✅ Sin jefes\n✅ Sin horarios\n🌐 Aquí el link: {{codigo}}",
    "📱 Gana comisiones viendo videos\n✅ Reales, fáciles y automáticas\n🔥 FameViz lo hace posible\nRegístrate con tu código aquí: {{codigo}}",
    "😎 Sin experiencia, sin complicaciones\nSolo necesitas conexión y ganas\n💰 FameViz te paga por ver videos\nÚnete ahora 👉 {{codigo}}"
]

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
        logger.error(f"Error cargando grupos: {e}")
        return []

def guardar_publicacion(grupo, estado):
    with open(app.config['HISTORIAL_PUBLICACIONES'], 'a', encoding='utf-8') as f:
        f.write(f"{grupo[0]} | {grupo[1]} | {estado} | {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

async def verificar_permisos_internal(client, grupo):
    try:
        full = await client(GetFullChannelRequest(grupo))
        rights = full.full_chat.default_banned_rights
        return not rights.send_messages and not rights.send_media
    except Exception as e:
        logger.error(f"Error verificando permisos: {e}")
        return False

def validar_texto(texto):
    texto = texto.lower()
    return not any(palabra in texto for palabra in PALABRAS_PROHIBIDAS)

def obtener_imagenes_disponibles():
    return [f for f in os.listdir(app.config['FAMEVIZ_IMAGES']) 
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))]

# Funciones principales
async def publicar_en_grupos_internal():
    global estado_actual, progreso_detalles, publicando
    
    try:
        if not panel_activo or not mensaje_publicacion:
            return
        
        publicando = True
        progreso_detalles = ["Iniciando proceso de publicación..."]
        estado_actual = "Preparando publicación..."
        
        # Validar texto
        if not validar_texto(mensaje_publicacion):
            progreso_detalles.append("❌ ERROR: Texto contiene palabras prohibidas")
            estado_actual = "Publicación bloqueada"
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
        total_grupos = len(grupos)
        
        if total_grupos == 0:
            estado_actual = "No hay grupos disponibles"
            progreso_detalles.append("⚠️ No se encontraron grupos válidos")
            publicando = False
            return
        
        total_publicados = 0
        for i, grupo in enumerate(grupos):
            if not publicando:
                break
                
            nombre, enlace = grupo
            username = enlace.split('/')[-1]
            estado_actual = f"Publicando ({i+1}/{total_grupos}): {nombre[:20]}..."
            
            try:
                entity = await client.get_entity(username)
                
                # Verificar permisos usando la función interna asíncrona
                if not await verificar_permisos_internal(client, entity):
                    guardar_publicacion(grupo, "Sin permisos")
                    progreso_detalles.append(f"🚫 Sin permisos en: {nombre}")
                    continue
                
                if imagen_publicacion and os.path.exists(imagen_publicacion):
                    await client.send_file(entity, imagen_publicacion, caption=mensaje_publicacion)
                else:
                    await client.send_message(entity, mensaje_publicacion)
                
                guardar_publicacion(grupo, "Publicado")
                progreso_detalles.append(f"📢 Publicado en: {nombre}")
                total_publicados += 1
                
                # Espera entre publicaciones
                if i < len(grupos) - 1 and publicando:
                    await asyncio.sleep(10)
                    
            except Exception as e:
                guardar_publicacion(grupo, f"Error: {type(e).__name__}")
                progreso_detalles.append(f"❌ Error en {nombre}: {str(e)}")
        
        estado_actual = f"Publicación completada: {total_publicados}/{total_grupos} grupos"
        progreso_detalles.append("✅ Publicación completada")
    except Exception as e:
        estado_actual = f"Error en publicación: {str(e)}"
        progreso_detalles.append(f"❌❌ ERROR: {str(e)}")
    finally:
        publicando = False
        if 'client' in locals():
            await client.disconnect()

# Funciones asíncronas envueltas para ejecución síncrona
def crear_sesion_wrapper():
    return asyncio.run(crear_sesion_async())

def reenviar_codigo_wrapper():
    return asyncio.run(reenviar_codigo_async())

# Rutas Flask
@app.route('/', methods=['GET', 'POST'])
def index():
    if os.path.exists(app.config['SESSION_FILE']) and os.path.exists(app.config['REFERRAL_FILE']):
        return redirect(url_for('panel'))
    
    if request.method == 'POST':
        telefono = request.form.get('telefono')
        api_id = request.form.get('api_id')
        api_hash = request.form.get('api_hash')
        referral = request.form.get('referral')
        
        if not all([telefono, api_id, api_hash, referral]):
            return render_template('fameviz_index.html', error="Todos los campos son obligatorios")
        
        if 'fameviz' not in referral.lower():
            return render_template('fameviz_index.html', error="Enlace de referido no válido")
        
        session['telefono'] = telefono
       
