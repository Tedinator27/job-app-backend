-- Run this in your Supabase project's SQL editor

create table public.profiles (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid references auth.users(id) on delete cascade unique not null,
  resume     text,
  linkedin   text,
  github     text,
  updated_at timestamptz default now()
);

create table public.applications (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid references auth.users(id) on delete cascade not null,
  kind       text not null,
  company    text,
  role       text,
  output     text not null,
  created_at timestamptz default now()
);

alter table public.profiles enable row level security;
alter table public.applications enable row level security;
