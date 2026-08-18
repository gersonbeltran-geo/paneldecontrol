import streamlit as st
import pandas as pd
import plotly.express as px
import io
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

st.set_page_config(page_title="Panel de Seguimiento Comercial", layout="wide", page_icon="📊")

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
    return True

if not check_password():
    st.stop()

FILE_ID = "1Ha2pXVlHrtBFCkiTgwdWhTjKnw6SEfY3fGckqIffhLc"
SKIP_ROWS = 15
OBJETIVO_2026 = 750000
EUR = st.column_config.NumberColumn(format="%.2f €")

st.markdown("""
<style>
.stApp { background-color: #0e1117; }
[data-testid="stMetric"] { background: #1b1f2a; border-radius: 12px; padding: 16px; border: 1px solid #2a2f3a; }
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

def year_columns(df):
    cols = {}
    for c in df.columns:
        try:
            y = int(float(str(c).replace(",", ".")))
            if 2020 <= y <= 2035:
                cols[y] = c
        except ValueError:
            continue
    return dict(sorted(cols.items()))

service = get_drive_service()
df = load_data(service, FILE_ID)

# 2019 está mensualizado en las columnas P a AA (posiciones 15 a 26): se suma para obtener el total del año
if len(df.columns) > 26:
    cols_2019 = df.columns[15:27]
    df["_2019_TOTAL"] = df[cols_2019].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)

YEAR_COLS = year_columns(df)
for y, col in YEAR_COLS.items():
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
if "_2019_TOTAL" in df.columns:
    YEAR_COLS = {2019: "_2019_TOTAL", **YEAR_COLS}

def importe_por_año(data, estados=None):
    d = data.copy()
    if estados:
        d = d[d["ESTADO"].isin(estados)]
    return {y: (d["IMPORTE ESTIMADO (SIN IVA)"] * d[col]).sum() for y, col in YEAR_COLS.items()}

col_a, col_b = st.columns([5, 1])
with col_a:
    st.title("📊 Panel de Seguimiento Comercial")
with col_b:
    if st.button("🔄 Refrescar"):
        st.cache_data.clear()
        st.rerun()

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
if estado_f: f = f[f["ESTADO"].isin(estado_f)]
if linea_f: f = f[f["LÍNEA DE NEGOCIO"].isin(linea_f)]
if resp_f: f = f[f["RESPONSABLE"].isin(resp_f)]
if tipologia_f: f = f[f["TIPOLOGÍA DE CLIENTES"].isin(tipologia_f)]
if captacion_f: f = f[f["CAPTACIÓN"].isin(captacion_f)]
if herramientas_f: f = f[f["HERRAMIENTAS"].isin(herramientas_f)]
if subestado_f: f = f[f["SUBESTADO"].isin(subestado_f)]

k1, k2 = st.columns(2)
k1.metric("Oportunidades", len(f))
k2.metric("Importe estimado", f'{f["IMPORTE ESTIMADO (SIN IVA)"].sum():,.2f} €')

st.divider()
st.subheader("📅 Importe de proyectos por año (2019-2026)")
importes_proyecto = importe_por_año(f, estados=["PROYECTO"])
df_años = pd.DataFrame({"Año": list(importes_proyecto.keys()), "Importe": list(importes_proyecto.values())})
fig_años = px.bar(df_años, x="Año", y="Importe", text_auto=",.2f")
fig_años.update_layout(template="plotly_dark", height=400)
st.plotly_chart(fig_años, use_container_width=True)
st.metric("Total acumulado del periodo", f'{df_años["Importe"].sum():,.2f} €')

st.divider()
st.subheader("🎯 Oportunidades 2026 (ponderado vs sin ponderar)")
oportunidades_2026 = f[f["ESTADO"] == "OPORTUNIDAD"]
col_2026 = YEAR_COLS.get(2026)
if col_2026 is not None:
    sin_pond = (oportunidades_2026["IMPORTE ESTIMADO (SIN IVA)"] * oportunidades_2026[col_2026]).sum()
    pond = (oportunidades_2026["IMPORTE PONDERADO (SIN IVA)"] * oportunidades_2026[col_2026]).sum()
else:
    sin_pond = oportunidades_2026["IMPORTE ESTIMADO (SIN IVA)"].sum()
    pond = oportunidades_2026["IMPORTE PONDERADO (SIN IVA)"].sum()
oc1, oc2 = st.columns(2)
oc1.metric("Sin ponderar 2026", f'{sin_pond:,.2f} €')
oc2.metric("Ponderado 2026", f'{pond:,.2f} €')

st.divider()
st.subheader("🎯 Desviación vs objetivo 2026")
real_2026 = importes_proyecto.get(2026, 0)
desviacion = real_2026 - OBJETIVO_2026
dc1, dc2, dc3 = st.columns(3)
dc1.metric("Objetivo 2026", f'{OBJETIVO_2026:,.2f} €')
dc2.metric("Real 2026", f'{real_2026:,.2f} €')
dc3.metric("Desviación", f'{desviacion:,.2f} €')

st.divider()
proyectos_abiertos = f[f["SUBESTADO"] == "ABIERTO"]
st.subheader(f"📋 Proyectos en estado abierto ({len(proyectos_abiertos)})")
st.dataframe(proyectos_abiertos, use_container_width=True, column_config={
    "IMPORTE ESTIMADO (SIN IVA)": EUR, "IMPORTE PONDERADO (SIN IVA)": EUR
})

st.divider()
st.subheader("📋 Oportunidades priorizadas por probabilidad de conversión")
oportunidades_tabla = f[f["ESTADO"] == "OPORTUNIDAD"].sort_values("PROBABILIDAD CONVERSIÓN", ascending=False)
st.dataframe(oportunidades_tabla, use_container_width=True, column_config={
    "IMPORTE ESTIMADO (SIN IVA)": EUR,
    "IMPORTE PONDERADO (SIN IVA)": EUR,
    "PROBABILIDAD CONVERSIÓN": st.column_config.NumberColumn(format="percent")
})

st.divider()
st.subheader("🥧 Distribución general")
g1, g2 = st.columns(2)
with g1:
    st.caption("Tipología de clientes")
    datos_tipologia = f.dropna(subset=["TIPOLOGÍA DE CLIENTES"])
    datos_tipologia = datos_tipologia[datos_tipologia["TIPOLOGÍA DE CLIENTES"].str.strip() != ""]
    fig1 = px.pie(datos_tipologia, names="TIPOLOGÍA DE CLIENTES")
    fig1.update_layout(template="plotly_dark", height=350)
    st.plotly_chart(fig1, use_container_width=True)
with g2:
    st.caption("Herramientas")
    fig2 = px.pie(f.dropna(subset=["HERRAMIENTAS"]), names="HERRAMIENTAS")
    fig2.update_layout(template="plotly_dark", height=350)
    st.plotly_chart(fig2, use_container_width=True)
g3, g4 = st.columns(2)
with g3:
    st.caption("Línea de negocio")
    datos_linea = f.dropna(subset=["LÍNEA DE NEGOCIO"])
    conteo_linea = datos_linea["LÍNEA DE NEGOCIO"].value_counts().reset_index()
    conteo_linea.columns = ["LÍNEA DE NEGOCIO", "Nº oportunidades"]
    fig3 = px.bar(conteo_linea.sort_values("Nº oportunidades"), x="Nº oportunidades", y="LÍNEA DE NEGOCIO", orientation="h")
    fig3.update_layout(template="plotly_dark", height=500)
    st.plotly_chart(fig3, use_container_width=True)
with g4:
    st.caption("Canal de captación")
    fig4 = px.pie(f.dropna(subset=["CAPTACIÓN"]), names="CAPTACIÓN")
    fig4.update_layout(template="plotly_dark", height=350)
    st.plotly_chart(fig4, use_container_width=True)

st.divider()
st.subheader("💰 ¿Qué canal de captación funciona mejor (por importe)?")
fig_capt = px.bar(
    f.groupby("CAPTACIÓN")["IMPORTE ESTIMADO (SIN IVA)"].sum().reset_index().sort_values("IMPORTE ESTIMADO (SIN IVA)", ascending=False),
    x="CAPTACIÓN", y="IMPORTE ESTIMADO (SIN IVA)", color="CAPTACIÓN", text_auto=",.2f"
)
fig_capt.update_layout(template="plotly_dark", height=400)
st.plotly_chart(fig_capt, use_container_width=True)
with st.expander("ℹ️ ¿Qué significa cada canal de captación?"):
    st.markdown("""
    ⚠️ **Nota:** esta columna mezcla dos ideas distintas (el *canal* por el que llegó la oportunidad y, en el caso de "Turismo", el *sector*), y cada fila solo puede tener un valor. Por eso un proyecto turístico captado por concurso aparecerá como "Turismo" o como "Concurso abierto", pero no como ambos a la vez — están pendientes de separar en el Excel si se quiere un análisis más preciso.

    - **Concurso abierto**: licitación pública a la que puede presentarse cualquier empresa que cumpla los requisitos.
    - **Concurso directo**: adjudicación directa o concurso restringido, sin competencia abierta.
    - **Directo**: contacto comercial iniciado directamente por PLAYGOXP con el cliente.
    - **Indirecto**: oportunidad llegada a través de un tercero o intermediario, sin ser partner formal.
    - **Partner**: generada a través de un socio o colaborador estable de la empresa.
    - **Subvención**: proyecto vinculado a una convocatoria de ayuda o subvención pública.
    - **Turismo**: oportunidad del sector turístico, registrada como tal en vez de por su canal real de entrada.
    """)

st.divider()
st.subheader("🏆 Top clientes por importe ponderado (por tipología)")
top_clientes = (
    f.dropna(subset=["TIPOLOGÍA DE CLIENTES"])
     .groupby(["CLIENTE", "TIPOLOGÍA DE CLIENTES"])["IMPORTE PONDERADO (SIN IVA)"]
     .sum().reset_index().sort_values("IMPORTE PONDERADO (SIN IVA)", ascending=False).head(15)
)
fig_top = px.bar(top_clientes, x="CLIENTE", y="IMPORTE PONDERADO (SIN IVA)", color="TIPOLOGÍA DE CLIENTES", text_auto=",.2f")
fig_top.update_layout(template="plotly_dark", height=450)
st.plotly_chart(fig_top, use_container_width=True)

st.divider()
st.subheader("👤 Importe por responsable")
resp_data = f[~f["RESPONSABLE"].str.contains("Marcos|Ruth", case=False, na=False)]
fig_resp = px.bar(
    resp_data.groupby("RESPONSABLE")["IMPORTE ESTIMADO (SIN IVA)"].sum().reset_index(),
    x="RESPONSABLE", y="IMPORTE ESTIMADO (SIN IVA)", color="RESPONSABLE", text_auto=",.2f"
)
fig_resp.update_layout(template="plotly_dark", height=400)
st.plotly_chart(fig_resp, use_container_width=True)

st.divider()
st.subheader("Situación del pipeline por estado")
fig_pipeline = px.pie(f, names="ESTADO")
fig_pipeline.update_layout(template="plotly_dark", height=450)
st.plotly_chart(fig_pipeline, use_container_width=True)

st.divider()
with st.expander("📋 Ver tabla completa"):
    st.dataframe(f, use_container_width=True, column_config={
        "IMPORTE ESTIMADO (SIN IVA)": EUR, "IMPORTE PONDERADO (SIN IVA)": EUR
    })
