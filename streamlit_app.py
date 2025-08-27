import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Autenticación con Google Sheets
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive",
]
creds = ServiceAccountCredentials.from_json_keyfile_name("creds/creds.json", scope)
client = gspread.authorize(creds)

# Abrir hoja de mesas
spreadsheet = client.open_by_key("1kN5ZFVRgJIBpIaXgRWIJrO2DGmjIh-w-L2P0f_Qfxx0")
mesas_sheet = spreadsheet.worksheet("mesas")
datos = mesas_sheet.get_all_records()

# Procesar mesas
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
        "mensajes": []  # Puedes poblar esto si tienes una hoja de mensajes
    }
    mesas.append(mesa)


st.set_page_config(page_title="Panel Admin", layout="wide")
st.title("🎮 Panel de Control del Administrador")
st.subheader("Mesas Activas")

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
    """, unsafe_allow_html=True)

    st.markdown(f"👤 <b>Creador:</b> @{mesa['jugadores'][0]}", unsafe_allow_html=True)

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
