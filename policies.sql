-- Habilitar RLS
alter table registros enable row level security;
alter table usuarios  enable row level security;
alter table programas enable row level security;
alter table convenios enable row level security;
alter table instituciones enable row level security;
alter table profesores enable row level security;

-- Lectura global de catálogos
do $$ begin
  create policy read_catalogs_programas on programas for select using (true);
exception when duplicate_object then null; end $$;

do $$ begin
  create policy read_catalogs_convenios on convenios for select using (true);
exception when duplicate_object then null; end $$;

do $$ begin
  create policy read_catalogs_instituciones on instituciones for select using (true);
exception when duplicate_object then null; end $$;

do $$ begin
  create policy read_catalogs_profesores on profesores for select using (true);
exception when duplicate_object then null; end $$;

-- Usuarios visibles solo por admin o ellos mismos
do $$ begin
  create policy read_usuarios on usuarios for select
  using (
    coalesce((select rol from usuarios u where u.email = current_setting('request.jwt.claims', true)::json->>'email'), 'profesor') = 'admin'
    or email = current_setting('request.jwt.claims', true)::json->>'email'
  );
exception when duplicate_object then null; end $$;

-- Registros: un profesor ve sus registros; admin ve todo
do $$ begin
  create policy select_registros on registros for select
  using (
    (creado_por = current_setting('request.jwt.claims', true)::json->>'email')
    or coalesce((select rol from usuarios u where u.email = current_setting('request.jwt.claims', true)::json->>'email'), 'profesor') = 'admin'
  );
exception when duplicate_object then null; end $$;

do $$ begin
  create policy insert_registros on registros for insert
  with check (creado_por = current_setting('request.jwt.claims', true)::json->>'email');
exception when duplicate_object then null; end $$;

do $$ begin
  create policy update_registros on registros for update
  using (
    (creado_por = current_setting('request.jwt.claims', true)::json->>'email')
    or coalesce((select rol from usuarios u where u.email = current_setting('request.jwt.claims', true)::json->>'email'), 'profesor') = 'admin'
  )
  with check (true);
exception when duplicate_object then null; end $$;

do $$ begin
  create policy delete_registros on registros for delete
  using (
    (creado_por = current_setting('request.jwt.claims', true)::json->>'email')
    or coalesce((select rol from usuarios u where u.email = current_setting('request.jwt.claims', true)::json->>'email'), 'profesor') = 'admin'
  );
exception when duplicate_object then null; end $$;
