alter table public.document_pages
  add column warning_messages text[] not null default '{}';
