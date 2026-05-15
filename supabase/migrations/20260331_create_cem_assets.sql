create table if not exists public.cem_assets (
  id uuid default gen_random_uuid() primary key,
  created_by text not null,
  asset_type text default 'generated_image',
  prompt text,
  model_used text,
  url text,
  filename text,
  tags text[],
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz default now()
);

alter table public.cem_assets enable row level security;
