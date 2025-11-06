# Plantillas para carga masiva

## 1. plantilla_carga_masiva_profesionales.csv

Columnas:
- `nombre` (obligatorio)
- `documento` (opcional)
- `email` (opcional)
- `programa` (opcional, nombre EXACTO)
- `convenio` (opcional, nombre EXACTO)

## 2. plantilla_carga_masiva_pacientes.csv

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

## 3. plantilla_carga_masiva_atenciones.csv

Columnas mínimas:
- `fecha` (YYYY-MM-DD)
- `programa`
- `convenio`
- `institucion`
- `profesional`
- `numero_paciente`
- `nombre_paciente`
- `actividad` (una de las plantillas definidas)
- `atendido` (SI/NO)
- `registrado_panacea` (SI/NO)

Columnas opcionales:
- `tipo_contacto` (Presencial / Virtual / Telefónico / Otro)
- `duracion_minutos` (entero, minutos)
