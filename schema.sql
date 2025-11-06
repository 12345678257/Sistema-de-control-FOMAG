create table if not exists public.programas(
  id bigserial primary key,
  nombre text unique not null,
  activo boolean default true
);

create table if not exists public.convenios(
  id bigserial primary key,
  nombre text not null,
  programa_id bigint not null references public.programas(id),
  activo boolean default true,
  unique(nombre, programa_id)
);

create table if not exists public.instituciones(
  id bigserial primary key,
  nombre text not null,
  localidad text,
  municipio text,
  departamento text,
  activo boolean default true,
  unique(nombre, municipio, departamento)
);

create table if not exists public.profesores(
  id bigserial primary key,
  nombre text not null,
  documento text,
  email text,
  programa_id bigint references public.programas(id),
  convenio_id bigint references public.convenios(id),
  activo boolean default true
);

create table if not exists public.pacientes(
  id bigserial primary key,
  numero_documento text unique not null,
  nombre text not null,
  fecha_nacimiento date,
  sexo text,
  telefono text,
  email text,
  direccion text,
  localidad text,
  municipio text,
  departamento text,
  activo boolean default true
);

create table if not exists public.registros(
  id bigserial primary key,
  fecha date not null,
  programa_id bigint not null references public.programas(id),
  convenio_id bigint not null references public.convenios(id),
  institucion_id bigint not null references public.instituciones(id),
  profesor_id bigint not null references public.profesores(id),
  paciente_id bigint references public.pacientes(id),
  localidad text,
  municipio text,
  departamento text,
  numero_paciente text,
  nombre_paciente text,
  actividad text,
  atendido boolean,
  registrado_panacea boolean,
  duracion_minutos integer,
  tipo_contacto text,
  pacientes_programados integer not null default 1,
  pacientes_atendidos integer not null default 0,
  observaciones text,
  creado_por text,
  creado_en timestamptz,
  actualizado_en timestamptz
);
