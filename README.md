# 📊 App Productividad de Profesores (Streamlit + Supabase/SQLite)

Herramienta para capturar y monitorear la productividad de profesores por programa/convenio/institución, con tablero de control (dashboard), trazabilidad y exportación de reportes.

## 🚀 Estructura
```
.
├── app_productividad_profesores.py
├── requirements.txt
├── .gitignore
├── .streamlit/
│   └── secrets.toml.example
└── supabase/
    ├── schema.sql
    └── policies.sql
```

## 🧩 Instalación local
```bash
pip install -r requirements.txt
streamlit run app_productividad_profesores.py
```
- Sin variables de entorno, la app usa **SQLite** (`productividad_profesores.db`).

## ☁️ Modo nube (Supabase)
1. Crea un proyecto en Supabase y en **SQL Editor** ejecuta:
   - `supabase/schema.sql`
   - `supabase/policies.sql` (opcional pero recomendado)
2. Crea usuarios en **Authentication** (admin/profesores).
3. Configura variables de entorno:
   - `SUPABASE_URL`
   - `SUPABASE_KEY` (usa la *anon/public key* en Streamlit Cloud).
4. Ejecuta la app.

### Secrets en Streamlit Cloud
En **Settings → Secrets**, pega algo como:
```toml
SUPABASE_URL = "https://TU-PROYECTO.supabase.co"
SUPABASE_KEY = "tu_public_anon_key"
```

## 📈 Qué incluye
- Catálogos: Programas, Convenios, Instituciones, Profesores
- Captura periódica con: fecha, geografía (localidad, municipio, departamento), programados, atendidos, observaciones
- KPIs, tendencia semanal, ranking de profesores, distribución por institución y por departamento
- Exportación Excel (múltiples hojas) y CSV
- Trazabilidad: `creado_por`, `creado_en`, `actualizado_en`

## 🧰 Notas
- En **modo Supabase** se habilita login (email/contraseña). En **modo SQLite** no se requiere.
- Puedes extender con metas, semáforos, carga masiva desde Excel y evidencias (Storage).

## 🐛 Soporte
Si algo falla al correr en Supabase (por ejemplo, nombres de columnas), verifica que ejecutaste `schema.sql` y que tuviste éxito con `policies.sql`.
