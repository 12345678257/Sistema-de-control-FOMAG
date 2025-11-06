# Productividad de Profesionales

Aplicación en Streamlit para medir la productividad de profesionales en programas / convenios,
registrando atenciones a pacientes y generando indicadores y reportes de gestión.

## Funcionalidades principales

- Registro **individual** de atenciones:
  - Programa, Convenio, Profesional, Institución
  - Fecha
  - Actividad / plantilla:
    - VALORACION INICIAL POR PSICOLOGIA
    - CONTIGO PROFE EN AULA
    - PRIMEROS AUXILIOS PSICOLOGICO
    - APOYO TERAPEUTICO Y SEGUIMIENTO
  - Número y nombre del paciente
  - Búsqueda de paciente por documento (cédula) y autocompletado de datos
  - Ya registrado en Panacea (checkbox)
  - Tipo de contacto (Presencial / Virtual / Telefónico / Otro)
  - Duración de la atención (minutos)
  - Observaciones

- Registro **masivo** de atenciones desde Excel/CSV.
- Catálogos configurables: Programas, Convenios, Instituciones, Profesionales.
- Carga masiva de profesionales.
- Catálogo de pacientes con creación individual y carga masiva.
- Filtros claros (fechas, programa, convenio, profesional, actividad).
- Dashboard con:
  - Pacientes programados / atendidos / no asistieron
  - Tasa de atención
  - Minutos de atención, duración promedio, atenciones por hora efectiva
  - Brecha entre atenciones realizadas y registradas en Panacea
  - Tendencia semanal
  - Ranking de profesionales
  - Distribución por actividad e institución
- Descarga de reportes en Excel y CSV.

## Ejecutar en local (modo SQLite)

1. Crea y activa un entorno virtual (opcional pero recomendado).
2. Instala dependencias:

   ```bash
   pip install -r requirements.txt
   ```

3. Ejecuta la app:

   ```bash
   streamlit run app_productividad_profesores.py
   ```

La app creará un archivo `productividad_profesores.db` con el esquema SQLite necesario.

## Ejecutar en la nube (Supabase + Streamlit Cloud)

1. Crea un proyecto en Supabase y copia:
   - `SUPABASE_URL`
   - `SUPABASE_KEY` (public anon key)

2. En el panel SQL de Supabase, ejecuta el contenido de `supabase/schema.sql`.

3. Sube este proyecto a GitHub.

4. En Streamlit Cloud:
   - Crea una nueva app apuntando a este repositorio.
   - En **Settings → Secrets**, agrega:

     ```toml
     SUPABASE_URL = "https://TU-PROYECTO.supabase.co"
     SUPABASE_KEY = "tu_public_anon_key"
     ```

Si no configuras variables de Supabase, la app usará **SQLite local** automáticamente.
