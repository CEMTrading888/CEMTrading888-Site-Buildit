alter table public.cem_assets enable row level security;

do $$
begin
  create policy cem_assets_public_select
  on public.cem_assets
  for select
  to anon, authenticated
  using (true);
exception
  when duplicate_object then null;
end
$$;

do $$
begin
  create policy cem_assets_public_insert
  on public.cem_assets
  for insert
  to anon, authenticated
  with check (created_by is not null and length(trim(created_by)) > 0 and url is not null and length(trim(url)) > 0);
exception
  when duplicate_object then null;
end
$$;
