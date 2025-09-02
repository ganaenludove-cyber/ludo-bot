import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import firebase_admin
from firebase_admin import credentials, db
from datetime import datetime

# ⚙️ Configuración visual del panel
st.set_page_config(page_title="Panel Admin", layout="wide")
st.title("🎮 Panel de Control del Administrador")
st.subheader("Mesas Activas")
st.subheader("📢 Sala de espera")

# 🔍 Verificar que las claves estén disponibles
st.write("🔍 google es tipo:", type(st.secrets["google"]))
st.write("🔑 google keys:", getattr(st.secrets["google"], "keys", lambda: "❌ No es dict")())
st.write("🔍 Secciones disponibles en secrets:", list(st.secrets.keys()))
if "firebase" not in st.secrets or "google" not in st.secrets:
    st.error("❌ Faltan claves en la configuración de Streamlit. Verifica que [firebase] y [google] estén definidos en Secrets.")
    st.stop()

# ✅ Mostrar tipo de st.secrets["google"] para diagnóstico
st.write("✅ Tipo de google:", type(st.secrets["google"]))

# 🔐 Autenticación con Google Sheets
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive",
]
creds_dict = st.secrets["google"].to_dict()
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)


# 🧪 Validación rápida: leer celda A1
try:
    test_sheet = client.open_by_key("1kN5ZFVRgJIBpIaXgRWIJrO2DGmjIh-w-L2P0f_Qfxx0").worksheet("mesas")
    valor = test_sheet.acell("A1").value
    st.success(f"✅ Conexión con Google Sheets exitosa. Valor en A1: {valor}")
except Exception as e:
    st.error(f"❌ Error al acceder a la hoja: {e}")
    st.stop()

# 📄 Abrir hojas
spreadsheet = client.open_by_key("1kN5ZFVRgJIBpIaXgRWIJrO2DGmjIh-w-L2P0f_Qfxx0")
mesas_sheet = spreadsheet.worksheet("mesas")
saldos_sheet = spreadsheet.worksheet("saldos")
usuarios = saldos_sheet.get_all_records()
usuarios = [
    {k.lower().replace(" ", "_"): v for k, v in fila.items()}
    for fila in usuarios
]
sin_mesa = [u for u in usuarios if not u.get("mesa_id") or u["mesa_id"] == "pendiente"]
datos = mesas_sheet.get_all_records()

# 🔌 Inicializar Firebase
if not firebase_admin._apps:
    cred_dict = dict(st.secrets["firebase"])
    if "\\n" in cred_dict["private_key"]:
        cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred, {
        'databaseURL': cred_dict["databaseURL"]
    })

# 🧩 Procesar mesas
mesas = []
for fila in datos:
    jugadores = [fila.get(f"Jugador {i}") for i in range(1, 5) if fila.get(f"Jugador {i}")]
    tipo = "1v1" if len(jugadores) == 2 else "2v2" if len(jugadores) == 4 else "4_jugadores"
    mesa = {
        "id": fila["ID"],
        "estado": fila.get("Estado", "pendiente"),
        "tipo": tipo,
        "creador": jugadores[0] if jugadores else "Desconocido",
        "jugadores": jugadores,
        "mensajes": []
    }

    # 🔄 Cargar mensajes desde Firebase
    try:
        ref = db.reference(f"mensajes/{mesa['id']}")
        mensajes = ref.get()
        mesa["mensajes"] = list(mensajes.values()) if mensajes else []
    except Exception:
        mesa["mensajes"] = []

    mesas.append(mesa)

# 🖥️ Mostrar mesas activas
for mesa in mesas:
    with st.expander(f"🧩 Mesa {mesa['id']} - {mesa['tipo']} - {mesa['estado']}"):
        st.write("👥 Jugadores:", ", ".join(mesa["jugadores"]))
        if mesa["mensajes"]:
            st.write("💬 Mensajes:")
            for msg in mesa["mensajes"]:
                st.markdown(f"- {msg}")
        else:
            st.info("Sin mensajes registrados.")

# 📥 Preguntas pendientes simuladas
preguntas_pendientes = st.session_state.get("preguntas_pendientes", [])
st.session_state["preguntas_pendientes"] = [
    {"usuario": "jugador1", "id": "123456", "texto": "¿Cuándo empieza la partida?"},
    {"usuario": "jugador2", "id": "789012", "texto": "No me asignaron mesa"}
]

# 🧪 Probar conexión con log de inicio
try:
    test_ref = db.reference("test_bot")
    test_ref.set({
        "mensaje": "Bot conectado correctamente",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "origen": "streamlit_app.py",
        "admin_id": st.session_state.get("admin_id", "desconocido")
    })
    st.success("✅ Conexión a Firebase exitosa")
except Exception as e:
    st.error(f"❌ Error conectando a Firebase: {e}")

# 💾 Función para guardar mensajes en Firebase
def guardar_mensaje_en_firebase(mesa_id, mensaje):
    try:
        ref = db.reference(f"mensajes/{mesa_id}")
        ref.push(mensaje)
    except Exception as e:
        st.error(f"❌ Error al guardar mensaje en Firebase: {e}")

# 🧾 Vista previa de clave (opcional para depurar)
st.text_area("🔐 Clave Google (preview)", creds_dict["private_key"], height=200)

def responder_pregunta_por_id(id_pregunta, respuesta):
    try:
        ref = db.reference("preguntas")
        todas = ref.get()
        for clave, pregunta in todas.items():
            if pregunta["id"] == id_pregunta:
                ref.child(clave).update({
                    "respuesta": respuesta,
                    "estado": "respondida",
                    "respondido_por": st.session_state.get("admin_id", "desconocido"),
                    "timestamp_respuesta": datetime.datetime.now().isoformat()
                })
                break
    except Exception as e:
        st.error(f"❌ Error al guardar respuesta: {e}")

if preguntas_pendientes:
    for i, p in enumerate(preguntas_pendientes):
        st.markdown(f"""
        <div style='background-color:#222;padding:12px;border-radius:10px;margin-bottom:10px;'>
            <b>👤 @{p['usuario']}</b><br>
            🆔 {p['id']}<br>
            💬 {p['texto']}
        </div>
        """, unsafe_allow_html=True)

        respuesta = st.text_input(f"✏️ Responder a @{p['usuario']}", key=f"respuesta_{i}")
        if st.button(f"📤 Enviar respuesta", key=f"btn_respuesta_{i}"):
            if respuesta.strip():
                responder_pregunta_por_id(p["id"], respuesta)
                st.success(f"📨 Respuesta enviada a @{p['usuario']}")
            else:
                st.warning("⚠️ La respuesta no puede estar vacía.")
else:
    st.info("✅ No hay preguntas pendientes.")



mensaje_global = st.text_input("✏️ Mensaje para jugadores sin mesa")
if st.button("📤 Enviar mensaje global"):
    st.success("Mensaje enviado a todos los jugadores sin mesa")
    # Aquí podrías guardar el mensaje en una hoja 'mensajes_globales' si lo deseas

# Filtro por estado
estado_seleccionado = st.selectbox("Filtrar por estado", ["Todos", "en_juego", "pendiente"])
mesas_filtradas = [m for m in mesas if estado_seleccionado == "Todos" or m["estado"] == estado_seleccionado]

# Búsqueda por jugador
busqueda = st.text_input("🔍 Buscar jugador")
if busqueda:
    mesas_filtradas = [m for m in mesas_filtradas if busqueda in m["jugadores"]]
    st.info(f"{busqueda} está en las mesas: {[m['id'] for m in mesas_filtradas]}")

# Estilos visuales
st.markdown("""
<style>
.card {border-radius: 10px; padding: 10px; margin-bottom: 10px;}
.en_juego {background-color: #d1f7c4;}
.pendiente {background-color: #fef3c7;}
.cerrada {background-color: #f3f4f6;}
.admin-msg {background-color: #e0e7ff; padding: 5px; border-radius: 5px; margin-bottom: 4px;}
.player-msg {background-color: #f9fafb; padding: 5px; border-radius: 5px; margin-bottom: 4px;}
</style>
""", unsafe_allow_html=True)
def responder_pregunta(id_pregunta, respuesta):
    try:
        ref = db.reference(f"preguntas/{id_pregunta}")
        ref.update({
            "respuesta": respuesta,
            "estado": "respondida",
            "respondido_por": st.session_state.get("admin_id", "desconocido"),
            "timestamp_respuesta": datetime.datetime.now().isoformat()
        })
    except Exception as e:
        st.error(f"❌ Error al responder pregunta: {e}")

def registrar_reembolso_en_firebase(mesa_id, jugadores):
    try:
        ref = db.reference("reembolsos")
        ref.push({
            "mesa_id": mesa_id,
            "jugadores": jugadores,
            "admin": st.session_state.get("admin_id", "desconocido"),
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        st.warning(f"⚠️ No se pudo registrar reembolso en Firebase: {e}")


# Funciones modulares
def render_mesa(mesa):
    tipo_label = {
        "1v1": "⚔️ 1 vs 1",
        "2v2": "👥 2 vs 2",
        "4_jugadores": "🎲 4 jugadores libres"
    }.get(mesa["tipo"], "🎲 Mesa libre")

    estado_color = {
        "en_juego": "#28a745",
        "pendiente": "#ffc107",
        "cerrada": "#6c757d"
    }.get(mesa["estado"], "#444")

    st.markdown(f"""
        <div style='
            background-color:#1c1c1c;
            padding:20px;
            border-radius:16px;
            margin-bottom:30px;
            box-shadow:0 0 10px rgba(0,0,0,0.3);
        '>
            <div style='
                background-color:{estado_color};
                color:white;
                padding:14px;
                border-radius:12px;
                font-size:24px;
                font-weight:bold;
                text-align:center;
                margin-bottom:20px;
                box-shadow:0 0 6px rgba(0,0,0,0.2);
            '>
                🧩 Mesa #{mesa['id']} — {tipo_label} &nbsp;&nbsp;|&nbsp;&nbsp; Estado: {mesa["estado"].upper()}
            </div>
        </div>
    """, unsafe_allow_html=True)

    # 👤 Mostrar creador de la mesa
    if mesa.get("jugadores") and len(mesa["jugadores"]) > 0:
        st.markdown(f"👤 <b>Creador:</b> @{mesa['jugadores'][0]}", unsafe_allow_html=True)
    else:
        st.markdown("👤 <b>Creador:</b> (sin asignar)", unsafe_allow_html=True)

    col1, col2 = st.columns([1, 2])

    with col1:
        st.markdown("👥 <b>Jugadores:</b>", unsafe_allow_html=True)

        if mesa["tipo"] == "2v2" and len(mesa["jugadores"]) == 4:
            equipo_a = mesa["jugadores"][:2]
            equipo_b = mesa["jugadores"][2:]

            st.markdown("🟦 <b>Equipo A</b>", unsafe_allow_html=True)
            for jugador in equipo_a:
                st.markdown(f"<div style='background-color:#444;color:white;padding:6px 10px;border-radius:6px;font-size:13px;margin-bottom:4px;'>@{jugador}</div>", unsafe_allow_html=True)

            st.markdown("🟥 <b>Equipo B</b>", unsafe_allow_html=True)
            for jugador in equipo_b:
                st.markdown(f"<div style='background-color:#444;color:white;padding:6px 10px;border-radius:6px;font-size:13px;margin-bottom:4px;'>@{jugador}</div>", unsafe_allow_html=True)
        else:
            for jugador in mesa["jugadores"]:
                st.markdown(f"@{jugador}")

        st.markdown("---")
        st.markdown("👤 <b>Nuevo creador</b>", unsafe_allow_html=True)
        nuevo_creador = st.selectbox("Selecciona jugador", mesa["jugadores"], key=f"nuevo_creador_{mesa['id']}")
        if st.button("🔄 Cambiar creador", key=f"btn_cambiar_creador_{mesa['id']}"):
            mesa["jugadores"].remove(nuevo_creador)
            mesa["jugadores"].insert(0, nuevo_creador)
            st.success(f"✅ @{nuevo_creador} ahora es el creador de la mesa #{mesa['id']}")

        st.markdown("---")
        st.markdown("🚫 <b>Descalificar jugador</b>", unsafe_allow_html=True)
        jugador_descalificar = st.selectbox("Selecciona jugador", mesa["jugadores"][1:], key=f"descalificar_{mesa['id']}")
        if st.button("❌ Descalificar", key=f"btn_descalificar_{mesa['id']}"):
            mesa["jugadores"].remove(jugador_descalificar)
            eliminar_jugador_en_sheets(mesa["id"], jugador_descalificar)
            st.warning(f"⚠️ @{jugador_descalificar} ha sido descalificado de la mesa #{mesa['id']}")

    with col2:
        render_chat(mesa)

    st.markdown("</div>", unsafe_allow_html=True)


def render_jugadores(mesa):
    st.write("👥 Jugadores:")
    for j, jugador in enumerate(mesa["jugadores"]):
        icono_equipo = ""
        if mesa["tipo"] == "2v2":
            icono_equipo = "🟦A" if j < 2 else "🟥B"
        st.markdown(f"<div style='background-color:#444; color:white; padding:6px 10px; border-radius:6px; font-size:13px; display:inline-block; margin-bottom:4px;'>{icono_equipo} {jugador}</div>", unsafe_allow_html=True)

def render_chat(mesa):
    # 🔄 Sincronizar mensajes desde Firebase
    try:
        ref = db.reference(f"mensajes/{mesa['id']}")
        mensajes = ref.get()
        mesa["mensajes"] = list(mensajes.values()) if mensajes else []
    except Exception as e:
        mesa["mensajes"] = []

    st.markdown("💬 <b>Chat de la mesa:</b>", unsafe_allow_html=True)

    chat_html = "<div style='background-color:#111;padding:16px;border-radius:12px;height:300px;overflow-y:auto;font-size:12px;margin-bottom:12px;display:flex;flex-direction:column;'>"

    for mensaje in mesa["mensajes"]:
        remitente = mensaje["de"]
        avatar_url = mesa.get("avatars", {}).get(remitente, "https://via.placeholder.com/32")
        es_admin = remitente == "Admin"
        color = "#0f62fe" if es_admin and mensaje["para"] == "Todos" else "#ff6f00" if es_admin else "#333"
        direccion = "row-reverse" if es_admin else "row"
        borde = "border-radius:12px 12px 0px 12px;" if es_admin else "border-radius:12px 12px 12px 0px;"
        destinatario = f"(TODOS)" if mensaje["para"] == "Todos" else f"({mensaje['para']})"

        chat_html += (
            f"<div style='display:flex;flex-direction:{direccion};align-items:flex-start;margin:6px 0;'>"
            f"<img src='{avatar_url}' style='width:28px;height:28px;border-radius:50%;margin:4px;' />"
            f"<div style='background-color:{color};color:white;padding:6px 10px;max-width:80%;{borde}'>"
            f"<b>{remitente}</b> {destinatario}<br>{mensaje['texto']}</div></div>"
        )

    chat_html += "</div>"
    st.markdown(chat_html, unsafe_allow_html=True)

    # 📤 Envío de nuevo mensaje
    opciones_destino = ["Todos"]

    if mesa["tipo"] == "2v2" and len(mesa["jugadores"]) == 4:
        equipo_a = mesa["jugadores"][:2]
        equipo_b = mesa["jugadores"][2:]
        opciones_destino += [f"Equipo A ({', '.join(equipo_a)})", f"Equipo B ({', '.join(equipo_b)})"]

    opciones_destino += mesa["jugadores"]

    destinatario = st.selectbox("📍 Destinatario", opciones_destino, key=f"dest_{mesa['id']}")
    mensaje_respuesta = st.text_input("✏️ Escribe tu mensaje", key=f"respuesta_unica_{mesa['id']}")
    if st.button("📤 Enviar", key=f"btn_respuesta_unica_{mesa['id']}"):
        if mensaje_respuesta:
            nuevo_mensaje = {
                "de": "Admin",
                "para": destinatario,
                "texto": mensaje_respuesta
            }
            mesa["mensajes"].append(nuevo_mensaje)
            guardar_mensaje_en_firebase(mesa["id"], nuevo_mensaje)
            st.success(f"📨 Mensaje enviado a {destinatario} en mesa #{mesa['id']}")
        else:
            st.warning("⚠️ Escribe un mensaje antes de enviar")
def render_botones(mesa):
    col1, col2 = st.columns(2)
    with col1:
        nuevo_creador = st.selectbox("👤 Nuevo creador", mesa["jugadores"], key=f"nuevo_creador_{mesa['id']}")
        if st.button("✅ Cambiar creador", key=f"btn_cambiar_creador_{mesa['id']}"):
            mesa["creador"] = nuevo_creador
            st.success(f"Mesa #{mesa['id']}: creador cambiado a {nuevo_creador}")
    with col2:
        jugador_descalificar = st.selectbox("🚫 Descalificar jugador", mesa["jugadores"], key=f"descalificar_{mesa['id']}")
        if st.button("❌ Descalificar", key=f"btn_descalificar_{mesa['id']}"):
            if jugador_descalificar in mesa["jugadores"]:
                mesa["jugadores"].remove(jugador_descalificar)
                mesa["estado"] = "pendiente"
                mesa["mensajes"].append({
                    "de": "Admin",
                    "para": jugador_descalificar,
                    "texto": f"Has sido descalificado de la mesa #{mesa['id']}."
                })
                mesa["mensajes"].append({
                    "de": "Admin",
                    "para": "Todos",
                    "texto": f"{jugador_descalificar} fue descalificado. La partida debe repetirse."
                })
                st.warning(f"Mesa #{mesa['id']}: {jugador_descalificar} descalificado.")
            else:
                st.error("Ese jugador ya no está en la mesa.")

# Renderizado en rejilla
for i in range(0, len(mesas_filtradas), 3):
    fila = mesas_filtradas[i:i+3]
    columnas = st.columns(len(fila))
    for idx, mesa in enumerate(fila):
        with columnas[idx]:
            render_mesa(mesa)
# 🧠 Función para actualizar creador en Google Sheets
def actualizar_creador_en_sheets(mesa_id, nuevo_creador):
    try:
        fila = next(i+2 for i, m in enumerate(datos) if m["ID"] == mesa_id)
        col = mesas_sheet.find("Jugador 1").col
        mesas_sheet.update_cell(fila, col, nuevo_creador)
        st.success(f"✅ Creador actualizado en Sheets para mesa #{mesa_id}")
    except Exception as e:
        st.error(f"❌ Error al actualizar creador en Sheets: {e}")

# 🧠 Función para actualizar estado en Sheets
def actualizar_estado_en_sheets(mesa_id, nuevo_estado):
    try:
        fila = next(i+2 for i, m in enumerate(datos) if m["ID"] == mesa_id)
        col = mesas_sheet.find("Estado").col
        mesas_sheet.update_cell(fila, col, nuevo_estado)
        st.success(f"✅ Estado actualizado en Sheets para mesa #{mesa_id}")
    except Exception as e:
        st.error(f"❌ Error al actualizar estado en Sheets: {e}")

# 🧠 Función para registrar acción en log_admin
def registrar_log_accion(mesa_id, accion, usuario_afectado=""):
    try:
        log_sheet = spreadsheet.worksheet("log_admin")
        log_sheet.append_row([mesa_id, accion, usuario_afectado, st.session_state.get("admin_id", "desconocido")])
    except Exception as e:
        st.warning(f"⚠️ No se pudo registrar en log_admin: {e}")

# 💸 Función para reembolsar jugadores si mesa está incompleta
def reembolsar_mesa(mesa):
    registrar_reembolso_en_firebase(mesa["id"], jugadores)
    jugadores = mesa["jugadores"]
    if len(jugadores) < 2:
        st.warning("⚠️ No se puede reembolsar: mesa vacía")
        return
    try:
        saldos = saldos_sheet.get_all_records()
        for jugador in jugadores:
            fila = next((i+2 for i, u in enumerate(saldos) if u.get("usuario telegram") == jugador), None)
            if fila:
                col_saldo = saldos_sheet.find("saldo").col
                saldo_actual = float(saldos_sheet.cell(fila, col_saldo).value)
                nuevo_saldo = saldo_actual + 1.0  # ejemplo: reembolso de 1 unidad
                saldos_sheet.update_cell(fila, col_saldo, nuevo_saldo)
        mesa["estado"] = "cerrada"
        actualizar_estado_en_sheets(mesa["id"], "cerrada")
        registrar_log_accion(mesa["id"], "Reembolso automático", ",".join(jugadores))
        st.success(f"💸 Reembolso aplicado a jugadores de mesa #{mesa['id']}")
    except Exception as e:
        st.error(f"❌ Error al aplicar reembolso: {e}")
def eliminar_jugador_en_sheets(mesa_id, jugador):
    try:
        fila = next(i+2 for i, m in enumerate(datos) if m["ID"] == mesa_id)
        for i in range(1, 5):
            col = mesas_sheet.find(f"Jugador {i}").col
            if mesas_sheet.cell(fila, col).value == jugador:
                mesas_sheet.update_cell(fila, col, "")
                break
    except Exception as e:
        st.error(f"❌ Error al eliminar jugador en Sheets: {e}")

# 🔧 Añadir controles extra en render_botones
def render_botones(mesa):
    col1, col2 = st.columns(2)
    with col1:
        nuevo_creador = st.selectbox("👤 Nuevo creador", mesa["jugadores"], key=f"nuevo_creador_{mesa['id']}")
        if st.button("✅ Cambiar creador", key=f"btn_cambiar_creador_{mesa['id']}"):
            mesa["creador"] = nuevo_creador
            actualizar_creador_en_sheets(mesa["id"], nuevo_creador)
            registrar_log_accion(mesa["id"], "Cambio de creador", nuevo_creador)

        nuevo_estado = st.selectbox("📌 Cambiar estado", ["pendiente", "en_juego", "cerrada"], key=f"estado_{mesa['id']}")
        if st.button("🔄 Actualizar estado", key=f"btn_estado_{mesa['id']}"):
            mesa["estado"] = nuevo_estado
            actualizar_estado_en_sheets(mesa["id"], nuevo_estado)
            registrar_log_accion(mesa["id"], "Cambio de estado", nuevo_estado)

    with col2:
        jugador_descalificar = st.selectbox("🚫 Descalificar jugador", mesa["jugadores"], key=f"descalificar_{mesa['id']}")
        if st.button("❌ Descalificar", key=f"btn_descalificar_{mesa['id']}"):
            if jugador_descalificar in mesa["jugadores"]:
                mesa["jugadores"].remove(jugador_descalificar)
                mesa["estado"] = "pendiente"
                mesa["mensajes"].append({
                    "de": "Admin",
                    "para": jugador_descalificar,
                    "texto": f"Has sido descalificado de la mesa #{mesa['id']}."
                })
                mesa["mensajes"].append({
                    "de": "Admin",
                    "para": "Todos",
                    "texto": f"{jugador_descalificar} fue descalificado. La partida debe repetirse."
                })
                actualizar_estado_en_sheets(mesa["id"], "pendiente")
                registrar_log_accion(mesa["id"], "Descalificación", jugador_descalificar)
                st.warning(f"Mesa #{mesa['id']}: {jugador_descalificar} descalificado.")
            else:
                st.error("Ese jugador ya no está en la mesa.")

        if st.button("💸 Reembolsar jugadores", key=f"btn_reembolso_{mesa['id']}"):
            reembolsar_mesa(mesa)









