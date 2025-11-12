# app_productividad_profesores.py
# -------------------------------------------------------------
# Productividad de Profesionales (Enterprise)
# -------------------------------------------------------------

import os
import io
from datetime import datetime, date
from typing import Optional, Dict, Any, List

import pandas as pd
import numpy as np

import streamlit as st
import plotly.express as px

import sqlite3

try:
    from supabase import create_client, Client  # type: ignore
except Exception:  # pragma: no cover
    create_client = None
    Client = None


APP_TITLE = "Dashboard de Profesionales"
APP_ICON = "📊"
DB_SQLITE_PATH = "productividad_profesionales.db"

ACTIVIDADES_PLANTILLAS = [
    "VALORACION INICIAL POR PSICOLOGIA",
    "CONTIGO PROFE EN AULA",
    "PRIMEROS AUXILIOS PSICOLOGICO",
    "APOYO TERAPEUTICO Y SEGUIMIENTO",
]

TIPOS_CONTACTO = [
    "Presencial",
    "Virtual",
    "Telefónico",
    "Otro",
]

st.set_page_config(page_title=APP_TITLE, page_icon=APP_ICON, layout="wide")


def _now_tzless() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def success_toast(msg: str):
    st.toast(msg, icon="✅")


def warn_toast(msg: str):
    st.toast(msg, icon="⚠️")


def error_toast(msg: str):
    st.toast(msg, icon="❌")


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


SQLITE_DDL = {
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
    "pacientes": """
        CREATE TABLE IF NOT EXISTS pacientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_documento TEXT UNIQUE NOT NULL,
            nombre TEXT NOT NULL,
            fecha_nacimiento TEXT,
            sexo TEXT,
            telefono TEXT,
            email TEXT,
            direccion TEXT,
            localidad TEXT,
            municipio TEXT,
            departamento TEXT,
            activo INTEGER DEFAULT 1
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
            paciente_id INTEGER,
            localidad TEXT,
            municipio TEXT,
            departamento TEXT,
            numero_paciente TEXT,
            nombre_paciente TEXT,
            actividad TEXT,
            atendido INTEGER,
            registrado_panacea INTEGER,
            duracion_minutos INTEGER,
            tipo_contacto TEXT,
            pacientes_programados INTEGER NOT NULL,
            pacientes_atendidos INTEGER NOT NULL,
            observaciones TEXT,
            creado_por TEXT,
            creado_en TEXT,
            actualizado_en TEXT,
            FOREIGN KEY(programa_id) REFERENCES programas(id),
            FOREIGN KEY(convenio_id) REFERENCES convenios(id),
            FOREIGN KEY(institucion_id) REFERENCES instituciones(id),
            FOREIGN KEY(profesor_id) REFERENCES profesores(id),
            FOREIGN KEY(paciente_id) REFERENCES pacientes(id)
        );
    """,
}


def ensure_sqlite_schema():
    if not SQLITE_CONN:
        return
    with SQLITE_CONN:
        for ddl in SQLITE_DDL.values():
            SQLITE_CONN.execute(ddl)
        cur = SQLITE_CONN.execute("PRAGMA table_info(registros);")
        existing = {row[1] for row in cur.fetchall()}
        needed = {
            "numero_paciente": "ALTER TABLE registros ADD COLUMN numero_paciente TEXT;",
            "nombre_paciente": "ALTER TABLE registros ADD COLUMN nombre_paciente TEXT;",
            "actividad": "ALTER TABLE registros ADD COLUMN actividad TEXT;",
            "atendido": "ALTER TABLE registros ADD COLUMN atendido INTEGER;",
            "registrado_panacea": "ALTER TABLE registros ADD COLUMN registrado_panacea INTEGER;",
            "duracion_minutos": "ALTER TABLE registros ADD COLUMN duracion_minutos INTEGER;",
            "tipo_contacto": "ALTER TABLE registros ADD COLUMN tipo_contacto TEXT;",
            "paciente_id": "ALTER TABLE registros ADD COLUMN paciente_id INTEGER;",
        }
        for col, stmt in needed.items():
            if col not in existing:
                SQLITE_CONN.execute(stmt)


if SQLITE_CONN:
    ensure_sqlite_schema()


class DataAccess:
    def __init__(self, sb: Optional["Client"], sqlite_conn: Optional[sqlite3.Connection]):
        self.sb = sb
        self.sqlite = sqlite_conn

    # -------- Programas / convenios / instituciones / profesores --------
    def list_programas(self) -> pd.DataFrame:
        if self.sb:
            res = self.sb.table("programas").select("*").eq("activo", True).execute()
            return pd.DataFrame(res.data)
        return pd.read_sql_query(
            "SELECT * FROM programas WHERE activo=1 ORDER BY nombre",
            self.sqlite,
        )

    def upsert_programa(self, nombre: str) -> None:
        if not nombre:
            return
        nombre = nombre.strip()
        if self.sb:
            self.sb.table("programas").upsert({"nombre": nombre, "activo": True}).execute()
        else:
            with self.sqlite:
                self.sqlite.execute(
                    "INSERT OR IGNORE INTO programas(nombre, activo) VALUES(?,1)",
                    (nombre,),
                )

    def list_convenios(self, programa_id: Optional[int] = None) -> pd.DataFrame:
        if self.sb:
            q = self.sb.table("convenios").select("*").eq("activo", True)
            if programa_id:
                q = q.eq("programa_id", programa_id)
            res = q.execute()
            return pd.DataFrame(res.data)
        base = "SELECT * FROM convenios WHERE activo=1"
        params: List[Any] = []
        if programa_id:
            base += " AND programa_id=?"
            params.append(programa_id)
        base += " ORDER BY nombre"
        return pd.read_sql_query(base, self.sqlite, params=params)

    def upsert_convenio(self, nombre: str, programa_id: int) -> None:
        if not (nombre and programa_id):
            return
        nombre = nombre.strip()
        if self.sb:
            self.sb.table("convenios").upsert(
                {"nombre": nombre, "programa_id": programa_id, "activo": True}
            ).execute()
        else:
            with self.sqlite:
                self.sqlite.execute(
                    "INSERT OR IGNORE INTO convenios(nombre, programa_id, activo) VALUES(?,?,1)",
                    (nombre, programa_id),
                )

    def list_instituciones(self) -> pd.DataFrame:
        if self.sb:
            res = self.sb.table("instituciones").select("*").eq("activo", True).execute()
            return pd.DataFrame(res.data)
        return pd.read_sql_query(
            "SELECT * FROM instituciones WHERE activo=1 ORDER BY departamento, municipio, nombre",
            self.sqlite,
        )

    def upsert_institucion(self, nombre: str, localidad: str, municipio: str, departamento: str) -> None:
        if not nombre:
            return
        nombre = nombre.strip()
        if self.sb:
            self.sb.table("instituciones").upsert(
                {
                    "nombre": nombre,
                    "localidad": localidad.strip() if localidad else None,
                    "municipio": municipio.strip() if municipio else None,
                    "departamento": departamento.strip() if departamento else None,
                    "activo": True,
                }
            ).execute()
        else:
            with self.sqlite:
                self.sqlite.execute(
                    """
                    INSERT OR IGNORE INTO instituciones(nombre, localidad, municipio, departamento, activo)
                    VALUES(?,?,?,?,1)
                    """,
                    (nombre, localidad or None, municipio or None, departamento or None),
                )

    def list_profesores(self, programa_id: Optional[int] = None, convenio_id: Optional[int] = None) -> pd.DataFrame:
        if self.sb:
            q = self.sb.table("profesores").select("*").eq("activo", True)
            if programa_id:
                q = q.eq("programa_id", programa_id)
            if convenio_id:
                q = q.eq("convenio_id", convenio_id)
            res = q.execute()
            return pd.DataFrame(res.data)
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

    def upsert_profesor(
        self,
        nombre: str,
        documento: Optional[str],
        email: Optional[str],
        programa_id: Optional[int],
        convenio_id: Optional[int],
    ) -> None:
        if not nombre:
            return
        nombre = nombre.strip()
        documento = documento.strip() if documento else None
        email = email.strip() if email else None
        if self.sb:
            self.sb.table("profesores").upsert(
                {
                    "nombre": nombre,
                    "documento": documento,
                    "email": email,
                    "programa_id": programa_id,
                    "convenio_id": convenio_id,
                    "activo": True,
                }
            ).execute()
        else:
            with self.sqlite:
                self.sqlite.execute(
                    """
                    INSERT OR IGNORE INTO profesores(nombre, documento, email, programa_id, convenio_id, activo)
                    VALUES(?,?,?,?,?,1)
                    """,
                    (nombre, documento, email, programa_id, convenio_id),
                )

    # -------- Pacientes ----------
    def list_pacientes(self) -> pd.DataFrame:
        if self.sb:
            res = self.sb.table("pacientes").select("*").eq("activo", True).execute()
            return pd.DataFrame(res.data)
        return pd.read_sql_query(
            "SELECT * FROM pacientes WHERE activo=1 ORDER BY nombre",
            self.sqlite,
        )

    def get_paciente_por_documento(self, numero_documento: str) -> Optional[Dict[str, Any]]:
        numero_documento = (numero_documento or "").strip()
        if not numero_documento:
            return None
        if self.sb:
            res = (
                self.sb.table("pacientes")
                .select("*")
                .eq("numero_documento", numero_documento)
                .limit(1)
                .execute()
            )
            if res.data:
                return res.data[0]
            return None
        cur = self.sqlite.execute(
            "SELECT * FROM pacientes WHERE numero_documento=? AND activo=1",
            (numero_documento,),
        )
        row = cur.fetchone()
        if not row:
            return None
        cur2 = self.sqlite.execute("PRAGMA table_info(pacientes);")
        cols = [r[1] for r in cur2.fetchall()]
        return dict(zip(cols, row))

    def upsert_paciente(
        self,
        numero_documento: str,
        nombre: str,
        fecha_nacimiento: Optional[str] = None,
        sexo: Optional[str] = None,
        telefono: Optional[str] = None,
        email: Optional[str] = None,
        direccion: Optional[str] = None,
        localidad: Optional[str] = None,
        municipio: Optional[str] = None,
        departamento: Optional[str] = None,
    ) -> int:
        numero_documento = (numero_documento or "").strip()
        nombre = (nombre or "").strip()
        if not numero_documento or not nombre:
            raise ValueError("Documento y nombre de paciente son obligatorios")
        if self.sb:
            existing = self.get_paciente_por_documento(numero_documento)
            payload = {
                "numero_documento": numero_documento,
                "nombre": nombre,
                "fecha_nacimiento": fecha_nacimiento,
                "sexo": sexo,
                "telefono": telefono,
                "email": email,
                "direccion": direccion,
                "localidad": localidad,
                "municipio": municipio,
                "departamento": departamento,
                "activo": True,
            }
            if existing:
                self.sb.table("pacientes").update(payload).eq(
                    "numero_documento", numero_documento
                ).execute()
                return int(existing["id"])
            else:
                res = self.sb.table("pacientes").insert(payload).execute()
                if res.data:
                    return int(res.data[0]["id"])
                raise RuntimeError("No se pudo crear paciente en Supabase")
        cur = self.sqlite.execute(
            "SELECT id FROM pacientes WHERE numero_documento=?",
            (numero_documento,),
        )
        row = cur.fetchone()
        data_tuple = (
            nombre,
            fecha_nacimiento,
            sexo,
            telefono,
            email,
            direccion,
            localidad,
            municipio,
            departamento,
        )
        if row:
            pac_id = int(row[0])
            with self.sqlite:
                self.sqlite.execute(
                    """
                    UPDATE pacientes
                    SET nombre=?, fecha_nacimiento=?, sexo=?, telefono=?, email=?,
                        direccion=?, localidad=?, municipio=?, departamento=?
                    WHERE id=?
                    """,
                    (*data_tuple, pac_id),
                )
            return pac_id
        with self.sqlite:
            cur2 = self.sqlite.execute(
                """
                INSERT INTO pacientes(
                    numero_documento, nombre, fecha_nacimiento, sexo, telefono,
                    email, direccion, localidad, municipio, departamento, activo
                )
                VALUES(?,?,?,?,?,?,?,?,?,?,1)
                """,
                (numero_documento, *data_tuple),
            )
        return int(cur2.lastrowid)

    # -------- Registros ----------
    def insert_registro(
        self,
        fecha: date,
        programa_id: int,
        convenio_id: int,
        institucion_id: int,
        profesor_id: int,
        paciente_id: Optional[int],
        localidad: Optional[str],
        municipio: Optional[str],
        departamento: Optional[str],
        numero_paciente: str,
        nombre_paciente: str,
        actividad: str,
        atendido: bool,
        registrado_panacea: bool,
        duracion_minutos: Optional[int],
        tipo_contacto: Optional[str],
        observaciones: Optional[str],
        creado_por: Optional[str],
    ) -> None:
        pacientes_programados = 1
        pacientes_atendidos = 1 if atendido else 0
        row = {
            "fecha": fecha.strftime("%Y-%m-%d"),
            "programa_id": programa_id,
            "convenio_id": convenio_id,
            "institucion_id": institucion_id,
            "profesor_id": profesor_id,
            "paciente_id": paciente_id,
            "localidad": localidad or None,
            "municipio": municipio or None,
            "departamento": departamento or None,
            "numero_paciente": (numero_paciente or "").strip() or None,
            "nombre_paciente": (nombre_paciente or "").strip() or None,
            "actividad": actividad,
            "atendido": 1 if atendido else 0,
            "registrado_panacea": 1 if registrado_panacea else 0,
            "duracion_minutos": int(duracion_minutos) if duracion_minutos is not None else None,
            "tipo_contacto": tipo_contacto or None,
            "pacientes_programados": pacientes_programados,
            "pacientes_atendidos": pacientes_atendidos,
            "observaciones": observaciones or None,
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
        if self.sb:
            q = self.sb.table("registros").select("*")
            if filtros.get("fecha_desde"):
                q = q.gte("fecha", filtros["fecha_desde"].strftime("%Y-%m-%d"))
            if filtros.get("fecha_hasta"):
                q = q.lte("fecha", filtros["fecha_hasta"].strftime("%Y-%m-%d"))
            for k in ["programa_id", "convenio_id", "profesor_id"]:
                if filtros.get(k):
                    q = q.eq(k, filtros[k])
            if filtros.get("actividad"):
                q = q.eq("actividad", filtros["actividad"])
            res = q.execute()
            df = pd.DataFrame(res.data)

            def fetch_name(table: str, id_value: Any) -> Optional[str]:
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
            base = """
                SELECT r.*,
                       p.nombre AS programa,
                       c.nombre AS convenio,
                       i.nombre AS institucion,
                       f.nombre AS profesor,
                       f.email AS profesor_email
                FROM registros r
                LEFT JOIN programas p ON p.id = r.programa_id
                LEFT JOIN convenios c ON c.id = r.convenio_id
                LEFT JOIN instituciones i ON i.id = r.institucion_id
                LEFT JOIN profesores f ON f.id = r.profesor_id
                WHERE 1=1
            """
            params: List[Any] = []
            if filtros.get("fecha_desde"):
                base += " AND date(r.fecha) >= date(?)"
                params.append(filtros["fecha_desde"].strftime("%Y-%m-%d"))
            if filtros.get("fecha_hasta"):
                base += " AND date(r.fecha) <= date(?)"
                params.append(filtros["fecha_hasta"].strftime("%Y-%m-%d"))
            for k in ["programa_id", "convenio_id", "profesor_id"]:
                if filtros.get(k):
                    base += f" AND r.{k} = ?"
                    params.append(filtros[k])
            if filtros.get("actividad"):
                base += " AND r.actividad = ?"
                params.append(filtros["actividad"])
            base += " ORDER BY r.fecha DESC, r.id DESC"
            df = pd.read_sql_query(base, self.sqlite, params=params)

        if not df.empty:
            df["pacientes_programados"] = df["pacientes_programados"].fillna(0)
            df["pacientes_atendidos"] = df["pacientes_atendidos"].fillna(0)
            df["no_asistieron"] = df["pacientes_programados"] - df["pacientes_atendidos"]
            df["tasa_atencion"] = np.where(
                df["pacientes_programados"] > 0,
                df["pacientes_atendidos"] / df["pacientes_programados"],
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
            cols = ",".join([f"{k}=?" for k in updates.keys()])
            with self.sqlite:
                self.sqlite.execute(
                    f"UPDATE registros SET {cols} WHERE id=?",
                    (*updates.values(), registro_id),
                )


DATA = DataAccess(SUPABASE, SQLITE_CONN)


def ensure_session_state():
    if "auth_user" not in st.session_state:
        st.session_state.auth_user = None
    if "filters" not in st.session_state:
        st.session_state.filters = {}
    for key in [
        "pac_doc",
        "pac_nombre",
        "pac_fecha_nac",
        "pac_sexo",
        "pac_telefono",
        "pac_email",
        "pac_direccion",
        "pac_localidad",
        "pac_municipio",
        "pac_departamento",
        "pac_id_actual",
    ]:
        st.session_state.setdefault(key, None)


def render_login_supabase():
    st.markdown("#### Iniciar sesión")
    with st.form("login_form", clear_on_submit=False):
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Contraseña", type="password", key="login_pwd")
        submitted = st.form_submit_button("Ingresar", use_container_width=True)
    if submitted:
        try:
            auth = SUPABASE.auth.sign_in_with_password({"email": email, "password": password})
            st.session_state.auth_user = {"email": auth.user.email, "id": auth.user.id}
            success_toast("Has iniciado sesión")
            st.rerun()
        except Exception:
            error_toast("No fue posible iniciar sesión. Verifica credenciales.")


def render_logout_supabase():
    if st.button("Cerrar sesión", type="secondary", key="btn_logout"):
        try:
            SUPABASE.auth.sign_out()
        except Exception:
            pass
        st.session_state.auth_user = None
        st.rerun()


def sidebar_filters():
    st.sidebar.header("Filtros")
    hoy = date.today()
    default_from = hoy.replace(day=1)
    default_to = hoy

    f_desde = st.sidebar.date_input(
        "Desde",
        value=st.session_state.filters.get("fecha_desde", default_from),
        key="flt_desde",
    )
    f_hasta = st.sidebar.date_input(
        "Hasta",
        value=st.session_state.filters.get("fecha_hasta", default_to),
        key="flt_hasta",
    )

    programas = DATA.list_programas()
    prog_map = {r["nombre"]: int(r["id"]) for _, r in programas.iterrows()} if not programas.empty else {}
    prog_sel = st.sidebar.selectbox(
        "Programa",
        options=["(Todos)"] + list(prog_map.keys()),
        key="flt_programa",
    )
    programa_id = prog_map.get(prog_sel)

    convenios = DATA.list_convenios(programa_id=programa_id) if programa_id else DATA.list_convenios()
    conv_map = {r["nombre"]: int(r["id"]) for _, r in convenios.iterrows()} if not convenios.empty else {}
    conv_sel = st.sidebar.selectbox(
        "Convenio",
        options=["(Todos)"] + list(conv_map.keys()),
        key="flt_convenio",
    )
    convenio_id = conv_map.get(conv_sel)

    profesores = DATA.list_profesores(programa_id=programa_id, convenio_id=convenio_id)
    prof_map = {r["nombre"]: int(r["id"]) for _, r in profesores.iterrows()} if not profesores.empty else {}
    prof_sel = st.sidebar.selectbox(
        "Profesional",
        options=["(Todos)"] + list(prof_map.keys()),
        key="flt_profesional",
    )
    profesor_id = prof_map.get(prof_sel)

    actividad_sel = st.sidebar.selectbox(
        "Actividad / plantilla",
        options=["(Todas)"] + ACTIVIDADES_PLANTILLAS,
        key="flt_actividad",
    )
    actividad = None if actividad_sel == "(Todas)" else actividad_sel

    st.session_state.filters = {
        "fecha_desde": f_desde,
        "fecha_hasta": f_hasta,
        "programa_id": programa_id,
        "convenio_id": convenio_id,
        "profesor_id": profesor_id,
        "actividad": actividad,
    }


def ui_cargar_datos(auth_email: Optional[str]):
    st.subheader("Registrar atención / paciente")

    c1, c2 = st.columns([1.4, 1.4])

    programas = DATA.list_programas()
    prog_map = {r["nombre"]: int(r["id"]) for _, r in programas.iterrows()} if not programas.empty else {}
    prog_sel = c1.selectbox(
        "Programa",
        options=list(prog_map.keys()) if prog_map else [],
        key="form_programa",
        placeholder="Crea programas en Configuración",
    )
    programa_id = prog_map.get(prog_sel)

    convenios = DATA.list_convenios(programa_id=programa_id) if programa_id else pd.DataFrame()
    conv_map = {r["nombre"]: int(r["id"]) for _, r in convenios.iterrows()} if not convenios.empty else {}
    conv_sel = c1.selectbox(
        "Convenio",
        options=list(conv_map.keys()) if conv_map else [],
        key="form_convenio",
    )
    convenio_id = conv_map.get(conv_sel)

    profesores = DATA.list_profesores(programa_id=programa_id, convenio_id=convenio_id)
    prof_map = {r["nombre"]: int(r["id"]) for _, r in profesores.iterrows()} if not profesores.empty else {}
    prof_sel = c2.selectbox(
        "Profesional",
        options=list(prof_map.keys()) if prof_map else [],
        key="form_profesional",
    )
    profesor_id = prof_map.get(prof_sel)

    instituciones = DATA.list_instituciones()
    institucion_id = None
    localidad_val = None
    municipio_val = None
    departamento_val = None

    st.markdown("#### Ubicación e institución")
    if instituciones.empty:
        st.info("No hay instituciones configuradas. Crea instituciones en la pestaña Configuración.")
    else:
        g1, g2, g3, g4 = st.columns([1, 1, 1, 2])
        deps = sorted({str(x) for x in instituciones["departamento"].dropna().unique()})
        dep_sel = g1.selectbox(
            "Departamento",
            options=deps,
            key="form_departamento_sel",
        ) if deps else None

        inst_dep = instituciones
        if dep_sel:
            inst_dep = inst_dep[inst_dep["departamento"] == dep_sel]

        muns = sorted({str(x) for x in inst_dep["municipio"].dropna().unique()})
        mun_sel = g2.selectbox(
            "Municipio",
            options=["(Todos)"] + muns,
            key="form_municipio_sel",
        ) if muns else "(Todos)"

        inst_mun = inst_dep
        if mun_sel and mun_sel != "(Todos)":
            inst_mun = inst_mun[inst_mun["municipio"] == mun_sel]

        locs = sorted({str(x) for x in inst_mun["localidad"].dropna().unique()})
        loc_label = "Localidad (Bogotá)" if dep_sel and "BOGOTA" in dep_sel.upper() else "Localidad"
        loc_sel = g3.selectbox(
            loc_label,
            options=["(Todas)"] + locs,
            key="form_localidad_sel",
        ) if locs else "(Todas)"

        inst_geo = inst_mun
        if loc_sel and loc_sel != "(Todas)":
            inst_geo = inst_geo[inst_geo["localidad"] == loc_sel]

        inst_map = {r["nombre"]: int(r["id"]) for _, r in inst_geo.iterrows()}
        inst_sel = g4.selectbox(
            "Institución",
            options=list(inst_map.keys()) if inst_map else [],
            key="form_institucion",
        )
        institucion_id = inst_map.get(inst_sel)

        if institucion_id:
            row_inst = instituciones[instituciones["id"] == institucion_id].iloc[0]
            localidad_val = row_inst.get("localidad")
            municipio_val = row_inst.get("municipio")
            departamento_val = row_inst.get("departamento")

    c3, c4 = st.columns([1, 1])
    fecha = c3.date_input("Fecha de la atención", value=date.today(), key="form_fecha")
    actividad = c4.selectbox("Actividad / plantilla", ACTIVIDADES_PLANTILLAS, key="form_actividad")

    st.markdown("#### Datos del paciente")
    p1, p2 = st.columns([1, 1])
    pac_doc = p1.text_input("Documento del paciente (cédula)", key="pac_doc")
    if p2.button("Buscar paciente por documento", key="btn_buscar_paciente"):
        try:
            pac = DATA.get_paciente_por_documento(pac_doc)
            if pac:
                st.session_state["pac_id_actual"] = pac.get("id")
                st.session_state["pac_nombre"] = pac.get("nombre")
                st.session_state["pac_fecha_nac"] = pac.get("fecha_nacimiento")
                st.session_state["pac_sexo"] = pac.get("sexo")
                st.session_state["pac_telefono"] = pac.get("telefono")
                st.session_state["pac_email"] = pac.get("email")
                st.session_state["pac_direccion"] = pac.get("direccion")
                st.session_state["pac_localidad"] = pac.get("localidad")
                st.session_state["pac_municipio"] = pac.get("municipio")
                st.session_state["pac_departamento"] = pac.get("departamento")
                success_toast("Paciente encontrado. Datos cargados en el formulario.")
            else:
                st.session_state["pac_id_actual"] = None
                warn_toast("No se encontró paciente. Diligencia los datos y se creará automáticamente.")
        except Exception as e:
            error_toast(f"Error buscando paciente: {e}")

    p3, p4 = st.columns([1.5, 1])
    pac_nombre = p3.text_input(
        "Nombre completo del paciente",
        value=st.session_state.get("pac_nombre") or "",
        key="pac_nombre_input",
    )
    pac_sexo_opciones = ["(No especifica)", "F", "M", "Otro"]
    sexo_pre = st.session_state.get("pac_sexo") or "(No especifica)"
    if sexo_pre not in pac_sexo_opciones:
        sexo_pre = "(No especifica)"
    pac_sexo = p4.selectbox(
        "Sexo (opcional)",
        options=pac_sexo_opciones,
        index=pac_sexo_opciones.index(sexo_pre),
        key="pac_sexo_sel",
    )

    p5, p6 = st.columns([1, 1])
    pac_fecha_nac = p5.text_input(
        "Fecha de nacimiento (AAAA-MM-DD, opcional)",
        value=st.session_state.get("pac_fecha_nac") or "",
        key="pac_fecha_nac_input",
    )
    pac_telefono = p6.text_input(
        "Teléfono (opcional)",
        value=st.session_state.get("pac_telefono") or "",
        key="pac_telefono_input",
    )

    p7, p8 = st.columns([1, 1])
    pac_email = p7.text_input(
        "Email (opcional)",
        value=st.session_state.get("pac_email") or "",
        key="pac_email_input",
    )
    pac_direccion = p8.text_input(
        "Dirección (opcional)",
        value=st.session_state.get("pac_direccion") or "",
        key="pac_direccion_input",
    )

    p9, p10, p11 = st.columns([1, 1, 1])
    pac_loc = p9.text_input(
        "Localidad paciente (opcional)",
        value=st.session_state.get("pac_localidad") or "",
        key="pac_localidad_input",
    )
    pac_mun = p10.text_input(
        "Municipio paciente (opcional)",
        value=st.session_state.get("pac_municipio") or "",
        key="pac_municipio_input",
    )
    pac_dep = p11.text_input(
        "Departamento paciente (opcional)",
        value=st.session_state.get("pac_departamento") or "",
        key="pac_departamento_input",
    )

    c9, c10 = st.columns([1, 1])
    atendido_flag = c9.radio("¿Atendido?", ["No", "Sí"], index=1, horizontal=True, key="form_atendido")
    registrado_panacea = c10.checkbox("Ya registrado en Panacea", key="form_reg_panacea")

    c11, c12 = st.columns([1, 1])
    tipo_contacto = c11.selectbox(
        "Tipo de contacto",
        options=["(No especifica)"] + TIPOS_CONTACTO,
        key="form_tipo_contacto",
    )
    duracion_minutos = c12.number_input(
        "Duración de la atención (minutos, opcional)",
        min_value=0,
        max_value=480,
        step=5,
        key="form_duracion_minutos",
    )
    duracion_val = int(duracion_minutos) if duracion_minutos > 0 else None
    tipo_contacto_val = None if tipo_contacto == "(No especifica)" else tipo_contacto

    observaciones = st.text_area("Observaciones", key="form_observaciones")

    btn_guardar = st.button(
        "Guardar atención",
        type="primary",
        use_container_width=True,
        key="btn_guardar_atencion",
        disabled=not all([programa_id, convenio_id, profesor_id, institucion_id]),
    )

    if btn_guardar:
        if not pac_doc or not pac_nombre:
            warn_toast("Documento y nombre del paciente son obligatorios.")
            return
        try:
            sexo_val = None if pac_sexo == "(No especifica)" else pac_sexo
            pac_id = DATA.upsert_paciente(
                numero_documento=pac_doc,
                nombre=pac_nombre,
                fecha_nacimiento=pac_fecha_nac or None,
                sexo=sexo_val,
                telefono=pac_telefono or None,
                email=pac_email or None,
                direccion=pac_direccion or None,
                localidad=pac_loc or None,
                municipio=pac_mun or None,
                departamento=pac_dep or None,
            )
            DATA.insert_registro(
                fecha=fecha,
                programa_id=int(programa_id),
                convenio_id=int(convenio_id),
                institucion_id=int(institucion_id),
                profesor_id=int(profesor_id),
                paciente_id=pac_id,
                localidad=localidad_val,
                municipio=municipio_val,
                departamento=departamento_val,
                numero_paciente=pac_doc,
                nombre_paciente=pac_nombre,
                actividad=actividad,
                atendido=True if atendido_flag == "Sí" else False,
                registrado_panacea=bool(registrado_panacea),
                duracion_minutos=duracion_val,
                tipo_contacto=tipo_contacto_val,
                observaciones=observaciones,
                creado_por=auth_email,
            )
            success_toast("Atención registrada correctamente.")
            st.rerun()
        except Exception as e:
            error_toast(f"Error al guardar la atención: {e}")

    with st.expander("Carga masiva de atenciones / pacientes"):
        st.markdown(
            """
            **Formato esperado del archivo (Excel o CSV):**  
            Columnas mínimas (nombres de encabezado):
            - `fecha` (YYYY-MM-DD)  
            - `programa`  
            - `convenio`  
            - `institucion` (nombre exacto de la institución)  
            - `profesional` (nombre exacto del profesional)  
            - `numero_paciente`  
            - `nombre_paciente`  
            - `actividad` (una de las plantillas definidas)  
            - `atendido` (SI/NO)  
            - `registrado_panacea` (SI/NO)

            Columnas **opcionales** (si las incluyes, se aprovechan):
            - `tipo_contacto` (Presencial / Virtual / Telefónico / Otro)
            - `duracion_minutos` (entero, minutos)
            """
        )
        file = st.file_uploader(
            "Archivo de atenciones (Excel o CSV)",
            type=["xlsx", "xls", "csv"],
            key="up_atenciones",
        )
        if file is not None:
            if st.button("Procesar archivo", key="btn_procesar_atenciones"):
                try:
                    if file.name.lower().endswith(".csv"):
                        df_up = pd.read_csv(file, sep=None, engine="python")
                    else:
                        df_up = pd.read_excel(file)
                    required_cols = [
                        "fecha",
                        "programa",
                        "convenio",
                        "institucion",
                        "profesional",
                        "numero_paciente",
                        "nombre_paciente",
                        "actividad",
                        "atendido",
                        "registrado_panacea",
                    ]
                    missing = [c for c in required_cols if c not in df_up.columns]
                    if missing:
                        error_toast(f"Faltan columnas obligatorias: {', '.join(missing)}")
                    else:
                        progs = DATA.list_programas()
                        prog_map2 = {r["nombre"]: int(r["id"]) for _, r in progs.iterrows()} if not progs.empty else {}
                        convs = DATA.list_convenios()
                        conv_map2 = {
                            (r["nombre"], int(r["programa_id"])): int(r["id"])
                            for _, r in convs.iterrows()
                        } if not convs.empty else {}
                        insts = DATA.list_instituciones()
                        inst_by_name = {
                            r["nombre"]: {
                                "id": int(r["id"]),
                                "localidad": r.get("localidad"),
                                "municipio": r.get("municipio"),
                                "departamento": r.get("departamento"),
                            }
                            for _, r in insts.iterrows()
                        } if not insts.empty else {}
                        profs = DATA.list_profesores()
                        prof_map2 = {r["nombre"]: int(r["id"]) for _, r in profs.iterrows()} if not profs.empty else {}

                        ok = 0
                        skipped = 0

                        def parse_bool(v: Any) -> bool:
                            if isinstance(v, str):
                                v = v.strip().lower()
                                return v in ["si", "sí", "yes", "y", "1", "true"]
                            if isinstance(v, (int, float)):
                                return v == 1
                            return False

                        for _, row in df_up.iterrows():
                            try:
                                fecha_val = pd.to_datetime(row["fecha"]).date()
                                prog_name = str(row["programa"])
                                conv_name = str(row["convenio"])
                                inst_name = str(row["institucion"])
                                prof_name = str(row["profesional"])

                                if prog_name not in prog_map2:
                                    skipped += 1
                                    continue
                                programa_id2 = prog_map2[prog_name]

                                key_conv = (conv_name, programa_id2)
                                if key_conv not in conv_map2:
                                    skipped += 1
                                    continue
                                convenio_id2 = conv_map2[key_conv]

                                inst_info = inst_by_name.get(inst_name)
                                if not inst_info:
                                    skipped += 1
                                    continue
                                institucion_id2 = inst_info["id"]

                                if prof_name not in prof_map2:
                                    skipped += 1
                                    continue
                                profesor_id2 = prof_map2[prof_name]

                                actividad_val = str(row["actividad"]).strip()
                                if actividad_val not in ACTIVIDADES_PLANTILLAS:
                                    skipped += 1
                                    continue

                                atend_b = parse_bool(row["atendido"])
                                reg_p = parse_bool(row["registrado_panacea"])

                                tipo_contacto_val2 = None
                                if "tipo_contacto" in df_up.columns and pd.notna(row.get("tipo_contacto")):
                                    tc = str(row["tipo_contacto"]).strip()
                                    if tc in TIPOS_CONTACTO:
                                        tipo_contacto_val2 = tc

                                dur_val2 = None
                                if "duracion_minutos" in df_up.columns and pd.notna(row.get("duracion_minutos")):
                                    try:
                                        dv = int(row["duracion_minutos"])
                                        if dv > 0:
                                            dur_val2 = dv
                                    except Exception:
                                        pass

                                pac_doc_row = str(row["numero_paciente"])
                                pac_nom_row = str(row["nombre_paciente"])
                                sexo_val = None
                                fecha_nac_val = None
                                telefono_val = None
                                email_val = None
                                dir_val = None
                                pac_loc_val = None
                                pac_mun_val = None
                                pac_dep_val = None

                                try:
                                    pac_id = DATA.upsert_paciente(
                                        numero_documento=pac_doc_row,
                                        nombre=pac_nom_row,
                                        fecha_nacimiento=fecha_nac_val,
                                        sexo=sexo_val,
                                        telefono=telefono_val,
                                        email=email_val,
                                        direccion=dir_val,
                                        localidad=pac_loc_val,
                                        municipio=pac_mun_val,
                                        departamento=pac_dep_val,
                                    )
                                except Exception:
                                    pac_id = None

                                DATA.insert_registro(
                                    fecha=fecha_val,
                                    programa_id=programa_id2,
                                    convenio_id=convenio_id2,
                                    institucion_id=institucion_id2,
                                    profesor_id=profesor_id2,
                                    paciente_id=pac_id,
                                    localidad=inst_info["localidad"],
                                    municipio=inst_info["municipio"],
                                    departamento=inst_info["departamento"],
                                    numero_paciente=pac_doc_row,
                                    nombre_paciente=pac_nom_row,
                                    actividad=actividad_val,
                                    atendido=atend_b,
                                    registrado_panacea=reg_p,
                                    duracion_minutos=dur_val2,
                                    tipo_contacto=tipo_contacto_val2,
                                    observaciones=None,
                                    creado_por=auth_email,
                                )
                                ok += 1
                            except Exception:
                                skipped += 1
                        success_toast(f"Carga masiva finalizada. OK: {ok}, omitidas: {skipped}")
                        st.rerun()
                except Exception as e:
                    error_toast(f"Error procesando archivo: {e}")


def ui_registros():
    st.subheader("Listado de atenciones")

    df = DATA.list_registros(st.session_state.filters)
    if df.empty:
        st.info("No hay registros con los filtros actuales.")
        return

    if "tasa_atencion" in df.columns:
        df["tasa_atencion_%"] = (df["tasa_atencion"] * 100).round(1)

    show_cols = [
        "id",
        "fecha",
        "programa",
        "convenio",
        "institucion",
        "profesor",
        "actividad",
        "numero_paciente",
        "nombre_paciente",
        "tipo_contacto",
        "duracion_minutos",
        "atendido",
        "registrado_panacea",
        "pacientes_programados",
        "pacientes_atendidos",
        "no_asistieron",
        "tasa_atencion_%",
        "observaciones",
        "creado_por",
        "creado_en",
        "actualizado_en",
    ]
    cols_to_show = [c for c in show_cols if c in df.columns]
    st.dataframe(df[cols_to_show], use_container_width=True, hide_index=True)

    st.markdown("---")
    c1, c2, _ = st.columns([1, 1, 3])
    id_sel = c1.number_input("ID de atención", min_value=1, step=1, key="reg_id_sel")
    if c2.button("Eliminar atención", use_container_width=True, key="btn_eliminar_reg"):
        try:
            DATA.delete_registro(int(id_sel))
            success_toast("Atención eliminada.")
            st.rerun()
        except Exception as e:
            error_toast(f"No se pudo eliminar: {e}")

    with st.expander("Editar atención seleccionada"):
        df_ids = df["id"].tolist()
        row_sel = None
        if int(id_sel) in df_ids:
            row_sel = df.loc[df["id"] == int(id_sel)].iloc[0]
        else:
            st.info("Selecciona un ID existente de la tabla superior.")

        if row_sel is not None:
            c4, c5 = st.columns(2)
            upd_numero = c4.text_input(
                "Número de paciente",
                value=row_sel.get("numero_paciente", "") or "",
                key="upd_numero_paciente",
            )
            upd_nombre = c5.text_input(
                "Nombre de paciente",
                value=row_sel.get("nombre_paciente", "") or "",
                key="upd_nombre_paciente",
            )
            try:
                idx_act = ACTIVIDADES_PLANTILLAS.index(row_sel.get("actividad"))
            except Exception:
                idx_act = 0
            upd_actividad = st.selectbox(
                "Actividad / plantilla",
                ACTIVIDADES_PLANTILLAS,
                index=idx_act,
                key="upd_actividad",
            )

            c6, c7 = st.columns(2)
            upd_atendido_flag = c6.radio(
                "¿Atendido?",
                ["No", "Sí"],
                index=1 if row_sel.get("atendido") in [1, True] else 0,
                horizontal=True,
                key="upd_atendido",
            )
            upd_reg_panacea = c7.checkbox(
                "Ya registrado en Panacea",
                value=bool(row_sel.get("registrado_panacea")),
                key="upd_reg_panacea",
            )

            c8, c9 = st.columns(2)
            upd_tipo_contacto = c8.selectbox(
                "Tipo de contacto",
                options=["(No especifica)"] + TIPOS_CONTACTO,
                index=(
                    (["(No especifica)"] + TIPOS_CONTACTO).index(row_sel.get("tipo_contacto"))
                    if row_sel.get("tipo_contacto") in TIPOS_CONTACTO
                    else 0
                ),
                key="upd_tipo_contacto",
            )
            upd_duracion = c9.number_input(
                "Duración (minutos)",
                min_value=0,
                max_value=480,
                step=5,
                value=int(row_sel.get("duracion_minutos") or 0),
                key="upd_duracion_minutos",
            )

            upd_obs = st.text_area(
                "Observaciones",
                value=row_sel.get("observaciones", "") or "",
                key="upd_observaciones",
            )

            if st.button("Guardar cambios", type="primary", key="btn_guardar_cambios"):
                atendido_bool = upd_atendido_flag == "Sí"
                tc_val = None if upd_tipo_contacto == "(No especifica)" else upd_tipo_contacto
                dur_val = int(upd_duracion) if upd_duracion > 0 else None
                updates = {
                    "numero_paciente": upd_numero or None,
                    "nombre_paciente": upd_nombre or None,
                    "actividad": upd_actividad,
                    "atendido": 1 if atendido_bool else 0,
                    "registrado_panacea": 1 if upd_reg_panacea else 0,
                    "pacientes_programados": 1,
                    "pacientes_atendidos": 1 if atendido_bool else 0,
                    "tipo_contacto": tc_val,
                    "duracion_minutos": dur_val,
                    "observaciones": upd_obs or None,
                }
                try:
                    DATA.update_registro(int(id_sel), updates)
                    success_toast("Atención actualizada.")
                    st.rerun()
                except Exception as e:
                    error_toast(f"No se pudo actualizar: {e}")


def ui_dashboard():
    st.subheader("Dashboard de gestión")

    df = DATA.list_registros(st.session_state.filters)
    if df.empty:
        st.info("No hay datos para graficar con los filtros actuales.")
        return

    df["fecha"] = pd.to_datetime(df["fecha"])

    total_prog = int(df["pacientes_programados"].sum())
    total_att = int(df["pacientes_atendidos"].sum())
    total_no = int(df["no_asistieron"].sum())
    tasa = (total_att / total_prog * 100) if total_prog else 0.0

    total_minutos = int(df["duracion_minutos"].fillna(0).sum()) if "duracion_minutos" in df.columns else 0
    n_con_duracion = int(df["duracion_minutos"].notna().sum()) if "duracion_minutos" in df.columns else 0
    dur_promedio = (total_minutos / n_con_duracion) if n_con_duracion else 0.0
    horas_totales = total_minutos / 60 if total_minutos > 0 else 0.0
    productividad_ph = (total_att / horas_totales) if horas_totales > 0 else 0.0

    total_reg_panacea = int(df["registrado_panacea"].fillna(0).sum()) if "registrado_panacea" in df.columns else 0
    brecha_panacea = total_att - total_reg_panacea

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Pacientes programados", f"{total_prog:,}".replace(",", "."))
    k2.metric("Pacientes atendidos", f"{total_att:,}".replace(",", "."))
    k3.metric("No asistieron", f"{total_no:,}".replace(",", "."))
    k4.metric("Tasa de atención", f"{tasa:.1f}%")

    k5, k6, k7, k8 = st.columns(4)
    k5.metric("Minutos de atención", f"{total_minutos:,}".replace(",", "."))
    k6.metric("Duración promedio (min)", f"{dur_promedio:.1f}")
    k7.metric("Atenciones por hora efectiva", f"{productividad_ph:.2f}")
    k8.metric("Cargadas en Panacea / brecha", f"{total_reg_panacea} / {brecha_panacea}")

    tdf = (
        df.groupby(pd.Grouper(key="fecha", freq="W"))[["pacientes_programados", "pacientes_atendidos"]]
        .sum()
        .reset_index()
    )
    fig1 = px.line(
        tdf,
        x="fecha",
        y=["pacientes_programados", "pacientes_atendidos"],
        markers=True,
        title="Tendencia semanal de pacientes programados vs atendidos",
    )
    st.plotly_chart(fig1, use_container_width=True)

    if "profesor" not in df.columns and "profesores" in df.columns:
        df["profesor"] = df["profesores"].apply(lambda x: x.get("nombre") if isinstance(x, dict) else None)
    rank_prof = (
        df.groupby("profesor", dropna=True)["pacientes_atendidos"]
        .sum()
        .sort_values(ascending=False)
        .head(15)
        .reset_index()
    )
    fig2 = px.bar(
        rank_prof,
        x="profesor",
        y="pacientes_atendidos",
        title="Top profesionales por pacientes atendidos",
    )
    fig2.update_layout(xaxis_tickangle=-40)
    st.plotly_chart(fig2, use_container_width=True)

    if "registrado_panacea" in df.columns:
        pan_prof = (
            df.groupby("profesor", dropna=True)
            .agg(
                pacientes_atendidos=("pacientes_atendidos", "sum"),
                cargadas_panacea=("registrado_panacea", "sum"),
            )
            .reset_index()
        )
        pan_prof["brecha"] = pan_prof["pacientes_atendidos"] - pan_prof["cargadas_panacea"]
        pan_prof["cumplimiento"] = np.where(
            pan_prof["pacientes_atendidos"] > 0,
            pan_prof["cargadas_panacea"] / pan_prof["pacientes_atendidos"],
            np.nan,
        )
        pan_prof = pan_prof.sort_values("brecha", ascending=False).head(15)
        fig2b = px.bar(
            pan_prof,
            x="profesor",
            y=["pacientes_atendidos", "cargadas_panacea"],
            barmode="group",
            title="Atenciones vs cargadas en Panacea por profesional",
        )
        fig2b.update_layout(xaxis_tickangle=-40)
        st.plotly_chart(fig2b, use_container_width=True)

    act_sum = (
        df.groupby("actividad")[["pacientes_programados", "pacientes_atendidos"]]
        .sum()
        .reset_index()
    )
    fig3 = px.bar(
        act_sum,
        x="actividad",
        y=["pacientes_programados", "pacientes_atendidos"],
        barmode="group",
        title="Distribución por actividad / plantilla",
    )
    fig3.update_layout(xaxis_tickangle=-30)
    st.plotly_chart(fig3, use_container_width=True)

    if "institucion" not in df.columns and "instituciones" in df.columns:
        df["institucion"] = df["instituciones"].apply(lambda x: x.get("nombre") if isinstance(x, dict) else None)
    inst_sum = (
        df.groupby("institucion", dropna=True)[["pacientes_programados", "pacientes_atendidos"]]
        .sum()
        .sort_values(by="pacientes_atendidos", ascending=False)
        .head(15)
        .reset_index()
    )
    fig4 = px.bar(
        inst_sum,
        x="institucion",
        y=["pacientes_programados", "pacientes_atendidos"],
        barmode="group",
        title="Instituciones con mayor actividad",
    )
    fig4.update_layout(xaxis_tickangle=-40)
    st.plotly_chart(fig4, use_container_width=True)


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

    if "profesor" not in df.columns and "profesores" in df.columns:
        df["profesor"] = df["profesores"].apply(lambda x: x.get("nombre") if isinstance(x, dict) else None)

    agg_prof = (
        df.groupby("profesor", dropna=True)
        .agg(
            pacientes_programados=("pacientes_programados", "sum"),
            pacientes_atendidos=("pacientes_atendidos", "sum"),
            cargadas_panacea=("registrado_panacea", "sum"),
            minutos=("duracion_minutos", "sum"),
        )
        .reset_index()
    )
    agg_prof["tasa_atencion"] = np.where(
        agg_prof["pacientes_programados"] > 0,
        agg_prof["pacientes_atendidos"] / agg_prof["pacientes_programados"],
        np.nan,
    )
    agg_prof["brecha_panacea"] = agg_prof["pacientes_atendidos"] - agg_prof["cargadas_panacea"]

    por_inst = (
        df.groupby("institucion", dropna=True)[["pacientes_programados", "pacientes_atendidos"]]
        .sum()
        .reset_index()
    )
    por_geo = (
        df.groupby(["departamento", "municipio"], dropna=True)[["pacientes_programados", "pacientes_atendidos"]]
        .sum()
        .reset_index()
    )
    por_act = (
        df.groupby("actividad")[["pacientes_programados", "pacientes_atendidos"]]
        .sum()
        .reset_index()
    )

    xls = to_excel_bytes(
        {
            "Detalle": df,
            "Por_profesional": agg_prof,
            "Por_institucion": por_inst,
            "Por_geo": por_geo,
            "Por_actividad": por_act,
        }
    )
    st.download_button(
        "Descargar Excel (.xlsx)",
        data=xls,
        file_name=f"productividad_profesionales_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key="btn_descargar_xlsx",
    )

    st.download_button(
        "Descargar detalle (.csv)",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=f"productividad_profesionales_detalle_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
        use_container_width=True,
        key="btn_descargar_csv",
    )


def ui_configuracion():
    st.subheader("Configuración de catálogos")

    tabs = st.tabs(["Programas", "Convenios", "Instituciones", "Profesionales", "Pacientes"])

    # Programas
    with tabs[0]:
        c1, c2 = st.columns([2, 1])
        p_nombre = c1.text_input("Nombre del programa", key="cfg_prog_nombre")
        if c2.button("Agregar programa", use_container_width=True, key="btn_add_programa"):
            if not p_nombre.strip():
                warn_toast("Escribe un nombre de programa.")
            else:
                DATA.upsert_programa(p_nombre.strip())
                success_toast("Programa agregado/actualizado.")
                st.rerun()
        st.markdown("**Programas activos**")
        st.dataframe(DATA.list_programas(), use_container_width=True, hide_index=True)

    # Convenios
    with tabs[1]:
        programas = DATA.list_programas()
        prog_map = {r["nombre"]: int(r["id"]) for _, r in programas.iterrows()} if not programas.empty else {}
        c1, c2, c3 = st.columns([2, 2, 1])
        cv_prog = c1.selectbox(
            "Programa",
            options=list(prog_map.keys()) if prog_map else [],
            key="cfg_conv_prog",
        )
        cv_nombre = c2.text_input("Nombre del convenio", key="cfg_conv_nombre")
        if c3.button("Agregar convenio", use_container_width=True, key="btn_add_convenio"):
            if not (cv_prog and cv_nombre.strip()):
                warn_toast("Selecciona programa y escribe el nombre del convenio.")
            else:
                DATA.upsert_convenio(cv_nombre.strip(), prog_map[cv_prog])
                success_toast("Convenio agregado/actualizado.")
                st.rerun()
        st.markdown("**Convenios activos**")
        st.dataframe(DATA.list_convenios(), use_container_width=True, hide_index=True)

      # Instituciones
    with tabs[2]:
        # --- Creación / edición manual ---
        c1, c2, c3, c4, c5 = st.columns([2, 1.2, 1.2, 1.2, 1])
        i_nombre = c1.text_input("Nombre institución", key="cfg_inst_nombre")
        i_localidad = c2.text_input("Localidad", key="cfg_inst_localidad")
        i_municipio = c3.text_input("Municipio", key="cfg_inst_municipio")
        i_departamento = c4.text_input("Departamento", key="cfg_inst_departamento")

        if c5.button("Agregar institución", use_container_width=True, key="btn_add_inst"):
            if not i_nombre.strip():
                warn_toast("Escribe el nombre de la institución.")
            else:
                DATA.upsert_institucion(
                    i_nombre.strip(),
                    i_localidad.strip() if i_localidad else None,
                    i_municipio.strip() if i_municipio else None,
                    i_departamento.strip() if i_departamento else None,
                )
                success_toast("Institución agregada/actualizada.")
                st.rerun()

        st.markdown("**Instituciones activas**")
        st.dataframe(
            DATA.list_instituciones(),
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("---")
        # --- Carga masiva de instituciones ---
        st.markdown("### Carga masiva de instituciones")
        st.markdown(
            '''
            **Formato esperado (Excel o CSV):**  

            Columnas mínimas:
            - `nombre`

            Columnas opcionales:
            - `localidad`
            - `municipio`
            - `departamento`

            > La combinación (`nombre`, `municipio`, `departamento`) se usa para evitar duplicados.
            '''
        )

        file_inst = st.file_uploader(
            "Archivo de instituciones (Excel o CSV)",
            type=["xlsx", "xls", "csv"],
            key="up_instituciones",
        )

        if file_inst is not None:
            if st.button("Procesar instituciones", key="btn_procesar_instituciones"):
                try:
                    # Leer archivo
                    if file_inst.name.lower().endswith(".csv"):
                        df_inst = pd.read_csv(file_inst, sep=None, engine="python")
                    else:
                        df_inst = pd.read_excel(file_inst)

                    if "nombre" not in df_inst.columns:
                        error_toast("El archivo debe contener al menos la columna 'nombre'.")
                    else:
                        ok = 0
                        for _, row in df_inst.iterrows():
                            nombre = str(row["nombre"]).strip()
                            if not nombre:
                                continue

                            loc = (
                                str(row["localidad"]).strip()
                                if "localidad" in df_inst.columns and pd.notna(row["localidad"])
                                else None
                            )
                            mun = (
                                str(row["municipio"]).strip()
                                if "municipio" in df_inst.columns and pd.notna(row["municipio"])
                                else None
                            )
                            dep = (
                                str(row["departamento"]).strip()
                                if "departamento" in df_inst.columns and pd.notna(row["departamento"])
                                else None
                            )

                            DATA.upsert_institucion(nombre, loc, mun, dep)
                            ok += 1

                        success_toast(f"Se procesaron {ok} instituciones.")
                        st.rerun()
                except Exception as e:
                    error_toast(f"Error procesando instituciones: {e}")

    # Profesionales
    with tabs[3]:
        programas = DATA.list_programas()
        prog_map = {r["nombre"]: int(r["id"]) for _, r in programas.iterrows()} if not programas.empty else {}
        convenios = DATA.list_convenios()
        conv_map = {r["nombre"]: int(r["id"]) for _, r in convenios.iterrows()} if not convenios.empty else {}

        c1, c2, c3, c4, c5 = st.columns([2, 1.2, 1.4, 1.4, 1.2])
        f_nombre = c1.text_input("Nombre profesional", key="cfg_prof_nombre")
        f_doc = c2.text_input("Documento (opcional)", key="cfg_prof_doc")
        f_email = c3.text_input("Email (opcional)", key="cfg_prof_email")
        f_prog = c4.selectbox(
            "Programa",
            options=list(prog_map.keys()) if prog_map else [],
            key="cfg_prof_prog",
        )
        f_conv = c5.selectbox(
            "Convenio",
            options=list(conv_map.keys()) if conv_map else [],
            key="cfg_prof_conv",
        )
        if st.button("Agregar profesional", use_container_width=True, key="btn_add_prof"):
            if not f_nombre.strip():
                warn_toast("Escribe el nombre del profesional.")
            else:
                DATA.upsert_profesor(
                    f_nombre.strip(),
                    f_doc.strip() if f_doc else None,
                    f_email.strip() if f_email else None,
                    prog_map.get(f_prog),
                    conv_map.get(f_conv),
                )
                success_toast("Profesional agregado/actualizado.")
                st.rerun()

        st.markdown("**Profesionales activos**")
        st.dataframe(DATA.list_profesores(), use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("### Carga masiva de profesionales")
        st.markdown(
            """
            **Formato esperado (Excel o CSV):**  
            Columnas sugeridas:
            - `nombre` (obligatorio)  
            - `documento` (opcional)  
            - `email` (opcional)  
            - `programa` (opcional pero recomendado) -> Nombre EXACTO  
            - `convenio` (opcional)                  -> Nombre EXACTO
            """
        )
        file_prof = st.file_uploader(
            "Archivo de profesionales",
            type=["xlsx", "xls", "csv"],
            key="up_profesionales",
        )
        if file_prof is not None:
            if st.button("Procesar profesionales", key="btn_procesar_profesionales"):
                try:
                    if file_prof.name.lower().endswith(".csv"):
                        df_prof = pd.read_csv(file_prof, sep=None, engine="python")
                    else:
                        df_prof = pd.read_excel(file_prof)
                    if "nombre" not in df_prof.columns:
                        error_toast("El archivo debe contener al menos la columna 'nombre'.")
                    else:
                        progs2 = DATA.list_programas()
                        prog_map2 = {r["nombre"]: int(r["id"]) for _, r in progs2.iterrows()} if not progs2.empty else {}
                        convs2 = DATA.list_convenios()
                        conv_map2 = {r["nombre"]: int(r["id"]) for _, r in convs2.iterrows()} if not convs2.empty else {}

                        ok = 0
                        for _, row in df_prof.iterrows():
                            nombre = str(row["nombre"]).strip()
                            if not nombre:
                                continue
                            documento = (
                                str(row["documento"]).strip()
                                if "documento" in df_prof.columns and pd.notna(row["documento"])
                                else None
                            )
                            email = (
                                str(row["email"]).strip()
                                if "email" in df_prof.columns and pd.notna(row["email"])
                                else None
                            )
                            prog_name = (
                                str(row["programa"]).strip()
                                if "programa" in df_prof.columns and pd.notna(row["programa"])
                                else None
                            )
                            conv_name = (
                                str(row["convenio"]).strip()
                                if "convenio" in df_prof.columns and pd.notna(row["convenio"])
                                else None
                            )

                            prog_id = prog_map2.get(prog_name) if prog_name else None
                            conv_id = conv_map2.get(conv_name) if conv_name else None

                            DATA.upsert_profesor(nombre, documento, email, prog_id, conv_id)
                            ok += 1
                        success_toast(f"Se procesaron {ok} profesionales.")
                        st.rerun()
                except Exception as e:
                    error_toast(f"Error procesando profesionales: {e}")

    # Pacientes
    with tabs[4]:
        st.markdown("### Gestión de pacientes")
        c1, c2 = st.columns([1.2, 2])
        cfg_doc = c1.text_input("Documento (cédula)", key="cfg_pac_doc")
        cfg_nombre = c2.text_input("Nombre completo", key="cfg_pac_nombre")

        c3, c4, c5 = st.columns([1, 1, 1])
        cfg_fecha_nac = c3.text_input("Fecha de nacimiento (AAAA-MM-DD, opcional)", key="cfg_pac_fecha_nac")
        sexo_opts = ["(No especifica)", "F", "M", "Otro"]
        cfg_sexo = c4.selectbox("Sexo (opcional)", sexo_opts, key="cfg_pac_sexo")
        cfg_tel = c5.text_input("Teléfono (opcional)", key="cfg_pac_tel")

        c6, c7 = st.columns([1, 1])
        cfg_email = c6.text_input("Email (opcional)", key="cfg_pac_email")
        cfg_dir = c7.text_input("Dirección (opcional)", key="cfg_pac_dir")

        c8, c9, c10 = st.columns([1, 1, 1])
        cfg_loc = c8.text_input("Localidad (opcional)", key="cfg_pac_loc")
        cfg_mun = c9.text_input("Municipio (opcional)", key="cfg_pac_mun")
        cfg_dep = c10.text_input("Departamento (opcional)", key="cfg_pac_dep")

        if st.button("Guardar / actualizar paciente", key="btn_guardar_paciente_cfg"):
            if not cfg_doc.strip() or not cfg_nombre.strip():
                warn_toast("Documento y nombre del paciente son obligatorios.")
            else:
                sexo_val = None if cfg_sexo == "(No especifica)" else cfg_sexo
                try:
                    DATA.upsert_paciente(
                        numero_documento=cfg_doc.strip(),
                        nombre=cfg_nombre.strip(),
                        fecha_nacimiento=cfg_fecha_nac or None,
                        sexo=sexo_val,
                        telefono=cfg_tel or None,
                        email=cfg_email or None,
                        direccion=cfg_dir or None,
                        localidad=cfg_loc or None,
                        municipio=cfg_mun or None,
                        departamento=cfg_dep or None,
                    )
                    success_toast("Paciente guardado / actualizado.")
                    st.rerun()
                except Exception as e:
                    error_toast(f"No se pudo guardar paciente: {e}")

        st.markdown("**Pacientes activos**")
        st.dataframe(DATA.list_pacientes(), use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("### Carga masiva de pacientes")
        st.markdown(
            """
            **Formato esperado (Excel o CSV):**  
            Columnas mínimas:
            - `documento`
            - `nombre`

            Columnas opcionales:
            - `fecha_nacimiento` (AAAA-MM-DD)
            - `sexo` (F / M / Otro)
            - `telefono`
            - `email`
            - `direccion`
            - `localidad`
            - `municipio`
            - `departamento`
            """
        )
        file_pac = st.file_uploader(
            "Archivo de pacientes (Excel o CSV)",
            type=["xlsx", "xls", "csv"],
            key="up_pacientes",
        )
        if file_pac is not None:
            if st.button("Procesar pacientes", key="btn_procesar_pacientes"):
                try:
                    if file_pac.name.lower().endswith(".csv"):
                        df_pac = pd.read_csv(file_pac, sep=None, engine="python")
                    else:
                        df_pac = pd.read_excel(file_pac)
                    if "documento" not in df_pac.columns or "nombre" not in df_pac.columns:
                        error_toast("El archivo debe contener al menos las columnas 'documento' y 'nombre'.")
                    else:
                        ok = 0
                        for _, row in df_pac.iterrows():
                            doc = str(row["documento"]).strip()
                            nom = str(row["nombre"]).strip()
                            if not doc or not nom:
                                continue
                            DATA.upsert_paciente(
                                numero_documento=doc,
                                nombre=nom,
                                fecha_nacimiento=str(row["fecha_nacimiento"]) if "fecha_nacimiento" in df_pac.columns and pd.notna(row["fecha_nacimiento"]) else None,
                                sexo=str(row["sexo"]).strip() if "sexo" in df_pac.columns and pd.notna(row["sexo"]) else None,
                                telefono=str(row["telefono"]).strip() if "telefono" in df_pac.columns and pd.notna(row["telefono"]) else None,
                                email=str(row["email"]).strip() if "email" in df_pac.columns and pd.notna(row["email"]) else None,
                                direccion=str(row["direccion"]).strip() if "direccion" in df_pac.columns and pd.notna(row["direccion"]) else None,
                                localidad=str(row["localidad"]).strip() if "localidad" in df_pac.columns and pd.notna(row["localidad"]) else None,
                                municipio=str(row["municipio"]).strip() if "municipio" in df_pac.columns and pd.notna(row["municipio"]) else None,
                                departamento=str(row["departamento"]).strip() if "departamento" in df_pac.columns and pd.notna(row["departamento"]) else None,
                            )
                            ok += 1
                        success_toast(f"Se procesaron {ok} pacientes.")
                        st.rerun()
                except Exception as e:
                    error_toast(f"Error procesando pacientes: {e}")


def main():
    ensure_session_state()

    st.markdown(f"# {APP_ICON} {APP_TITLE}")
    if SUPABASE:
        st.caption(
            "Modo nube con Supabase. Si dejas SUPABASE_URL y SUPABASE_KEY vacíos, funciona en modo local (SQLite)."
        )
    else:
        st.caption("Modo local con SQLite. Para usar Supabase, define SUPABASE_URL y SUPABASE_KEY.")

    sidebar_filters()

    auth_email = None
    if SUPABASE:
        with st.sidebar:
            if not st.session_state.auth_user:
                render_login_supabase()
            else:
                auth_email = st.session_state.auth_user.get("email")
                st.success(f"Sesión: {auth_email}")
                render_logout_supabase()

    tabs = st.tabs(
        [
            "Registrar atenciones",
            "Listado",
            "Dashboard",
            "Reportes",
            "Configuración",
        ]
    )

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
