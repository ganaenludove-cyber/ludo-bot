import logging
import re
import random
import json
import os
RUTA_MESAS = os.path.join("creeds", "mesas.json")
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
import gspread
from oauth2client.service_account import ServiceAccountCredentials
# CONFIGURACIÓN
TOKEN = "7922777635:AAEAb8NmzBzxmOFdxu9tDrLsRF3XPGtXGJA"
SPREADSHEET_ID = "1kN5ZFVRgJIBpIaXgRWIJrO2DGmjIh-w-L2P0f_Qfxx0"
ADMIN_USERNAME = "@ludoclubve_admin"
ADMIN_ID = 998267451
BOT_USERNAME = "@Ludoclubve_bot"
GRUPO_ID = -1002624779868  # ID de tu grupo de Telegram

# LOGGING
logging.basicConfig(level=logging.INFO)

# GOOGLE SHEETS
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive",
]
creds = ServiceAccountCredentials.from_json_keyfile_name("creds/creds.json", scope)
client = gspread.authorize(creds)
spreadsheet = client.open_by_key(SPREADSHEET_ID)
saldos_sheet = spreadsheet.worksheet("saldos")
historial_sheet = spreadsheet.worksheet("historial_recargas")
historial_partidas_sheet = spreadsheet.worksheet("historial_partidas")


# FAQ y palabras clave para respuestas automáticas
faq_respuestas = {
    "cómo retiro mi premio": {
        "claves": ["transfieran", "quiero sacar la plata", "como retiro", "como cobro", "como saco", "como me pagan", "retiro", "cobro", "sacar plata"],
        "respuesta": (
            "🏆 ¿Cómo retirar tu premio?\n\n"
            "1. Toma captura de tu victoria y compártela en el grupo.\n"
            "2. Envía tu Pago Móvil por privado para reclamar tu premio.\n"
            "3. Puedes seguir jugando y acumular tus ganancias."
        )
    },
    "pago movil": {
        "claves": ["pm", "numero de cuenta", "donde transfiero", "pagomovil", "pago movil", "cuenta", "donde pago", "numero pm", "pagomov"],
        "respuesta": (
            "💳 ENVÍA TU RECARGA A:\n"
            "28094277\n04126721219\n0134 Banesco\n\n"
            "Y envía el comprobante aquí por privado."
        )
    },
    "ausente": {
        "claves": ["no me deja entrar", "ausente", "me fui", "no entre a la partida", "no pude entrar", "no logre entrar"],
        "respuesta": f"Si no puedes entrar a la partida, debes avisar a {ADMIN_USERNAME} antes de 5 minutos desde que se envió el link."
    },
    "como jugar": {
        "claves": ["como juego", "quiero jugar", "empezar", "crear sala", "crear partida"],
        "respuesta": (
            "📽 Aprende cómo jugar y crear partidas:\n\n"
            "👥 ¿Cómo unirte a una partida?\n👉 https://t.me/+-rrwc63ny0tlY2E5\n"
            "🏠 ¿Cómo crear una sala?\n👉 https://t.me/+-rrwc63ny0tlY2E5"
        )
    },
    "uso de bot": {
        "claves": ["usa bot", "bot jugando"],
        "respuesta": "🤖 El uso de bots no representa ventaja real. No es ilegal ni descalificable, pero puede ser molesto."
    },
    "trampa": {
        "claves": ["compro dados", "hizo trampa", "reportar"],
        "respuesta": f"📩 Si crees que alguien hizo trampa, manda evidencia al grupo o a {ADMIN_USERNAME}."
    },
    "cuanto tarda": {
        "claves": ["cuanto tardan", "cuanto tiempo", "cuando me pagan", "tarda"],
        "respuesta": "⏱ El pago tarda aproximadamente 15 minutos luego de confirmado."
    },
}
keywords_saldo = ["saldo", "cuanto tengo", "cuanto me queda", "cuanta plata tengo"]

# Variables globales para manejo de mesas y estado
activo_mesero = False
numero_mesa_actual = 1
ultimo_dia_publicacion = None

mesas_1vs1 = []
mesas_4 = []
mesas_2vs2 = []

usuarios_en_mesa = {}  # user_id => (tipo_mesa, id_mesa)
mensaje_mesas_publicadas = {}  # (tipo_mesa, id_mesa) => mensaje_id
mensajes_enviados = []
comprobantes = {}

capturas_enviadas = {}  # { (user_id, tipo_mesa, id_mesa): datetime }

scheduler = AsyncIOScheduler()

# FUNCIONES AUXILIARES
def enviar_mensajes(application):
    mesas = cargar_mesas()
    for mesa in mesas:
        for mensaje in mesa.get("mensajes", []):
            if mensaje not in mensajes_enviados:
                destino = mensaje["para"]
                texto = mensaje["texto"]

                if destino == "Todos":
                    for jugador in mesa.get("jugadores", []):
                        chat = chat_id(jugador)
                        if chat:
                            application.bot.send_message(chat_id=chat, text=texto)
                elif destino.startswith("Equipo A"):
                    for jugador in mesa.get("jugadores", [])[:2]:
                        chat = chat_id(jugador)
                        if chat:
                            application.bot.send_message(chat_id=chat, text=texto)
                elif destino.startswith("Equipo B"):
                    for jugador in mesa.get("jugadores", [])[2:]:
                        chat = chat_id(jugador)
                        if chat:
                            application.bot.send_message(chat_id=chat, text=texto)
                else:
                    chat = chat_id(destino)
                    if chat:
                        application.bot.send_message(chat_id=chat, text=texto)

                mensajes_enviados.append(mensaje)

def cargar_mesas():
    if not os.path.exists(RUTA_MESAS):
        return []
    with open(RUTA_MESAS, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar_mesas(mesas):
    with open(RUTA_MESAS, "w", encoding="utf-8") as f:
        json.dump(mesas, f, indent=2, ensure_ascii=False)


async def iniciar_scheduler():
    scheduler.add_job(reset_historial_semanal, 'cron', day_of_week='mon', hour=0, minute=0)
    scheduler.start()

def reset_historial_semanal():
    try:
        historial_partidas_sheet.clear()
        historial_partidas_sheet.append_row([
            "Fecha", "Hora", "Tipo de mesa", "#Mesa", "Jugadores",
            "Saldo antes", "Apuesta", "Premio", "Estado"
        ])
        print("✅ Historial semanal reiniciado")
    except Exception as e:
        print("❌ Error al reiniciar historial:", e)

def registrar_historial(mesa, estado=None):
    from datetime import datetime

    fecha_hora = datetime.now()
    fecha = fecha_hora.strftime("%d/%m/%Y")
    hora = fecha_hora.strftime("%H:%M")

    tipo_mesa = mesa.get("tipo", "N/A")
    numero_mesa = mesa.get("numero", mesa.get("id", "N/A"))
    jugadores_lista = mesa.get("jugadores", [])
    jugadores = ", ".join(jugadores_lista)

    # Obtener saldos antes del juego
    saldos_antes = []
    for jugador in jugadores_lista:
        saldo = obtener_saldo_usuario(jugador)
        saldos_antes.append(str(saldo))
    saldos_antes_str = ", ".join(saldos_antes)

    apuesta = mesa.get("apuesta", 0)
    premio = mesa.get("premio", 0)

    # 🧠 Formatear estado si no fue pasado manualmente
    if estado is None:
        if tipo_mesa == "1vs1":
            ganador = mesa.get("ganador", "N/A")
            perdedor = [j for j in jugadores_lista if j != ganador]
            estado = f"Ganador: {ganador} | Perdedor: {', '.join(perdedor)}"

        elif tipo_mesa == "2vs2":
            ganadores = mesa.get("equipo_ganador", [])
            perdedores = [j for j in jugadores_lista if j not in ganadores]
            estado = f"Ganadores: {', '.join(ganadores)} | Perdedores: {', '.join(perdedores)}"

        elif tipo_mesa == "4":
            ganador_1 = mesa.get("ganador_1", "N/A")
            ganador_2 = mesa.get("ganador_2", "N/A")
            perdedores = [j for j in jugadores_lista if j not in [ganador_1, ganador_2]]
            estado = f"1er: {ganador_1} | 2do: {ganador_2} | Perdieron: {', '.join(perdedores)}"

        else:
            estado = "Resultado no especificado"

    # Registrar en Google Sheets
    try:
        historial_partidas_sheet.append_row([
            fecha, hora, tipo_mesa, numero_mesa, jugadores,
            saldos_antes_str, apuesta, premio, estado
        ])
        print(f"✅ Registro exitoso en historial_partidas para mesa #{numero_mesa}")
    except Exception as e:
        print(f"❌ Error al registrar en historial_partidas: {e}")


# Obtener la fila de un usuario en la hoja 'saldos'
def obtener_mesa_usuario(username):
    # Obtener user_id desde la hoja 'saldos'
    usuarios = saldos_sheet.col_values(1)
    ids = saldos_sheet.col_values(2)
    if username not in usuarios:
        return None
    index = usuarios.index(username)
    user_id = int(ids[index])
    
    # Buscar en la memoria si el usuario tiene mesa
    if user_id in usuarios_en_mesa:
        return usuarios_en_mesa[user_id]  # devuelve (tipo, id_mesa)
    return None

def obtener_fila_usuario(username):
    usuarios = saldos_sheet.col_values(1)
    if username in usuarios:
        return usuarios.index(username) + 1
    return None

# Actualizar la mesa actual de un usuario
def actualizar_mesa_usuario(username, mesa_id):
    fila = obtener_fila_usuario(username)
    if fila:
        saldos_sheet.update_cell(fila, 4, mesa_id)

def registrar_usuario_si_no_existe(username: str, user_id: int):
    usuarios = saldos_sheet.col_values(1)
    if username not in usuarios:
        saldos_sheet.append_row([username, str(user_id), "0"])

def obtener_saldo_usuario(username: str):
    usuarios = saldos_sheet.col_values(1)
    if username in usuarios:
        fila = usuarios.index(username) + 1
        saldo = saldos_sheet.cell(fila, 3).value
        return float(saldo)
    return 0.0

def actualizar_saldo_usuario(username: str, monto: float):
    usuarios = saldos_sheet.col_values(1)
    if username in usuarios:
        fila = usuarios.index(username) + 1
        saldo_actual = float(saldos_sheet.cell(fila, 3).value)
        nuevo_saldo = saldo_actual + monto
        saldos_sheet.update_cell(fila, 3, str(nuevo_saldo))
        historial_sheet.append_row([username, str(monto)])
        return nuevo_saldo
    return None

def detectar_pregunta(texto: str):
    texto = texto.lower()
    for data in faq_respuestas.values():
        for clave in data["claves"]:
            if clave in texto:
                return data["respuesta"]
    return None

# FUNCIONES PARA MESAS
def construir_mesa_texto(mesa):
    tipo = mesa["tipo"]
    id_mesa = mesa["id"]
    jugadores = mesa["jugadores"]
    texto = ""
    if tipo == "1vs1":
        texto = (
            f"🎲 <b>1vs1 - Mesa #{id_mesa}</b>\n\n"
            "💰 Apuesta: 160Bs\n"
            "🏆 Premio: 270Bs\n\n"
            "👥 Jugadores:\n"
        )
        for i in range(2):
            texto += f"  {i+1}. {jugadores[i] if i < len(jugadores) else '---'}\n"
    elif tipo == "4":
        texto = (
            f"🎲 <b>Clasica 4J - Mesa #{id_mesa}</b>\n\n"
            "💰 Apuesta: 100Bs\n"
            "🥇 1er lugar: 250Bs\n"
            "🥈 2do lugar: 100Bs\n\n"
            "👥 Jugadores:\n"
        )
        for i in range(4):
            texto += f"  {i+1}. {jugadores[i] if i < len(jugadores) else '---'}\n"
    elif tipo == "2vs2":
        texto = (
            f"🎲 <b>2vs2 Dupla - Mesa #{id_mesa}</b>\n\n"
            "💰 Apuesta: 200Bs\n"
            "🏆 Premio: 750Bs\n\n"
            "👥 Jugadores:\n"
            "👫 Pareja 1:\n"
        )
        for i in range(2):
            texto += f"  {i+1}. {jugadores[i] if i < len(jugadores) else '---'}\n"
        texto += "👫 Pareja 2:\n"
        for i in range(2,4):
            texto += f"  {i+1}. {jugadores[i] if i < len(jugadores) else '---'}\n"
    from random import choice

    if mesa["estado"] == "completa" and mesa["jugadores"]:
        creador = choice([j for j in mesa["jugadores"] if j != "---"])
        texto += f"\n🍀 ¡Suerte a todos!\n🎮 {creador} fue elegido para crear la sala."
    else:
        texto += "\n¿QUIÉN JUEGA?"

    return texto

def botones_mesa(mesa, bloquear=False):
    if bloquear:
        return None

    tipo = mesa["tipo"]

    if tipo == "2vs2":
        botones = [
            [
                InlineKeyboardButton("🔵 Pareja 1", callback_data=f"unirme_p1|{tipo}|{mesa['id']}"),
                InlineKeyboardButton("🔴 Pareja 2", callback_data=f"unirme_p2|{tipo}|{mesa['id']}")
            ],
            [InlineKeyboardButton("🚪 Salirme", callback_data=f"salirme|{tipo}|{mesa['id']}")],
            [
                InlineKeyboardButton(
                    "💳 Recargar saldo",
                    url=f"https://t.me/{BOT_USERNAME[1:]}?start=recargar"
                )
            ],
            [
                InlineKeyboardButton(
                    "📊 Ver Saldo",
                    callback_data=f"saldo|{tipo}|{mesa['id']}"
                )
            ]
        ]
    else:
        botones = [
            [
                InlineKeyboardButton("✅ Unirme", callback_data=f"unirme|{tipo}|{mesa['id']}"),
                InlineKeyboardButton("🚪 Salirme", callback_data=f"salirme|{tipo}|{mesa['id']}")
            ],
            [
                InlineKeyboardButton(
                    "💳 Recargar saldo",
                    url=f"https://t.me/{BOT_USERNAME[1:]}?start=recargar"
                )
            ],
            [
                InlineKeyboardButton(
                    "📊 Ver Saldo",
                    callback_data=f"saldo|{tipo}|{mesa['id']}"
                )
            ]
        ]

    return InlineKeyboardMarkup(botones)
async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📊 Ver mesas", callback_data="ver_mesas")],
        [InlineKeyboardButton("🧾 Historial", callback_data="ver_historial")],
        [InlineKeyboardButton("⚙️ Configuración", callback_data="config")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🎮 Panel de administración:", reply_markup=reply_markup)

async def publicar_mesas(context: ContextTypes.DEFAULT_TYPE):
    global numero_mesa_actual, ultimo_dia_publicacion, activo_mesero

    hoy = datetime.now().date()
    if ultimo_dia_publicacion != hoy:
        ultimo_dia_publicacion = hoy
        numero_mesa_actual = 1
        mesas_1vs1.clear()
        mesas_4.clear()
        mesas_2vs2.clear()
        usuarios_en_mesa.clear()

    # Borrar solo los mensajes de mesas pendientes
    for key, msg_id in mensaje_mesas_publicadas.items():
        tipo, id_mesa = key
        lista = mesas_1vs1 if tipo == "1vs1" else mesas_4 if tipo == "4" else mesas_2vs2
        m = next((x for x in lista if x["id"] == id_mesa), None)
        if m and m["estado"] == "pendiente":
            try:
                await context.bot.delete_message(chat_id=GRUPO_ID, message_id=msg_id)
            except:
                pass
    mensaje_mesas_publicadas.clear()


    if not activo_mesero:
        return

    # Chequear o crear mesas pendientes
    def buscar_o_crear(mesas, tipo, max_jugadores):
        # Buscar mesa pendiente (incompleta)
        for m in mesas:
            if m["estado"] == "pendiente" and len(m["jugadores"]) < max_jugadores:
                return m
        # Si no hay mesa pendiente, crear una nueva
        global numero_mesa_actual
        id_nueva = max([m["id"] for m in mesas], default=0) + 1
        m = {"id": id_nueva, "tipo": tipo, "jugadores": [], "estado": "pendiente"}
        mesas.append(m)
        return m


    m2 = buscar_o_crear(mesas_2vs2, "2vs2", 4)
    m1 = buscar_o_crear(mesas_1vs1, "1vs1", 2)
    m4 = buscar_o_crear(mesas_4, "4", 4)

    await publicar_o_actualizar(m2, context)
    await publicar_o_actualizar(m1, context)
    await publicar_o_actualizar(m4, context)



async def publicar_o_actualizar(mesa, context):
    key = (mesa["tipo"], mesa["id"])
    texto = construir_mesa_texto(mesa)
    bloquear = mesa["estado"] != "pendiente" or len(mesa["jugadores"]) == (2 if mesa["tipo"] == "1vs1" else 4)
    botones = botones_mesa(mesa, bloquear)

    # ✅ NOTIFICAR cuando se llena
    if mesa["estado"] == "completa" and "creador_notificado" not in mesa:
        from random import choice
        jugadores_validos = [j for j in mesa["jugadores"] if j != "---"]
        creador = choice(jugadores_validos)
        mesa["creador"] = creador

        usuarios = saldos_sheet.col_values(1)
        ids = saldos_sheet.col_values(2)

        for jugador in jugadores_validos:
            if jugador in usuarios:
                index = usuarios.index(jugador)
                jugador_id = int(ids[index])

                try:
                    if jugador == creador:
                        await context.bot.send_message(
                            chat_id=jugador_id,
                            text="🎮 Te tocó crear la sala. Cuando la tengas, envía el link aquí por aqui."
                        )
                    else:
                        await context.bot.send_message(
                            chat_id=jugador_id,
                            text="⏳ Mesa completa. Pronto recibirás el link de la sala. Mantente atento."
                        )
                except:
                    await context.bot.send_message(ADMIN_ID, f"⚠️ No se pudo escribir al jugador {jugador}")

        mesa["creador_notificado"] = True

    # ✅ SIEMPRE actualizar el mensaje en el grupo (no solo si está completa)
    from telegram.error import BadRequest

    if key in mensaje_mesas_publicadas:
        try:
            await context.bot.edit_message_text(
                chat_id=GRUPO_ID,
                message_id=mensaje_mesas_publicadas[key],
                text=texto,
                reply_markup=botones,
                parse_mode=ParseMode.HTML
            )
        except BadRequest as e:
            if "Message is not modified" in str(e):
                pass  # no hay cambio
            else:
                mensaje_mesas_publicadas.pop(key, None)
                msg = await context.bot.send_message(
                    chat_id=GRUPO_ID,
                    text=texto,
                    reply_markup=botones,
                    parse_mode=ParseMode.HTML
                )
                mensaje_mesas_publicadas[key] = msg.message_id
    else:
        msg = await context.bot.send_message(
            chat_id=GRUPO_ID,
            text=texto,
            reply_markup=botones,
            parse_mode=ParseMode.HTML
        )
        mensaje_mesas_publicadas[key] = msg.message_id

# Comprobar si un usuario está en alguna mesa
def usuario_en_mesa(user_id):
    return user_id in usuarios_en_mesa

# HANDLERS DE COMANDOS Y CALLBACKS
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = f"@{update.effective_user.username}"
    user_id = update.effective_user.id
    registrar_usuario_si_no_existe(username, user_id)

    # Detectar si /start viene con parámetro, como /start recargar
    args = context.args
    if args and args[0].lower() == "recargar":
        await update.message.reply_text(
            "💳 RECARGAR SALDO:\n\n"
            "Pago movil:\n\n"
            "28094277\n04126721219\n0134 Banesco\n\n"
            "📌 Luego, envía el comprobante aquí por privado para que sea verificado."
        )
        return

    texto = (
        "🎲 ¡Bienvenido a LudoClubVE! 🇻🇪\n\n"
        "Antes de comenzar a jugar debes ver estos dos videos:\n\n"
        "👥 ¿Cómo unirte a una partida?\n🎥 <a href='https://t.me/+-rrwc63ny0tlY2E5'>Click aquí</a>\n\n"
        "🏠 ¿Cómo crear una sala?\n🎥 <a href='https://t.me/+-rrwc63ny0tlY2E5'>Click aquí</a>\n\n"
        "🏆 ¿Cómo retirar tu premio?\n1. Captura tu victoria y compártela.\n2. Envía tu pago móvil por privado.\n\n"
        "📌 Reglas en el grupo. Lee antes de jugar.\n\n"
        "🚨 No bloquees este bot ni silencies el grupo.\n\n"
        "📊 Consulta tu saldo: /saldo"
    )
    await update.message.reply_text(texto, parse_mode=ParseMode.HTML)


async def saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = f"@{update.effective_user.username}"
    user_id = update.effective_user.id
    registrar_usuario_si_no_existe(username, user_id)
    saldo_actual = obtener_saldo_usuario(username)
    mensaje = (
        "🏦 SALDO DISPONIBLE 🏦\n\n"
        f"👤 {username}\n💰 Saldo: {saldo_actual:.2f} Bs\n\n"
        "📲 Pago móvil\n28094277\n04126721219\n0134 Banesco\n\n"
        "📌 Enviar comprobante de pago aquí para hacer una recarga."
    )
    await update.message.reply_text(mensaje)

async def mensaje_privado_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return

    texto = update.message.text
    if not texto:
        return

    user_id = update.effective_user.id
    username = f"@{update.effective_user.username}" if update.effective_user.username else str(user_id)
    registrar_usuario_si_no_existe(username, user_id)

    # ✅ Caso especial: si el ADMIN responde con "respuesta a ..."
    if user_id == ADMIN_ID and 'respuesta a "' in texto:
        try:
            import re
            match = re.search(r'respuesta a "(\d+)": (.+)', texto, re.DOTALL)
            if match:
                target_id = int(match.group(1))
                respuesta = match.group(2).strip()
                await context.bot.send_message(chat_id=target_id, text=respuesta)
                await update.message.reply_text("✅ Respuesta enviada al usuario.")
                return
        except Exception as e:
            await update.message.reply_text(f"❌ Error reenviando respuesta: {e}")
            return

    # 🌟 Revisar en qué mesa está el jugador
    mesa_actual_usuario = obtener_mesa_usuario(username)

    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    boton_responder = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            f"✍️ Responder a {username}",
            switch_inline_query_current_chat=f'{username} respuesta a "{user_id}": '
        )
    ]])

    if mesa_actual_usuario:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"🎲 Nuevo mensaje de {username}\n"
                f"🔸 Mesa: #{mesa_actual_usuario}\n\n"
                f"Contenido:\n{texto}"
            ),
            reply_markup=boton_responder
        )
    else:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📩 Pregunta de {username}:\n\n{texto}",
            reply_markup=boton_responder
        )

    # 🎮 Procesar link de Ludo Club y activar mesa
    if "ludoclub.com/invite.html" in texto and "Code:" in texto:
        try:
            import re
            match_link = re.search(r"(https://ludoclub\.com/invite\.html\?[^\s]+)", texto)
            match_codigo = re.search(r"Code:\s*([A-Z0-9]+)", texto)

            if match_link and match_codigo:
                link = match_link.group(1)
                codigo = match_codigo.group(1)

                mensaje_formateado = (
                    "🎮 ¡Nuevo código de sala recibido!\n\n"
                    "🔗 Entra al juego usando este link:\n"
                    f"👉 {link}\n\n"
                    "📌 Si no puedes entrar con el link, copia y pega este código:\n"
                    f"`{codigo}`\n\n"
                    "⬆️ Solo toca el código para copiarlo."
                )
                await update.message.reply_text(mensaje_formateado, parse_mode=ParseMode.MARKDOWN)

                usuarios = saldos_sheet.col_values(1)
                ids = saldos_sheet.col_values(2)

                mesa_encontrada = None
                jugadores = []
                for lista in [mesas_1vs1, mesas_4, mesas_2vs2]:
                    for m in lista:
                        if m.get("creador") == username and not m.get("link_enviado", False):
                            if m["estado"] in ["pendiente_link", "completa"]:
                                mesa_encontrada = m
                                jugadores = m["jugadores"]
                                break
                    if mesa_encontrada:
                        break

                if not mesa_encontrada:
                    await update.message.reply_text("⚠️ No se encontró una mesa lista para recibir el link. Verifica que esté completa y que no hayas enviado el link antes.")
                    await context.bot.send_message(ADMIN_ID, f"🔍 {username} envió link pero no se encontró mesa válida.")
                    return

                mesa_encontrada["estado"] = "activa"
                mesa_encontrada["link"] = link
                mesa_encontrada["link_enviado"] = True

                if not mesa_encontrada.get("saldo_descontado", False):
                    monto = mesa_encontrada.get("monto", 300)
                    for jugador in jugadores:
                        actualizar_saldo_usuario(jugador, -monto)
                    mesa_encontrada["saldo_descontado"] = True

                for jugador in jugadores:
                    if jugador in usuarios:
                        index = usuarios.index(jugador)
                        jugador_id = int(ids[index])
                        if jugador != username:
                            try:
                                await context.bot.send_message(
                                    chat_id=jugador_id,
                                    text=(
                                        "🎮 Ya puedes entrar a la sala:\n\n"
                                        f"👉 {link}\n\n"
                                        "📌 Código:\n"
                                        f"`{codigo}`\n\n"
                                        "⬆️ Toca el código para copiarlo. Si no puedes entrar con el link, usa el código manualmente."
                                    ),
                                    parse_mode=ParseMode.MARKDOWN
                                )
                            except Exception as e:
                                await context.bot.send_message(ADMIN_ID, f"⚠️ No se pudo enviar link a {jugador}: {e}")
                        else:
                            # Mensaje solo para el creador
                            await context.bot.send_message(
                                chat_id=jugador_id,
                                text=(
                                    "✅ Link enviado a todos los jugadores, espera que ingresen.\n\n"
                                    f"🔠 Código: `{codigo}`\n\n"
                                    "⏳ Al cumplirse los 5min te avisaré para que inicies."
                                ),
                                parse_mode=ParseMode.MARKDOWN
                            )

                await update.message.reply_text("✅ Link enviado a los demás jugadores y saldo descontado. ¡Buena suerte!")
                return
        except Exception as e:
            await update.message.reply_text("⚠️ Hubo un error procesando el código de sala.")
            await context.bot.send_message(ADMIN_ID, f"❌ Error reenviando link: {e}")
            return

    # 💰 Confirmación de pagos por el admin
    if user_id == ADMIN_ID and texto.startswith("(confirmado:"):
        import re
        match = re.match(r"\(confirmado:(\d+)\s+(@\w+)\)", texto)
        if match:
            monto = int(match.group(1))
            usuario = match.group(2)
            if usuario in comprobantes:
                nuevo_saldo = actualizar_saldo_usuario(usuario, monto)
                if nuevo_saldo is not None:
                    await context.bot.send_message(ADMIN_ID, f"✅ Se sumaron {monto}Bs a {usuario}")
                    try:
                        await context.bot.send_message(comprobantes[usuario], f"✅ Se acreditaron {monto}Bs a tu cuenta.")
                    except:
                        await context.bot.send_message(ADMIN_ID, "⚠️ El usuario no inició chat con el bot.")
                else:
                    await context.bot.send_message(ADMIN_ID, f"❌ Usuario {usuario} no encontrado.")
            else:
                await context.bot.send_message(ADMIN_ID, "❌ No hay comprobante para ese usuario.")
        else:
            await context.bot.send_message(ADMIN_ID, "❌ Formato incorrecto. Usa (confirmado:100 @usuario)")
        return

    # 🤖 Respuestas automáticas (FAQ)
    respuesta_faq = detectar_pregunta(texto)
    if respuesta_faq:
        await update.message.reply_text(respuesta_faq)
        return

    # 💳 Consulta de saldo
    if any(k in texto.lower() for k in keywords_saldo):
        await saldo(update, context)
        return

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    username = f"@{update.effective_user.username}"
    user_id = update.effective_user.id
    registrar_usuario_si_no_existe(username, user_id)
    photo_file_id = update.message.photo[-1].file_id
    caption = f"📷 Comprobante de {username}"
    comprobantes[username] = user_id
    await context.bot.send_photo(ADMIN_ID, photo_file_id, caption=caption)
    await update.message.reply_text("✅ Comprobante recibido. Espera confirmación del admin.")

async def manejar_mesa_completa(m, tipo, monto_apuesta, context, mensaje_a_editar):
    # Normalizar jugadores con arroba
    m["jugadores"] = [j if j.startswith("@") else f"@{j}" for j in m["jugadores"]]

    # Asignar creador solo si no tiene
    if "creador" not in m or not m["creador"]:
        m["creador"] = random.choice(m["jugadores"])
        # Guardar en la lista original
        lista = mesas_1vs1 if tipo == "1vs1" else mesas_4 if tipo == "4" else mesas_2vs2
        for i in range(len(lista)):
            if lista[i]["id"] == m["id"]:
                lista[i]["creador"] = m["creador"]
                break

    # Actualizar mesa_actual de cada jugador en Google Sheets y memoria
    for jugador in m["jugadores"]:
        if jugador not in ["---", None]:
            actualizar_mesa_usuario(jugador, f"{tipo}|{m['id']}")  # actualizar en Sheets
            # Actualizar en memoria
            for uid, (t, mid) in usuarios_en_mesa.items():
                if t == tipo and mid == m["id"]:
                    usuarios_en_mesa[uid] = (tipo, m["id"])

    # Construir texto para el grupo
    texto = (
        f"🎲 {'Mesa 1vs1' if tipo=='1vs1' else 'Mesa de 4' if tipo=='4' else 'Mesa 2vs2'} - Mesa #{m['id']}\n\n"
        f"💰 Apuesta: {monto_apuesta}Bs\n"
        f"🏆 Premio: {'270Bs' if tipo=='1vs1' else '250Bs 1er lugar, 100Bs 2do lugar' if tipo=='4' else '750Bs'}\n\n"
        "👥 Jugadores:\n"
    )
    for i, jugador in enumerate(m["jugadores"], 1):
        texto += f"  {i}. {jugador}\n"
    texto += f"\n🍀 ¡Suerte a todos!\n"
    texto += f"🎮 {m['creador']} fue elegido para crear la sala."

    # Editar mensaje en grupo
    await mensaje_a_editar.edit_text(texto, reply_markup=botones_mesa(m, True), parse_mode=ParseMode.HTML)

    # Enviar mensajes privados
    usuarios_sheet = saldos_sheet.col_values(1)
    ids_sheet = saldos_sheet.col_values(2)

    for jugador in m["jugadores"]:
        if jugador in usuarios_sheet:
            index = usuarios_sheet.index(jugador)
            jugador_id = int(ids_sheet[index])
            try:
                if jugador == m["creador"]:
                    mensaje_privado = "🎮 Te tocó crear la sala. Cuando la tengas, envía el link por aquí."
                else:
                    mensaje_privado = (
                        f"🎮 ¡Tu mesa ya está completa!\n\n"
                        f"🏷️ Modalidad: {'1vs1' if tipo == '1vs1' else '2vs2' if tipo == '2vs2' else 'Todos contra todos'}\n"
                        f"💰 Se descontaron {monto_apuesta}Bs de tu saldo.\n"
                        f"⏳ Espera que el creador de la mesa comparta el link."
                    )
                await context.bot.send_message(chat_id=jugador_id, text=mensaje_privado)
            except Exception:
                await context.bot.send_message(ADMIN_ID, f"⚠️ No se pudo enviar mensaje a {jugador}")

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    username = f"@{query.from_user.username}" if query.from_user.username else query.from_user.first_name

    registrar_usuario_si_no_existe(username, user_id)

    data = query.data
    # ✅ Acciones del panel de administración
    if data == "ver_mesas":
        mesas = cargar_mesas()
        texto = "🎮 Mesas Activas:\n\n"
        for mesa in mesas:
            tipo = mesa.get("tipo", "N/A")
            estado = mesa.get("estado", "N/A").upper()
            jugadores = "\n".join([f"@{j}" for j in mesa.get("jugadores", [])])
            texto += f"🧩 Mesa #{mesa['id']} — {tipo} | Estado: {estado}\n👥 Jugadores:\n{jugadores}\n\n"
        await query.edit_message_text(text=texto)
        return

    elif data == "ver_historial":
        await query.edit_message_text("📜 Historial de partidas:\n\n(Próximamente disponible)")
        return

    elif data == "config":
        await query.edit_message_text("⚙️ Configuración del panel:\n\n(Próximamente disponible)")
        return


    # ✅ Acción de recarga
    if data == "recargar":
        await query.answer(
            f"Para recargar saldo envía tu comprobante por privado a {BOT_USERNAME}",
            show_alert=True
        )
        return
    # ✅ Acción de responder mensaje privado
    if data.startswith("responder|"):
        try:
            _, usuario, uid = data.split("|")
            await query.answer()  # cerrar loading
            # Enviar el "prefijo de respuesta" en el chat del admin
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"{usuario} respuesta a \"{uid}\": "
            )
        except Exception as e:
            await query.answer("⚠️ Error procesando respuesta.", show_alert=True)
            await context.bot.send_message(ADMIN_ID, f"❌ Error en responder: {e}")
        return

    # ⬇️ Todo lo tuyo de mesas sigue igual ⬇️
    try:
        partes = data.split("|")
        accion = partes[0]
        tipo = partes[1]
        id_mesa = int(partes[2])
    except:
        await query.answer("Acción no válida.", show_alert=True)
        return

    # Manejo del botón de saldo
    if accion == "saldo":
        saldo_actual = obtener_saldo_usuario(username)
        await query.answer(
            f"🏦 Saldo disponible: {saldo_actual:.2f}Bs",
            show_alert=True
        )
        return

    mesas = mesas_1vs1 if tipo == "1vs1" else mesas_4 if tipo == "4" else mesas_2vs2
    max_jugadores = 2 if tipo == "1vs1" else 4

    # Buscar la mesa válida
    mesa_encontrada = next((m for m in mesas if m["id"] == id_mesa and m["estado"] == "pendiente"), None)
    if not mesa_encontrada:
        await query.answer("⚠️ No se encontró esta mesa. Puede que ya esté llena o eliminada.", show_alert=True)
        return

    m = mesa_encontrada
    
    if accion in ["unirme", "unirme_p1", "unirme_p2"]:
        pareja = None

        if usuario_en_mesa(user_id):
            await query.answer("Solo puedes estar en una mesa a la vez. Sal de la actual para unirte a otra.", show_alert=True)
            return

        saldo_actual = obtener_saldo_usuario(username)
        monto_apuesta = 160 if tipo == "1vs1" else 100 if tipo == "4" else 200

        if saldo_actual < monto_apuesta:
            await query.answer(
                f"❌ Saldo insuficiente\n\n"
                f"💳 Apuesta: {monto_apuesta}Bs\n"
                f"💰Tu saldo: {saldo_actual:.2f}Bs\n\n"
                f"📌 Realiza el pago de tu apuesta y envía el capture al privado.",
                show_alert=True
            )
            return

        if accion == "unirme_p1":
            pareja = 1
        elif accion == "unirme_p2":
            pareja = 2

        # Unirse a la mesa según modalidad
        if pareja == 1:
            if len(m["jugadores"]) >= 2 and m["jugadores"][0] and m["jugadores"][1]:
                await query.answer("Pareja 1 ya está llena.", show_alert=True)
                return
            if len(m["jugadores"]) < 1:
                m["jugadores"].append(username)
            elif len(m["jugadores"]) == 1:
                m["jugadores"].insert(1, username)
        elif pareja == 2:
            if len(m["jugadores"]) >= 4 and m["jugadores"][2] and m["jugadores"][3]:
                await query.answer("Pareja 2 ya está llena.", show_alert=True)
                return
            while len(m["jugadores"]) < 2:
                m["jugadores"].append("---")
            if len(m["jugadores"]) == 2:
                m["jugadores"].append(username)
            elif len(m["jugadores"]) == 3:
                m["jugadores"].insert(3, username)
            elif len(m["jugadores"]) == 4:
                m["jugadores"][2] = username if m["jugadores"][2] == "---" else m["jugadores"][2]
                m["jugadores"][3] = username if m["jugadores"][3] == "---" else m["jugadores"][3]
        else:
            m["jugadores"].append(username)

        # Guardar en diccionario y Google Sheets
        usuarios_en_mesa[user_id] = (tipo, id_mesa)
        actualizar_mesa_usuario(username, f"{tipo}|{id_mesa}")

        # Si la mesa se llena, marcar completa y llamar a manejar_mesa_completa
        if len(m["jugadores"]) == max_jugadores:
            m["estado"] = "completa"
            m["completada_en"] = datetime.now()
            await manejar_mesa_completa(m, tipo, monto_apuesta, context, query.message)
            return

        # Actualizar mensaje de la mesa
        texto = construir_mesa_texto(m)
        botones = botones_mesa(m, False)
        await query.message.edit_text(texto, reply_markup=botones, parse_mode=ParseMode.HTML)
        return

    elif accion == "salirme":
        if user_id not in usuarios_en_mesa:
            await query.answer("No estás en ninguna mesa.", show_alert=True)
            return

        tipo_mesa, id_m = usuarios_en_mesa[user_id]
        if tipo_mesa != tipo or id_m != id_mesa:
            await query.answer("No estás en esta mesa.", show_alert=True)
            return

        for m in mesas:
            if m["id"] == id_mesa and m["estado"] == "pendiente":
                if username in m["jugadores"]:
                    m["jugadores"].remove(username)
                usuarios_en_mesa.pop(user_id)
                actualizar_mesa_usuario(username, "0")  # Resetear mesa
                await query.answer("🚪 Saliste de la mesa.", show_alert=True)
                texto = construir_mesa_texto(m)
                botones = botones_mesa(m, False)
                await query.message.edit_text(texto, reply_markup=botones, parse_mode=ParseMode.HTML)
                return

        await query.answer("No puedes salir si la partida ya comenzó.", show_alert=True)

    else:
        await query.answer("Acción no reconocida.", show_alert=True)

# --- RESPUESTAS DEL ADMIN ---
async def handle_admin_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Solo permitir que lo use el admin
    if update.effective_user.id != ADMIN_ID:
        return

    texto = update.message.text.strip()

    # Debe empezar con 'respuesta a "ID": '
    if texto.startswith('respuesta a "'):
        try:
            # Extraer ID y mensaje
            partes = texto.split('"')
            user_id = int(partes[1])  # lo que está entre comillas
            respuesta = texto.split('":', 1)[1].strip()  # después de los dos puntos

            # Mandar respuesta al usuario original
            await context.bot.send_message(chat_id=user_id, text=respuesta)

            # Confirmación al admin
            await update.message.reply_text("✅ Respuesta enviada al usuario.")
        except Exception as e:
            await update.message.reply_text(f"⚠️ Error al procesar la respuesta: {e}")
    else:
        # Si el admin escribe algo que no es respuesta
        await update.message.reply_text("Eres el admin 😉")

async def foto_grupo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global capturas_enviadas

    if not update.message or not update.message.photo:
        return

    user_id = update.message.from_user.id
    username = f"@{update.message.from_user.username}" if update.message.from_user.username else update.message.from_user.first_name
    chat_id = update.message.chat_id
    file_id = update.message.photo[-1].file_id
    ahora = datetime.now()

    key = f"{user_id}_{file_id}"
    if key in capturas_enviadas:
        ultima_vez = capturas_enviadas[key]
        if (ahora - ultima_vez).seconds < 300:
            return
    capturas_enviadas[key] = ahora

    if user_id not in usuarios_en_mesa:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📸 {username} envió un capture en el grupo pero no ha jugado recientemente."
        )
        return

    tipo_mesa, id_mesa = usuarios_en_mesa[user_id]
    lista_mesas = mesas_1vs1 if tipo_mesa == "1vs1" else mesas_4 if tipo_mesa == "4" else mesas_2vs2
    mesa = next((m for m in lista_mesas if m["id"] == id_mesa), None)

    if not mesa:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📸 {username} envió un capture pero su mesa ya fue cerrada o no existe."
        )
        return

    estado_valido = mesa.get("estado") in ["activa", "pendiente_pago", "completa"]
    if not estado_valido:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📸 {username} envió un capture pero su mesa ya fue procesada o está en estado: {mesa.get('estado')}."
        )
        return

    key_mesa = (user_id, tipo_mesa, id_mesa)
    if key_mesa in capturas_enviadas:
        minutos_pasados = int((ahora - capturas_enviadas[key_mesa]).total_seconds() / 60)
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"⚠️ {username} ya envió un capture para esta mesa hace {minutos_pasados} min. Ignorando duplicado."
        )
        return

    capturas_enviadas[key_mesa] = ahora

    jugadores_txt = "\n".join([f"• {j}" for j in mesa.get("jugadores", [])]) if mesa.get("jugadores") else "• (no registrados)"
    minutos_desde_completa = int((ahora - mesa.get("completada_en", ahora)).total_seconds() / 60)
    tiempo_txt = f"hace {minutos_desde_completa} min" if minutos_desde_completa > 0 else "hace poco"
    modalidad = "1vs1" if tipo_mesa == "1vs1" else "4 jugadores" if tipo_mesa == "4" else "2vs2"

    texto_admin = (
        f"🕵️ Verificación de victoria de {username}\n\n"
        f"🔸 Mesa: #{mesa['id']} ({modalidad})\n"
        f"⏱️ Completada {tiempo_txt}\n"
        f"👥 Jugadores:\n{jugadores_txt}\n\n"
        f"✍️ Usa:\n/ganador {username} 300"
    )

    boton_ganador = InlineKeyboardButton(
        text=f"💸 /ganador {username}",
        callback_data=f"comando_ganador:{username}"
    )
    teclado = InlineKeyboardMarkup([[boton_ganador]])

    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=file_id,
        caption=texto_admin,
        reply_markup=teclado
    )


async def activarmesas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global activo_mesero
    activo_mesero = True
    # Reiniciar estructuras internas
    mesas_1vs1.clear()
    mesas_4.clear()
    mesas_2vs2.clear()
    usuarios_en_mesa.clear()

    # Mostrar mensaje informativo mientras se actualizan las mesas
    mensaje_espera = await update.message.reply_text("🔄 Actualizando mesas... espera unos segundos.")

    # Cancelar cualquier publicación anterior para no duplicar
    for job in context.job_queue.get_jobs_by_name("publicar_mesas"):
        job.schedule_removal()

    # 🧹 Limpiar mesas viejas antes de publicar nuevas
    await limpiar_mensajes_viejos(context)

    # Publicar inmediatamente usando el contexto real
    from types import SimpleNamespace
    await publicar_mesas(SimpleNamespace(bot=context.bot, job_queue=context.job_queue))


    # Programar publicación automática cada 5 minutos
    context.job_queue.run_repeating(publicar_mesas, interval=300, first=300, name="publicar_mesas")

    # Editar el mensaje de espera para confirmar que ya están listas
    try:
        await mensaje_espera.edit_text("✅ Publicación de mesas activada. Ya puedes unirte.")
    except:
        pass  # Por si no se puede editar el mensaje



async def ganador(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("No tienes permiso para usar este comando.")
        return

    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Uso correcto: /ganador @usuario 300")
        return

    usuario = args[0]
    try:
        monto = float(args[1])
    except:
        await update.message.reply_text("El monto debe ser un número.")
        return

    usuarios = saldos_sheet.col_values(1)
    ids = saldos_sheet.col_values(2)

    if usuario not in usuarios:
        await update.message.reply_text("❌ Usuario no encontrado en la hoja de saldos.")
        return

    fila = usuarios.index(usuario) + 1
    saldo_actual = float(saldos_sheet.cell(fila, 3).value)
    nuevo_saldo = saldo_actual + monto
    saldos_sheet.update_cell(fila, 3, str(nuevo_saldo))
    historial_sheet.append_row([usuario, str(monto), "GANANCIA"])

    # Enviar mensaje al grupo
    mensaje = (
        "🏅 <b>¡PREMIO ENTREGADO!</b>\n\n"
        f"🎉 Felicitaciones: <b>{usuario}</b>\n"
        f"💰 Premio: <b>{monto:.2f} Bs</b>\n"
        "✅ ¡Sigue jugando y ganando!"
    )
    await context.bot.send_message(chat_id=GRUPO_ID, text=mensaje, parse_mode=ParseMode.HTML)

    # Confirmar al admin
    await update.message.reply_text(f"✅ {usuario} recibió {monto:.2f} Bs.")

    # Enviar mensaje privado al ganador
    try:
        index = usuarios.index(usuario)
        user_id = int(ids[index])
        mensaje_privado = (
            f"🏆 ¡Felicidades! Has ganado {monto:.2f} Bs 🎉\n"
            "💳 Ya fue acreditado a tu saldo.\n"
            "📲 Usa /saldo para ver tu balance."
        )
        await context.bot.send_message(chat_id=user_id, text=mensaje_privado)
    except Exception as e:
        await context.bot.send_message(ADMIN_ID, f"⚠️ No se pudo enviar mensaje privado a {usuario}: {e}")
        user_id = None

    # --- NUEVO: Resetear mesa_actual y registrar historial ---
    tipo_mesa = None
    id_mesa = None
    for uid, (t, m_id) in usuarios_en_mesa.items():
        if uid == user_id:
            tipo_mesa = t
            id_mesa = m_id
            break

    if tipo_mesa and id_mesa:
        lista_mesas = mesas_1vs1 if tipo_mesa == "1vs1" else mesas_4 if tipo_mesa == "4" else mesas_2vs2
        mesa = next((m for m in lista_mesas if m["id"] == id_mesa), None)

        if mesa:
            try:
                mesa["premio"] = monto
                if "apuesta" not in mesa:
                    mesa["apuesta"] = 0
                if "numero" not in mesa:
                    mesa["numero"] = mesa.get("id", "N/A")

                registrar_historial(mesa, "completada")
                print(f"✅ Historial registrado para mesa #{mesa['id']}")
            except Exception as e:
                print(f"❌ Error al registrar historial de mesa: {e}")

        jugadores_a_resetear = [uid for uid, (t, m_id) in usuarios_en_mesa.items() if t == tipo_mesa and m_id == id_mesa]
        for uid in jugadores_a_resetear:
            usuarios_en_mesa.pop(uid)
            index = ids.index(str(uid))
            saldos_sheet.update_cell(index + 1, 4, "0")  # columna 4 = mesa_actual


async def desactivar_mesas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global activo_mesero, mesas_1vs1, mesas_4, mesas_2vs2, usuarios_en_mesa, mensaje_mesas_publicadas

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("No tienes permiso para usar este comando.")
        return

    activo_mesero = False

    # Cancelar jobs de publicar mesas
    jobs = context.job_queue.get_jobs_by_name("publicar_mesas")
    for job in jobs:
        job.schedule_removal()

    # Borrar todos los mensajes de mesas en el grupo
    for key, msg_id in mensaje_mesas_publicadas.items():
        try:
            await context.bot.delete_message(chat_id=GRUPO_ID, message_id=msg_id)
        except Exception as e:
            print(f"❌ No se pudo borrar mensaje de mesa: {e}")

    mensaje_mesas_publicadas.clear()

    # Resetear todas las estructuras de mesas
    mesas_1vs1.clear()
    mesas_4.clear()
    mesas_2vs2.clear()
    usuarios_en_mesa.clear()

    await update.message.reply_text("🔴 Todas las mesas fueron eliminadas y el sistema fue reiniciado.")


async def mensaje_grupo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # NO hacer nada para mensajes en grupo para evitar reenviar
    pass

async def test_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    botones = InlineKeyboardMarkup([
        [InlineKeyboardButton("Probar alerta", callback_data="alerta_test")]
    ])
    await context.bot.send_message(chat_id=update.effective_chat.id, text="🔍 Pulsa el botón para probar:", reply_markup=botones)

async def test_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data == "alerta_test":
        await query.answer("✅ ¡Funciona la ventana emergente!", show_alert=True)
        
async def limpiar_mensajes_viejos(context):
    global mesas_1vs1, mesas_4, mesas_2vs2, usuarios_en_mesa, mensaje_mesas_publicadas

    mensajes_eliminados = 0
    for (tipo, id_mesa), msg_id in mensaje_mesas_publicadas.items():
        try:
            await context.bot.delete_message(chat_id=GRUPO_ID, message_id=msg_id)
            mensajes_eliminados += 1
        except:
            pass

    # 🧹 Limpiar estructuras internas
    mesas_1vs1.clear()
    mesas_4.clear()
    mesas_2vs2.clear()
    usuarios_en_mesa.clear()
    mensaje_mesas_publicadas.clear()

    print(f"🧹 Se eliminaron {mensajes_eliminados} mesas antiguas.")

if __name__ == "__main__":
    from types import SimpleNamespace

    app = ApplicationBuilder().token(TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("saldo", saldo))
    app.add_handler(CommandHandler("activarmesas", activarmesas))
    app.add_handler(CommandHandler("desactivarmesas", desactivar_mesas))
    app.add_handler(CommandHandler("testalerta", test_alert))
    app.add_handler(CommandHandler("ganador", ganador))
    app.add_handler(CommandHandler("panel", panel))


    app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, mensaje_privado_handler))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, mensaje_grupo_handler))
    app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.GROUPS, foto_grupo_handler))
    app.add_handler(MessageHandler(filters.TEXT & filters.User(user_id=ADMIN_ID), handle_admin_response))

    app.add_handler(CallbackQueryHandler(test_callback, pattern="^alerta_test$"))
    app.add_handler(CallbackQueryHandler(callback_query_handler))

    async def on_startup(app):
        context_fake = SimpleNamespace()
        context_fake.bot = app.bot
        context_fake.job_queue = app.job_queue

        await limpiar_mensajes_viejos(context_fake)
        await iniciar_scheduler()

    app.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)
