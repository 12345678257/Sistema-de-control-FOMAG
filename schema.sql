-- Tablas base para Supabase (PostgreSQL)

create table if not exists programas(
  id bigserial primary key,
  nombre text unique not null,
  activo boolean default true
);

create table if not exists convenios(
  id bigserial primary key,
  nombre text not null,
  programa_id bigint not null references programas(id),
  activo boolean default true,
  unique(nombre, programa_id)
);

create table if not exists instituciones(
  id bigserial primary key,
  nombre text not null,
  localidad text,
  municipio text,
  departamento text,
  activo boolean default true,
  unique(nombre, municipio, departamento)
);

create table if not exists profesores(
  id bigserial primary key,
  nombre text not null,
  documento text,
  email text,
  programa_id bigint references programas(id),
  convenio_id bigint references convenios(id),
  activo boolean default true
);

create table if not exists usuarios(
  id bigserial primary key,
  email text unique,
  nombre text,
  rol text default 'profesor',
  creado_en timestamptz default now()
);

create table if not exists registros(
  id bigserial primary key,
  fecha date not null,
  programa_id bigint not null references programas(id),
  convenio_id bigint not null references convenios(id),
  institucion_id bigint not null references instituciones(id),
  profesor_id bigint not null references profesores(id),
  localidad text,
  municipio text,
  departamento text,
  pacientes_programados int not null,
  pacientes_atendidos int not null,
  observaciones text,
  creado_por text,
  creado_en timestamptz default now(),
  actualizado_en timestamptz default now()
);
