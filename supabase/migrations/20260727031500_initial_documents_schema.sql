-- Milestone 8: Supabase persistence foundation.
-- This migration is drafted locally first and should be reviewed before applying.

create extension if not exists pgcrypto with schema extensions;

create table public.documents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  library_document_id uuid null,
  title text not null check (char_length(trim(title)) > 0),
  recording_title text null,
  target_language text null check (
    target_language is null
    or target_language in ('cantonese', 'mandarin', 'english')
  ),
  tts_voice text null,
  original_filename text null,
  source_type text not null check (source_type in ('pdf', 'images')),
  source_storage_bucket text null,
  source_storage_path text null,
  total_pages integer not null check (total_pages > 0),
  status text not null check (
    status in (
      'uploaded',
      'normalizing_pages',
      'inspecting',
      'extracting_text',
      'running_ocr',
      'text_ready',
      'generating_audio',
      'ready',
      'failed'
    )
  ),
  error_message text null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint documents_id_user_id_unique unique (id, user_id),
  constraint documents_library_document_id_fkey
    foreign key (library_document_id, user_id)
    references public.documents (id, user_id)
    on delete set null (library_document_id)
);

create table public.document_pages (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null,
  user_id uuid not null,
  page_number integer not null check (page_number > 0),
  original_filename text null,
  original_image_storage_bucket text null,
  original_image_storage_path text null,
  processed_image_storage_bucket text null,
  processed_image_storage_path text null,
  extraction_method text not null check (
    extraction_method in ('pending', 'embedded_text', 'ocr')
  ),
  extracted_text text not null default '',
  error_message text null,
  rotation_degrees integer not null default 0 check (
    rotation_degrees in (0, 90, 180, 270)
  ),
  processing_status text not null check (
    processing_status in (
      'pending',
      'normalizing',
      'extracting',
      'running_ocr',
      'completed',
      'failed'
    )
  ),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint document_pages_document_user_fkey
    foreign key (document_id, user_id)
    references public.documents (id, user_id)
    on delete cascade,
  constraint document_pages_document_page_number_unique
    unique (document_id, page_number),
  constraint document_pages_id_document_user_unique
    unique (id, document_id, user_id)
);

create table public.audio_segments (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null,
  user_id uuid not null,
  page_id uuid null,
  segment_number integer not null check (segment_number > 0),
  source_text text not null,
  audio_storage_bucket text null,
  audio_storage_path text null,
  duration_seconds numeric(10, 3) null check (
    duration_seconds is null
    or duration_seconds >= 0
  ),
  processing_status text not null check (
    processing_status in ('pending', 'generating', 'completed', 'failed')
  ),
  error_message text null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint audio_segments_document_user_fkey
    foreign key (document_id, user_id)
    references public.documents (id, user_id)
    on delete cascade,
  constraint audio_segments_page_document_user_fkey
    foreign key (page_id, document_id, user_id)
    references public.document_pages (id, document_id, user_id),
  constraint audio_segments_document_segment_number_unique
    unique (document_id, segment_number)
);

create table public.listening_progress (
  user_id uuid not null references auth.users (id) on delete cascade,
  document_id uuid not null,
  current_segment_number integer not null default 1 check (
    current_segment_number > 0
  ),
  position_seconds numeric(10, 3) not null default 0 check (
    position_seconds >= 0
  ),
  playback_speed numeric(4, 2) not null default 1 check (
    playback_speed >= 0.5
    and playback_speed <= 3
  ),
  completed boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (user_id, document_id),
  constraint listening_progress_document_user_fkey
    foreign key (document_id, user_id)
    references public.documents (id, user_id)
    on delete cascade
);

create index documents_user_updated_at_idx
  on public.documents (user_id, updated_at desc);

create index documents_user_library_document_id_idx
  on public.documents (user_id, library_document_id);

create index document_pages_user_document_page_number_idx
  on public.document_pages (user_id, document_id, page_number);

create index audio_segments_user_document_segment_number_idx
  on public.audio_segments (user_id, document_id, segment_number);

create index audio_segments_user_page_id_idx
  on public.audio_segments (user_id, page_id);

create index listening_progress_user_updated_at_idx
  on public.listening_progress (user_id, updated_at desc);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

revoke execute on function public.set_updated_at() from public, anon, authenticated;

create trigger documents_set_updated_at
  before update on public.documents
  for each row
  execute function public.set_updated_at();

create trigger document_pages_set_updated_at
  before update on public.document_pages
  for each row
  execute function public.set_updated_at();

create trigger audio_segments_set_updated_at
  before update on public.audio_segments
  for each row
  execute function public.set_updated_at();

create trigger listening_progress_set_updated_at
  before update on public.listening_progress
  for each row
  execute function public.set_updated_at();

alter table public.documents enable row level security;
alter table public.document_pages enable row level security;
alter table public.audio_segments enable row level security;
alter table public.listening_progress enable row level security;

grant usage on schema public to authenticated;
grant select, insert, update, delete on public.documents to authenticated;
grant select, insert, update, delete on public.document_pages to authenticated;
grant select, insert, update, delete on public.audio_segments to authenticated;
grant select, insert, update, delete on public.listening_progress to authenticated;

create policy "Users can read their documents"
  on public.documents
  for select
  to authenticated
  using ((select auth.uid()) = user_id);

create policy "Users can create their documents"
  on public.documents
  for insert
  to authenticated
  with check ((select auth.uid()) = user_id);

create policy "Users can update their documents"
  on public.documents
  for update
  to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

create policy "Users can delete their documents"
  on public.documents
  for delete
  to authenticated
  using ((select auth.uid()) = user_id);

create policy "Users can read their document pages"
  on public.document_pages
  for select
  to authenticated
  using ((select auth.uid()) = user_id);

create policy "Users can create their document pages"
  on public.document_pages
  for insert
  to authenticated
  with check ((select auth.uid()) = user_id);

create policy "Users can update their document pages"
  on public.document_pages
  for update
  to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

create policy "Users can delete their document pages"
  on public.document_pages
  for delete
  to authenticated
  using ((select auth.uid()) = user_id);

create policy "Users can read their audio segments"
  on public.audio_segments
  for select
  to authenticated
  using ((select auth.uid()) = user_id);

create policy "Users can create their audio segments"
  on public.audio_segments
  for insert
  to authenticated
  with check ((select auth.uid()) = user_id);

create policy "Users can update their audio segments"
  on public.audio_segments
  for update
  to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

create policy "Users can delete their audio segments"
  on public.audio_segments
  for delete
  to authenticated
  using ((select auth.uid()) = user_id);

create policy "Users can read their listening progress"
  on public.listening_progress
  for select
  to authenticated
  using ((select auth.uid()) = user_id);

create policy "Users can create their listening progress"
  on public.listening_progress
  for insert
  to authenticated
  with check ((select auth.uid()) = user_id);

create policy "Users can update their listening progress"
  on public.listening_progress
  for update
  to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

create policy "Users can delete their listening progress"
  on public.listening_progress
  for delete
  to authenticated
  using ((select auth.uid()) = user_id);

insert into storage.buckets (id, name, public)
values
  ('documents-source', 'documents-source', false),
  ('documents-pages', 'documents-pages', false),
  ('documents-audio', 'documents-audio', false)
on conflict (id) do update
set public = excluded.public;

create policy "Users can read their document storage objects"
  on storage.objects
  for select
  to authenticated
  using (
    bucket_id in ('documents-source', 'documents-pages', 'documents-audio')
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

create policy "Users can create their document storage objects"
  on storage.objects
  for insert
  to authenticated
  with check (
    bucket_id in ('documents-source', 'documents-pages', 'documents-audio')
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

create policy "Users can update their document storage objects"
  on storage.objects
  for update
  to authenticated
  using (
    bucket_id in ('documents-source', 'documents-pages', 'documents-audio')
    and (storage.foldername(name))[1] = (select auth.uid())::text
  )
  with check (
    bucket_id in ('documents-source', 'documents-pages', 'documents-audio')
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

create policy "Users can delete their document storage objects"
  on storage.objects
  for delete
  to authenticated
  using (
    bucket_id in ('documents-source', 'documents-pages', 'documents-audio')
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );
