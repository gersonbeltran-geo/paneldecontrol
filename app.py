import streamlit as st
import pandas as pd
import plotly.express as px
import io
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

st.set_page_config(page_title="Panel Comercial", layout="wide", page_icon="📊")
def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets["app_password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("Contraseña", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Contraseña", type="password", on_change=password_entered, key="password")
        st.error("Contraseña incorrecta")
        return False
    else:
        return True

if not check_password():
    st.stop()

FILE_ID = "1Ha2pXVlHrtBFCkiTgwdWhTjKnw6SEfY3fGckqIffhLc"
CREDS_PATH = "credenciales.json"
SKIP_ROWS = 15  # fila 16 = cabecera real

# --- Estilo ---
st.markdown("""
<style>
.stApp { background-color: #0e1117; }
[data-testid="stMetric"] {
    background: #1b1f2a; border-radius: 12px; padding: 16px;
    border: 1px solid #2a2f3a;
}
h1 { font-weight: 800; }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def get_drive_service():
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build("drive", "v3", credentials=creds)

@st.cache_data(ttl=30)
def load_data(_service, file_id):
    meta = _service.files().get(fileId=file_id, fields="mimeType").execute()
    mime = meta["mimeType"]
    if mime == "application/vnd.google-apps.spreadsheet":
        request = _service.files().export_media(
            fileId=file_id,
            mimeType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        request = _service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    buffer.seek(0)
    df = pd.read_excel(buffer, skiprows=SKIP_ROWS)
    df.columns = [str(c).strip() for c in df.columns]
    return df

service = get_drive_service()
df = load_data(service, FILE_ID)

# --- Cabecera ---
col_a, col_b = st.columns([5, 1])
with col_a:
    st.title("📊 Panel de Seguimiento Comercial")
with col_b:
    if st.button("🔄 Refrescar"):
        st.cache_data.clear()
        st.rerun()

# --- Filtros ---
with st.expander("🔍 Filtros", expanded=False):
    c1, c2, c3 = st.columns(3)
    estado_f = c1.multiselect("Estado", sorted(df["ESTADO"].dropna().unique()))
    linea_f = c2.multiselect("Línea de negocio", sorted(df["LÍNEA DE NEGOCIO"].dropna().unique()))
    resp_f = c3.multiselect("Responsable", sorted(df["RESPONSABLE"].dropna().unique()))

    c4, c5, c6 = st.columns(3)
    tipologia_f = c4.multiselect("Tipología de clientes", sorted(df["TIPOLOGÍA DE CLIENTES"].dropna().unique()))
    captacion_f = c5.multiselect("Captación", sorted(df["CAPTACIÓN"].dropna().unique()))
    herramientas_f = c6.multiselect("Herramientas", sorted(df["HERRAMIENTAS"].dropna().unique()))

    c7, _, _ = st.columns(3)
    subestado_f = c7.multiselect("Subestado", sorted(df["SUBESTADO"].dropna().unique()))

f = df.copy()
if estado_f:
    f = f[f["ESTADO"].isin(estado_f)]
if linea_f:
    f = f[f["LÍNEA DE NEGOCIO"].isin(linea_f)]
if resp_f:
    f = f[f["RESPONSABLE"].isin(resp_f)]
if tipologia_f:
    f = f[f["TIPOLOGÍA DE CLIENTES"].isin(tipologia_f)]
if captacion_f:
    f = f[f["CAPTACIÓN"].isin(captacion_f)]
if herramientas_f:
    f = f[f["HERRAMIENTAS"].isin(herramientas_f)]
if subestado_f:
    f = f[f["SUBESTADO"].isin(subestado_f)]

# --- KPIs ---
k1, k2, k3, k4 = st.columns(4)
k1.metric("Oportunidades", len(f))
k2.metric("Importe estimado", f'{f["IMPORTE ESTIMADO (SIN IVA)"].sum():,.0f} €')
k3.metric("Importe ponderado", f'{f["IMPORTE PONDERADO (SIN IVA)"].sum():,.0f} €')
k4.metric("Prob. media", f'{f["PROBABILIDAD CONVERSIÓN"].mean():.0%}' if len(f) else "-")

st.divider()

# --- Preguntas de negocio ---
st.subheader("💡 Preguntas de negocio")

PREGUNTAS = {
    "¿Qué línea de negocio genera más importe?":
        lambda d: px.bar(d.groupby("LÍNEA DE NEGOCIO")["IMPORTE ESTIMADO (SIN IVA)"].sum().reset_index(),
                          x="LÍNEA DE NEGOCIO", y="IMPORTE ESTIMADO (SIN IVA)", color="LÍNEA DE NEGOCIO"),
    "¿Cuáles son los clientes con mayor importe ponderado?":
        lambda d: px.bar(d.groupby("CLIENTE")["IMPORTE PONDERADO (SIN IVA)"].sum().nlargest(10).reset_index(),
                          x="CLIENTE", y="IMPORTE PONDERADO (SIN IVA)"),
    "¿En qué estado está el pipeline?":
        lambda d: px.pie(d, names="ESTADO", title="Distribución por estado"),
    "¿Qué responsable lleva más importe?":
        lambda d: px.bar(d.groupby("RESPONSABLE")["IMPORTE ESTIMADO (SIN IVA)"].sum().reset_index(),
                          x="RESPONSABLE", y="IMPORTE ESTIMADO (SIN IVA)", color="RESPONSABLE"),
    "¿Qué tipología de cliente predomina?":
        lambda d: px.pie(d.dropna(subset=["TIPOLOGÍA DE CLIENTES"]), names="TIPOLOGÍA DE CLIENTES"),
    "¿Cómo se distribuye la probabilidad de conversión?":
        lambda d: px.histogram(d, x="PROBABILIDAD CONVERSIÓN", nbins=10),
    "¿Qué canal de captación funciona mejor (importe)?":
        lambda d: px.bar(d.groupby("CAPTACIÓN")["IMPORTE ESTIMADO (SIN IVA)"].sum().reset_index(),
                          x="CAPTACIÓN", y="IMPORTE ESTIMADO (SIN IVA)", color="CAPTACIÓN"),
}

pregunta = st.selectbox("Elige una pregunta:", list(PREGUNTAS.keys()))
try:
    fig = PREGUNTAS[pregunta](f)
    fig.update_layout(template="plotly_dark", height=450)
    st.plotly_chart(fig, use_container_width=True)
except Exception as e:
    st.warning(f"No se pudo generar esta vista con los filtros actuales: {e}")

st.divider()

# --- Tabla detalle ---
with st.expander("📋 Ver tabla completa"):
    st.dataframe(f, use_container_width=True)
