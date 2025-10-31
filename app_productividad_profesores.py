# app_productividad_profesores.py
# -------------------------------------------------------------
# Herramienta de control de productividad para Profesores
# - Registro periódico por programa/convenio/institución/localidad
# - Métricas y tablero (dashboard)
# - Exportación a Excel/CSV
# - Autenticación y almacenamiento en la nube (Supabase) o modo local (SQLite)
# -------------------------------------------------------------

import os
import io
from datetime import datetime, date
from typing import Optional, Dict, Any, List

import pandas as pd
import numpy as np

import streamlit as st

# Gráficos
import plotly.express as px

# Base de datos local (fallback)
import sqlite3

# Supabase (si está disponible)
try:
    from supabase import create_client, Client  # type: ignore
except Exception:
    create_client = None
    Client = None

# -------------------------------------------------------------
# CONFIGURACIÓN BÁSICA
# -------------------------------------------------------------
APP_TITLE = "Productividad de Profesores"
APP_ICON = "📊"
DB_SQLITE_PATH = "productividad_profesores.db"  # archivo local cuando no use Supabase

st.set_page_config(page_title=APP_TITLE, page_icon=APP_ICON, layout="wide")

# -------------------------------------------------------------
# UTILIDADES
# -------------------------------------------------------------

def _now_tzless() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def success_toast(msg: str):
    st.toast(msg, icon="✅")


def warn_toast(msg: str):
    st.toast(msg, icon="⚠️")


def error_toast(msg: str):
    st.toast(msg, icon="❌")


# -------------------------------------------------------------
# CONEXIÓN A SUPABASE O SQLITE
# -------------------------------------------------------------

def get_supabase_client() -> Optional["Client"]:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not (url and key and create_client):
        return None
    try:
        return create_client(url, key)
    except Exception:
        return None


SUPABASE: Optional["Client"] = get_supabase_client()


def get_sqlite_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_SQLITE_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


SQLITE_CONN: Optional[sqlite3.Connection] = None if SUPABASE else get_sqlite_conn()


# -------------------------------------------------------------
# ESQUEMA DE DATOS (SQLite)
# -------------------------------------------------------------
SQLITE_DDL = {
    "usuarios": """
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            nombre TEXT,
            rol TEXT DEFAULT 'profesor', -- 'admin' | 'profesor'
            creado_en TEXT
        );
    """,
    "programas": """
        CREATE TABLE IF NOT EXISTS programas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            activo INTEGER DEFAULT 1
        );
    """,
    "convenios": """
        CREATE TABLE IF NOT EXISTS convenios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            programa_id INTEGER NOT NULL,
            activo INTEGER DEFAULT 1,
            UNIQUE(nombre, programa_id),
            FOREIGN KEY(programa_id) REFERENCES programas(id)
        );
    """,
    "instituciones": """
        CREATE TABLE IF NOT EXISTS instituciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            localidad TEXT,
            municipio TEXT,
            departamento TEXT,
            activo INTEGER DEFAULT 1,
            UNIQUE(nombre, municipio, departamento)
        );
    """,
    "profesores": """
        CREATE TABLE IF NOT EXISTS profesores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            documento TEXT,
            email TEXT,
            programa_id INTEGER,
            convenio_id INTEGER,
            activo INTEGER DEFAULT 1,
            UNIQUE(email, programa_id, convenio_id),
            FOREIGN KEY(programa_id) REFERENCES programas(id),
            FOREIGN KEY(convenio_id) REFERENCES convenios(id)
        );
    """,
    "registros": """
        CREATE TABLE IF NOT EXISTS registros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            programa_id INTEGER NOT NULL,
            convenio_id INTEGER NOT NULL,
            institucion_id INTEGER NOT NULL,
            profesor_id INTEGER NOT NULL,
            localidad TEXT,
            municipio TEXT,
            departamento TEXT,
            pacientes_programados INTEGER NOT NULL,
            pacientes_atendidos INTEGER NOT NULL,
            observaciones TEXT,
            creado_por TEXT,
            creado_en TEXT,
            actualizado_en TEXT,
            FOREIGN KEY(programa_id) REFERENCES programas(id),
            FOREIGN KEY(convenio_id) REFERENCES convenios(id),
            FOREIGN KEY(institucion_id) REFERENCES instituciones(id),
            FOREIGN KEY(profesor_id) REFERENCES profesores(id)
        );
    """,
}

if SQLITE_CONN:
    with SQLITE_CONN:
        for ddl in SQLITE_DDL.values():
            SQLITE_CONN.execute(ddl)


# -------------------------------------------------------------
# CAPA DE DATOS: CRUD
# -------------------------------------------------------------

class DataAccess:
    def __init__(self, sb: Optional["Client"], sqlite_conn: Optional[sqlite3.Connection]):
        self.sb = sb
        self.sqlite = sqlite_conn

    # -------------------- PROGRAMAS --------------------
    def list_programas(self) -> pd.DataFrame:
        if self.sb:
            res = self.sb.table("programas").select("*").eq("activo", True).execute()
            return pd.DataFrame(res.data)
        else:
            return pd.read_sql_query("SELECT * FROM programas WHERE activo=1 ORDER BY nombre", self.sqlite)

    def upsert_programa(self, nombre: str) -> None:
        if not nombre:
            return
        if self.sb:
            self.sb.table("programas").upsert({"nombre": nombre, "activo": True}).execute()
        else:
            with self.sqlite:
                self.sqlite.execute(
                    "INSERT OR IGNORE INTO programas(nombre, activo) VALUES(?, 1)",
                    (nombre.strip(),),
                )

    # -------------------- CONVENIOS --------------------
    def list_convenios(self, programa_id: Optional[int] = None) -> pd.DataFrame:
        if self.sb:
            q = self.sb.table("convenios").select("*").eq("activo", True)
            if programa_id:
                q = q.eq("programa_id", programa_id)
            res = q.execute()
            return pd.DataFrame(res.data)
        else:
            if programa_id:
                return pd.read_sql_query(
                    "SELECT * FROM convenios WHERE activo=1 AND programa_id=? ORDER BY nombre",
                    self.sqlite,
                    params=(programa_id,),
                )
            return pd.read_sql_query(
                "SELECT * FROM convenios WHERE activo=1 ORDER BY nombre",
                self.sqlite,
            )

    def upsert_convenio(self, nombre: str, programa_id: int) -> None:
        if not (nombre and programa_id):
            return
        if self.sb:
            self.sb.table("convenios").upsert({
                "nombre": nombre.strip(),
                "programa_id": programa_id,
                "activo": True,
            }).execute()
        else:
            with self.sqlite:
                self.sqlite.execute(
                    "INSERT OR IGNORE INTO convenios(nombre, programa_id, activo) VALUES(?, ?, 1)",
                    (nombre.strip(), programa_id),
                )

    # -------------------- INSTITUCIONES --------------------
    def list_instituciones(self) -> pd.DataFrame:
        if self.sb:
            res = self.sb.table("instituciones").select("*").eq("activo", True).execute()
            return pd.DataFrame(res.data)
        else:
            return pd.read_sql_query(
                "SELECT * FROM instituciones WHERE activo=1 ORDER BY departamento, municipio, nombre",
                self.sqlite,
            )

    def upsert_institucion(self, nombre: str, localidad: str, municipio: str, departamento: str) -> None:
        if self.sb:
            self.sb.table("instituciones").upsert({
                "nombre": nombre.strip(),
                "localidad": localidad.strip() if localidad else None,
                "municipio": municipio.strip() if municipio else None,
                "departamento": departamento.strip() if departamento else None,
                "activo": True,
            }).execute()
        else:
            with self.sqlite:
                self.sqlite.execute(
                    """
                    INSERT OR IGNORE INTO instituciones(nombre, localidad, municipio, departamento, activo)
                    VALUES(?,?,?,?,1)
                    """,
                    (nombre.strip(), localidad or None, municipio or None, departamento or None),
                )

    # -------------------- PROFESORES --------------------
    def list_profesores(self, programa_id: Optional[int] = None, convenio_id: Optional[int] = None) -> pd.DataFrame:
        if self.sb:
            q = self.sb.table("profesores").select("*").eq("activo", True)
            if programa_id:
                q = q.eq("programa_id", programa_id)
            if convenio_id:
                q = q.eq("convenio_id", convenio_id)
            res = q.execute()
            return pd.DataFrame(res.data)
        else:
            base = "SELECT * FROM profesores WHERE activo=1"
            params: List[Any] = []
            if programa_id:
                base += " AND programa_id=?"
                params.append(programa_id)
            if convenio_id:
                base += " AND convenio_id=?"
                params.append(convenio_id)
            base += " ORDER BY nombre"
            return pd.read_sql_query(base, self.sqlite, params=params)

    def upsert_profesor(self, nombre: str, documento: str, email: str, programa_id: Optional[int], convenio_id: Optional[int]) -> None:
        if self.sb:
            self.sb.table("profesores").upsert({
                "nombre": nombre.strip(),
                "documento": documento.strip() if documento else None,
                "email": email.strip() if email else None,
                "programa_id": programa_id,
                "convenio_id": convenio_id,
                "activo": True,
            }).execute()
        else:
            with self.sqlite:
                self.sqlite.execute(
                    """
                    INSERT OR IGNORE INTO profesores(nombre, documento, email, programa_id, convenio_id, activo)
                    VALUES(?,?,?,?,?,1)
                    """,
                    (nombre.strip(), documento or None, email or None, programa_id, convenio_id),
                )

    # -------------------- REGISTROS (PRODUCTIVIDAD) --------------------
    def insert_registro(
        self,
        fecha: date,
        programa_id: int,
        convenio_id: int,
        institucion_id: int,
        profesor_id: int,
        localidad: Optional[str],
        municipio: Optional[str],
        departamento: Optional[str],
        programados: int,
        atendidos: int,
        observaciones: Optional[str],
        creado_por: Optional[str],
    ) -> None:
        row = {
            "fecha": fecha.strftime("%Y-%m-%d"),
            "programa_id": programa_id,
            "convenio_id": convenio_id,
            "institucion_id": institucion_id,
            "profesor_id": profesor_id,
            "localidad": localidad,
            "municipio": municipio,
            "departamento": departamento,
            "pacientes_programados": int(programados),
            "pacientes_atendidos": int(atendidos),
            "observaciones": observaciones,
            "creado_por": creado_por,
            "creado_en": _now_tzless(),
            "actualizado_en": _now_tzless(),
        }
        if self.sb:
            self.sb.table("registros").insert(row).execute()
        else:
            cols = ",".join(row.keys())
            placeholders = ",".join(["?"] * len(row))
            with self.sqlite:
                self.sqlite.execute(
                    f"INSERT INTO registros ({cols}) VALUES ({placeholders})",
                    tuple(row.values()),
                )

    def list_registros(self, filtros: Dict[str, Any]) -> pd.DataFrame:
        # filtros: fecha_desde, fecha_hasta, programa_id, convenio_id, profesor_id, departamento, municipio, institucion_id
        if self.sb:
            q = self.sb.table("registros").select("*")
            if filtros.get("fecha_desde"):
                q = q.gte("fecha", filtros["fecha_desde"].strftime("%Y-%m-%d"))
            if filtros.get("fecha_hasta"):
                q = q.lte("fecha", filtros["fecha_hasta"].strftime("%Y-%m-%d"))
            for k in ["programa_id", "convenio_id", "profesor_id", "institucion_id"]:
                if filtros.get(k):
                    q = q.eq(k, filtros[k])
            for k in ["departamento", "municipio"]:
                if filtros.get(k):
                    q = q.eq(k, filtros[k])
            res = q.execute()
            df = pd.DataFrame(res.data)
            # traer nombres con llamadas adicionales (simple para evitar complejidad de RPC/joins)
            def fetch_name(table, id_value):
                if id_value is None: 
                    return None
                try:
                    r = self.sb.table(table).select("nombre").eq("id", id_value).execute()
                    if r.data:
                        return r.data[0].get("nombre")
                except Exception:
                    return None
                return None
            if not df.empty:
                df["programa"] = df["programa_id"].apply(lambda v: fetch_name("programas", v))
                df["convenio"] = df["convenio_id"].apply(lambda v: fetch_name("convenios", v))
                df["institucion"] = df["institucion_id"].apply(lambda v: fetch_name("instituciones", v))
                df["profesor"] = df["profesor_id"].apply(lambda v: fetch_name("profesores", v))
        else:
            base = """SELECT r.*, p.nombre AS programa, c.nombre AS convenio, i.nombre AS institucion, f.nombre AS profesor, f.email AS profesor_email
                      FROM registros r
                      LEFT JOIN programas p ON p.id=r.programa_id
                      LEFT JOIN convenios c ON c.id=r.convenio_id
                      LEFT JOIN instituciones i ON i.id=r.institucion_id
                      LEFT JOIN profesores f ON f.id=r.profesor_id
                      WHERE 1=1"""
            params: List[Any] = []
            if filtros.get("fecha_desde"):
                base += " AND date(r.fecha) >= date(?)"
                params.append(filtros["fecha_desde"].strftime("%Y-%m-%d"))
            if filtros.get("fecha_hasta"):
                base += " AND date(r.fecha) <= date(?)"
                params.append(filtros["fecha_hasta"].strftime("%Y-%m-%d"))
            for k in ["programa_id", "convenio_id", "profesor_id", "institucion_id"]:
                if filtros.get(k):
                    base += f" AND r.{k} = ?"
                    params.append(filtros[k])
            for k in ["departamento", "municipio"]:
                if filtros.get(k):
                    base += f" AND r.{k} = ?"
                    params.append(filtros[k])
            base += " ORDER BY r.fecha DESC, r.id DESC"
            df = pd.read_sql_query(base, self.sqlite, params=params)
        # Derivados
        if not df.empty:
            df["no_asistieron"] = df["pacientes_programados"].fillna(0) - df["pacientes_atendidos"].fillna(0)
            df["tasa_atencion"] = np.where(
                df["pacientes_programados"].fillna(0) > 0,
                df["pacientes_atendidos"].fillna(0) / df["pacientes_programados"].replace(0, np.nan),
                np.nan,
            )
        return df

    def delete_registro(self, registro_id: int) -> None:
        if self.sb:
            self.sb.table("registros").delete().eq("id", registro_id).execute()
        else:
            with self.sqlite:
                self.sqlite.execute("DELETE FROM registros WHERE id=?", (registro_id,))

    def update_registro(self, registro_id: int, updates: Dict[str, Any]) -> None:
        updates["actualizado_en"] = _now_tzless()
        if self.sb:
            self.sb.table("registros").update(updates).eq("id", registro_id).execute()
        else:
            set_clause = ",".join([f"{k}=?" for k in updates.keys()])
            with self.sqlite:
                self.sqlite.execute(
                    f"UPDATE registros SET {set_clause} WHERE id=?",
                    (*updates.values(), registro_id),
                )


DATA = DataAccess(SUPABASE, SQLITE_CONN)

# -------------------------------------------------------------
# AUTENTICACIÓN (solo cuando haya Supabase). En SQLite, modo libre.
# -------------------------------------------------------------

def ensure_session_state():
    if "auth_user" not in st.session_state:
        st.session_state.auth_user = None
    if "filters" not in st.session_state:
        st.session_state.filters = {}


def render_login_supabase():
    st.markdown("#### Iniciar sesión")
    with st.form("login_form", clear_on_submit=False):
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Contraseña", type="password", key="login_pwd")
        submitted = st.form_submit_button("Ingresar", use_container_width=True)
    if submitted:
        try:
            auth = SUPABASE.auth.sign_in_with_password({"email": email, "password": password})
            st.session_state.auth_user = {
                "email": auth.user.email,
                "id": auth.user.id,
            }
            success_toast("Has iniciado sesión")
            st.rerun()
        except Exception:
            error_toast("No fue posible iniciar sesión. Verifica credenciales.")


def render_logout_supabase():
    if st.button("Cerrar sesión", help="Salir de la cuenta actual", type="secondary"):
        try:
            SUPABASE.auth.sign_out()
        except Exception:
            pass
        st.session_state.auth_user = None
        st.rerun()


# -------------------------------------------------------------
# UI: Sidebar filtros
# -------------------------------------------------------------

def sidebar_filters():
    st.sidebar.header("Filtros")
    hoy = date.today()
    default_from = hoy.replace(day=1)
    default_to = hoy

    f_desde = st.sidebar.date_input("Desde", key="sb_desde", value=st.session_state.filters.get("fecha_desde", default_from))
    f_hasta = st.sidebar.date_input("Hasta", key="sb_hasta", value=st.session_state.filters.get("fecha_hasta", default_to))

    programas = DATA.list_programas()
    prog_map = {r["nombre"]: int(r["id"]) for _, r in programas.iterrows()} if not programas.empty else {}
    prog_sel = st.sidebar.selectbox("Programa", key="sb_programa", options=["(Todos)"] + list(prog_map.keys()))
    programa_id = prog_map.get(prog_sel)

    convenios = DATA.list_convenios(programa_id=programa_id) if programa_id else DATA.list_convenios()
    conv_map = {r["nombre"]: int(r["id"]) for _, r in convenios.iterrows()} if not convenios.empty else {}
    conv_sel = st.sidebar.selectbox("Convenio", key="sb_convenio", options=["(Todos)"] + list(conv_map.keys()))
    convenio_id = conv_map.get(conv_sel)

    profesores = DATA.list_profesores(programa_id=programa_id, convenio_id=convenio_id)
    prof_map = {r["nombre"]: int(r["id"]) for _, r in profesores.iterrows()} if not profesores.empty else {}
    prof_sel = st.sidebar.selectbox("Profesor", key="sb_profesor", options=["(Todos)"] + list(prof_map.keys()))
    profesor_id = prof_map.get(prof_sel)

    instituciones = DATA.list_instituciones()
    inst_map = {f"{r['nombre']} ({r['municipio'] or ''}-{r['departamento'] or ''})": int(r["id"]) for _, r in instituciones.iterrows()} if not instituciones.empty else {}
    inst_sel = st.sidebar.selectbox("Institución", key="sb_institucion", options=["(Todas)"] + list(inst_map.keys()))
    institucion_id = inst_map.get(inst_sel)

    departamento = st.sidebar.text_input("Departamento (exacto)", key="sb_departamento", value=st.session_state.filters.get("departamento", ""))
    municipio = st.sidebar.text_input("Municipio (exacto)", key="sb_municipio", value=st.session_state.filters.get("municipio", ""))

    st.session_state.filters = {
        "fecha_desde": f_desde,
        "fecha_hasta": f_hasta,
        "programa_id": programa_id,
        "convenio_id": convenio_id,
        "profesor_id": profesor_id,
        "institucion_id": institucion_id,
        "departamento": departamento.strip() or None,
        "municipio": municipio.strip() or None,
    }


# -------------------------------------------------------------
# UI: Cargar datos (formulario)
# -------------------------------------------------------------

def ui_cargar_datos(auth_email: Optional[str]):
    st.subheader("Cargar/Actualizar productividad")

    c1, c2, c3 = st.columns([1.2, 1.1, 1])

    # Selecciones
    programas = DATA.list_programas()
    prog_map = {r["nombre"]: int(r["id"]) for _, r in programas.iterrows()} if not programas.empty else {}
    prog_sel = c1.selectbox("Programa", key="form_programa", options=list(prog_map.keys()) if prog_map else [], index=0 if prog_map else None, placeholder="Selecciona o crea uno en Configuración")
    programa_id = prog_map.get(prog_sel)

    convenios = DATA.list_convenios(programa_id=programa_id) if programa_id else pd.DataFrame()
    conv_map = {r["nombre"]: int(r["id"]) for _, r in convenios.iterrows()} if not convenios.empty else {}
    conv_sel = c1.selectbox("Convenio", key="form_convenio", options=list(conv_map.keys()) if conv_map else [], index=0 if conv_map else None)
    convenio_id = conv_map.get(conv_sel)

    profesores = DATA.list_profesores(programa_id=programa_id, convenio_id=convenio_id)
    prof_map = {r["nombre"]: int(r["id"]) for _, r in profesores.iterrows()} if not profesores.empty else {}
    prof_sel = c2.selectbox("Profesor", key="form_profesor", options=list(prof_map.keys()) if prof_map else [], index=0 if prof_map else None)
    profesor_id = prof_map.get(prof_sel)

    instituciones = DATA.list_instituciones()
    inst_map = {f"{r['nombre']} ({r['municipio'] or ''}-{r['departamento'] or ''})": int(r["id"]) for _, r in instituciones.iterrows()} if not instituciones.empty else {}
    inst_sel = c2.selectbox("Institución", key="form_institucion", options=list(inst_map.keys()) if inst_map else [], index=0 if inst_map else None)
    institucion_id = inst_map.get(inst_sel)

    # Geografía (permite sobreescribir lo de la institución si aplica)
    c4, c5, c6, c7 = st.columns([1, 1, 1, 1])
    fecha = c4.date_input("Fecha", key="form_fecha", value=date.today())
    localidad = c5.text_input("Localidad (opcional)", key="form_localidad")
    municipio = c6.text_input("Municipio (opcional)", key="form_municipio")
    departamento = c7.text_input("Departamento (opcional)", key="form_departamento")

    c8, c9, c10 = st.columns([1, 1, 2])
    programados = c8.number_input("Pacientes programados", key="form_prognum", min_value=0, step=1)
    atendidos = c9.number_input("Pacientes atendidos", key="form_attnum", min_value=0, step=1)
    observaciones = c10.text_area("Observaciones", key="form_observaciones", placeholder="Notas relevantes de la jornada")

    left, right = st.columns([1, 1])
    if left.button("Guardar registro", type="primary", use_container_width=True, disabled=not all([programa_id, convenio_id, profesor_id, institucion_id])):
        if atendidos > programados:
            warn_toast("Los atendidos no pueden ser mayores que los programados. Ajusta los valores.")
        else:
            try:
                DATA.insert_registro(
                    fecha=fecha,
                    programa_id=int(programa_id),
                    convenio_id=int(convenio_id),
                    institucion_id=int(institucion_id),
                    profesor_id=int(profesor_id),
                    localidad=localidad or None,
                    municipio=municipio or None,
                    departamento=departamento or None,
                    programados=int(programados),
                    atendidos=int(atendidos),
                    observaciones=observaciones or None,
                    creado_por=auth_email,
                )
                success_toast("Registro guardado")
                st.experimental_rerun()
            except Exception as e:
                error_toast(f"Error al guardar: {e}")


# -------------------------------------------------------------
# UI: Registros (tabla + acciones)
# -------------------------------------------------------------

def ui_registros():
    st.subheader("Registros capturados")

    df = DATA.list_registros(st.session_state.filters)
    if df.empty:
        st.info("No hay registros con los filtros actuales.")
        return

    show_cols = [
        "id", "fecha", "programa", "convenio", "institucion", "profesor",
        "departamento", "municipio", "localidad",
        "pacientes_programados", "pacientes_atendidos", "no_asistieron", "tasa_atencion",
        "observaciones", "creado_por", "creado_en", "actualizado_en",
    ]

    if "tasa_atencion" in df.columns:
        df["tasa_atencion_%"] = (df["tasa_atencion"] * 100).round(1)

    st.dataframe(df[[c for c in show_cols if c in df.columns]], use_container_width=True, hide_index=True)

    st.markdown("---")
    c1, c2, c3 = st.columns([1, 1, 3])
    id_sel = c1.number_input("ID de registro", key="reg_id_sel", min_value=1, step=1)
    if c2.button("Eliminar", use_container_width=True):
        try:
            DATA.delete_registro(int(id_sel))
            success_toast("Registro eliminado")
            st.experimental_rerun()
        except Exception as e:
            error_toast(f"No se pudo eliminar: {e}")

    with st.expander("Editar registro (campos rápidos)"):
        c4, c5, c6 = st.columns(3)
        upd_programados = c4.number_input("Programados (nuevo)", min_value=0, step=1, key="upd_prog")
        upd_atendidos = c5.number_input("Atendidos (nuevo)", min_value=0, step=1, key="upd_att")
        upd_obs = c6.text_input("Observaciones (nuevo)", key="upd_obs")
        if st.button("Guardar cambios", type="primary"):
            if upd_atendidos > upd_programados:
                warn_toast("Atendidos no puede superar Programados")
            else:
                try:
                    DATA.update_registro(int(id_sel), {
                        "pacientes_programados": int(upd_programados),
                        "pacientes_atendidos": int(upd_atendidos),
                        "observaciones": upd_obs or None,
                    })
                    success_toast("Actualizado")
                    st.experimental_rerun()
                except Exception as e:
                    error_toast(f"No se pudo actualizar: {e}")


# -------------------------------------------------------------
# UI: Dashboard (métricas y gráficos)
# -------------------------------------------------------------

def ui_dashboard():
    st.subheader("Dashboard de gestión")

    df = DATA.list_registros(st.session_state.filters)
    if df.empty:
        st.info("No hay datos para graficar con los filtros actuales.")
        return

    df["fecha"] = pd.to_datetime(df["fecha"])

    total_prog = int(df["pacientes_programados"].fillna(0).sum())
    total_att = int(df["pacientes_atendidos"].fillna(0).sum())
    total_no = int((df["pacientes_programados"].fillna(0) - df["pacientes_atendidos"].fillna(0)).sum())
    tasa = (total_att / total_prog * 100) if total_prog else 0.0

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Programados", f"{total_prog:,}".replace(",", "."))
    k2.metric("Atendidos", f"{total_att:,}".replace(",", "."))
    k3.metric("No asistieron", f"{total_no:,}".replace(",", "."))
    k4.metric("Tasa de atención", f"{tasa:.1f}%")

    # Tendencia temporal (semanal)
    tdf = (
        df.groupby(pd.Grouper(key="fecha", freq="W"))[["pacientes_programados", "pacientes_atendidos"]]
          .sum().reset_index()
    )
    fig1 = px.line(tdf, x="fecha", y=["pacientes_programados", "pacientes_atendidos"], markers=True, title="Tendencia semanal")
    st.plotly_chart(fig1, use_container_width=True)

    # Ranking de profesores por atendidos
    if "profesor" not in df.columns and "profesores" in df.columns:
        df["profesor"] = df["profesores"].apply(lambda x: x.get("nombre") if isinstance(x, dict) else None)
    rank_prof = df.groupby("profesor", dropna=True)["pacientes_atendidos"].sum().sort_values(ascending=False).head(15).reset_index()
    fig2 = px.bar(rank_prof, x="profesor", y="pacientes_atendidos", title="Top profesores por atendidos")
    fig2.update_layout(xaxis_tickangle=-40)
    st.plotly_chart(fig2, use_container_width=True)

    # Distribución por institución
    if "institucion" not in df.columns and "instituciones" in df.columns:
        df["institucion"] = df["instituciones"].apply(lambda x: x.get("nombre") if isinstance(x, dict) else None)
    inst_sum = df.groupby("institucion", dropna=True)[["pacientes_programados", "pacientes_atendidos"]].sum().sort_values(by="pacientes_atendidos", ascending=False).head(15).reset_index()
    fig3 = px.bar(inst_sum, x="institucion", y=["pacientes_programados", "pacientes_atendidos"], barmode="group", title="Instituciones con mayor actividad")
    fig3.update_layout(xaxis_tickangle=-40)
    st.plotly_chart(fig3, use_container_width=True)

    # Calor por departamento (barra)
    dep_sum = df.groupby("departamento", dropna=True)["pacientes_atendidos"].sum().sort_values(ascending=False).reset_index()
    fig4 = px.bar(dep_sum, x="departamento", y="pacientes_atendidos", title="Atendidos por departamento")
    st.plotly_chart(fig4, use_container_width=True)


# -------------------------------------------------------------
# UI: Reportes (exportación)
# -------------------------------------------------------------

def to_excel_bytes(multi_sheets: Dict[str, pd.DataFrame]) -> bytes:
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        for name, df in multi_sheets.items():
            safe = df.copy()
            safe.columns = [str(c)[:40] for c in safe.columns]
            safe.to_excel(writer, sheet_name=name[:31], index=False)
    return out.getvalue()


def ui_reportes():
    st.subheader("Reportes y descargas")

    df = DATA.list_registros(st.session_state.filters)
    if df.empty:
        st.info("No hay registros con los filtros actuales.")
        return

    por_prof = df.groupby("profesor", dropna=True)[["pacientes_programados", "pacientes_atendidos"]].sum().reset_index()
    por_prof["tasa_atencion"] = np.where(
        por_prof["pacientes_programados"] > 0,
        por_prof["pacientes_atendidos"] / por_prof["pacientes_programados"],
        np.nan,
    )

    por_inst = df.groupby("institucion", dropna=True)[["pacientes_programados", "pacientes_atendidos"]].sum().reset_index()
    por_geo = df.groupby(["departamento", "municipio"], dropna=True)[["pacientes_programados", "pacientes_atendidos"]].sum().reset_index()

    xls = to_excel_bytes({
        "Detalle": df,
        "Por_profesor": por_prof,
        "Por_institucion": por_inst,
        "Por_geo": por_geo,
    })
    st.download_button(
        label="Descargar Excel (.xlsx)",
        data=xls,
        file_name=f"productividad_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    st.download_button(
        label="Descargar detalle (.csv)",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=f"productividad_detalle_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
        use_container_width=True,
    )


# -------------------------------------------------------------
# UI: Configuración Catálogos
# -------------------------------------------------------------

def ui_configuracion():
    st.subheader("Configuración de catálogos")

    tabs = st.tabs(["Programas", "Convenios", "Instituciones", "Profesores"])

    # ----- Programas -----
    with tabs[0]:
        c1, c2 = st.columns([2, 1])
        p_nombre = c1.text_input("Nombre del programa", key="cfg_prog_nombre")
        if c2.button("Agregar programa", use_container_width=True):
            if not p_nombre.strip():
                warn_toast("Escribe un nombre de programa")
            else:
                DATA.upsert_programa(p_nombre.strip())
                success_toast("Programa agregado/actualizado")
                st.experimental_rerun()
        st.markdown("**Programas activos**")
        st.dataframe(DATA.list_programas(), use_container_width=True, hide_index=True)

    # ----- Convenios -----
    with tabs[1]:
        programas = DATA.list_programas()
        prog_map = {r["nombre"]: int(r["id"]) for _, r in programas.iterrows()} if not programas.empty else {}
        c1, c2, c3 = st.columns([2, 2, 1])
        cv_prog = c1.selectbox("Programa", key="cfg_conv_prog", options=list(prog_map.keys()) if prog_map else [])
        cv_nombre = c2.text_input("Nombre del convenio", key="cfg_conv_nombre")
        if c3.button("Agregar convenio", use_container_width=True, disabled=not (prog_map and cv_nombre)):
            DATA.upsert_convenio(cv_nombre.strip(), prog_map[cv_prog])
            success_toast("Convenio agregado/actualizado")
            st.experimental_rerun()
        st.markdown("**Convenios activos**")
        st.dataframe(DATA.list_convenios(), use_container_width=True, hide_index=True)

    # ----- Instituciones -----
    with tabs[2]:
        c1, c2, c3, c4, c5 = st.columns([2, 1.2, 1.2, 1.2, 1])
        i_nombre = c1.text_input("Nombre institución", key="cfg_inst_nombre")
        i_localidad = c2.text_input("Localidad", key="cfg_inst_localidad")
        i_municipio = c3.text_input("Municipio", key="cfg_inst_municipio")
        i_departamento = c4.text_input("Departamento", key="cfg_inst_departamento")
        if c5.button("Agregar institución", use_container_width=True, disabled=not i_nombre.strip()):
            DATA.upsert_institucion(i_nombre.strip(), i_localidad, i_municipio, i_departamento)
            success_toast("Institución agregada/actualizada")
            st.experimental_rerun()
        st.markdown("**Instituciones activas**")
        st.dataframe(DATA.list_instituciones(), use_container_width=True, hide_index=True)

    # ----- Profesores -----
    with tabs[3]:
        programas = DATA.list_programas()
        prog_map = {r["nombre"]: int(r["id"]) for _, r in programas.iterrows()} if not programas.empty else {}
        convenios = DATA.list_convenios()
        conv_map = {r["nombre"]: int(r["id"]) for _, r in convenios.iterrows()} if not convenios.empty else {}
        c1, c2, c3, c4, c5 = st.columns([2, 1.2, 1.4, 1.2, 1.2])
        f_nombre = c1.text_input("Nombre profesor/a", key="cfg_prof_nombre")
        f_doc = c2.text_input("Documento (opcional)", key="cfg_prof_doc")
        f_email = c3.text_input("Email (opcional)", key="cfg_prof_email")
        f_prog = c4.selectbox("Programa", options=list(prog_map.keys()) if prog_map else [], key="cfg_prof_programa")
        f_conv = c5.selectbox("Convenio", options=list(conv_map.keys()) if conv_map else [], key="cfg_prof_convenio")
        if st.button("Agregar profesor/a", use_container_width=True, disabled=not f_nombre.strip()):
            DATA.upsert_profesor(f_nombre.strip(), f_doc.strip(), f_email.strip(), prog_map.get(f_prog), conv_map.get(f_conv))
            success_toast("Profesor/a agregado/a")
            st.experimental_rerun()
        st.markdown("**Profesores activos**")
        st.dataframe(DATA.list_profesores(), use_container_width=True, hide_index=True)


# -------------------------------------------------------------
# LAYOUT PRINCIPAL
# -------------------------------------------------------------

def main():
    ensure_session_state()

    st.markdown(f"# {APP_ICON} {APP_TITLE}")
    if SUPABASE:
        st.caption("Conectado a Supabase (modo nube). Si prefieres, deja variables vacías para usar SQLite local.")
    else:
        st.caption("Modo local con SQLite. Para modo nube, define SUPABASE_URL y SUPABASE_KEY.")

    # Sidebar filtros
    sidebar_filters()

    # Autenticación
    auth_email = None
    if SUPABASE:
        if not st.session_state.auth_user:
            with st.sidebar:
                render_login_supabase()
        else:
            auth_email = st.session_state.auth_user.get("email")
            with st.sidebar:
                st.success(f"Sesión: {auth_email}")
                render_logout_supabase()

    tabs = st.tabs(["Cargar datos", "Registros", "Dashboard", "Reportes", "Configuración"])

    with tabs[0]:
        ui_cargar_datos(auth_email)
    with tabs[1]:
        ui_registros()
    with tabs[2]:
        ui_dashboard()
    with tabs[3]:
        ui_reportes()
    with tabs[4]:
        ui_configuracion()


if __name__ == "__main__":
    main()
