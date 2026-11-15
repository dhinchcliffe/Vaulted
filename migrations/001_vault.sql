create table public.vault_members (user_id uuid primary key references auth.users(id));
alter table public.vault_members enable row level security;
create policy own_membership on public.vault_members for select to authenticated using(user_id=(select auth.uid()));
grant select on public.vault_members to authenticated;
create table public.vault_files (
 id uuid primary key default gen_random_uuid(), path text unique not null,
 content text, object_key text, mime text not null default 'application/octet-stream',
 size bigint not null default 0, sha256 text, revision integer not null default 1,
 updated_at timestamptz not null default now(),
 check(path<>'' and path not like '/%' and path !~ '(^|/)\.\.(/|$)')
);
create table public.vault_versions (
 id bigint generated always as identity primary key, file_id uuid not null,
 path text not null, content text, revision integer not null, saved_at timestamptz not null default now()
);
create index vault_versions_file_idx on public.vault_versions(file_id,saved_at desc);
create extension if not exists pg_trgm with schema extensions;
create index vault_content_trgm_idx on public.vault_files using gin(content extensions.gin_trgm_ops);
alter table public.vault_files enable row level security;
alter table public.vault_versions enable row level security;
create policy member_files on public.vault_files for all to authenticated
 using(exists(select 1 from public.vault_members)) with check(exists(select 1 from public.vault_members));
create policy member_versions_read on public.vault_versions for select to authenticated using(exists(select 1 from public.vault_members));
create policy member_versions_insert on public.vault_versions for insert to authenticated with check(exists(select 1 from public.vault_members));
grant select,insert,update on public.vault_files to authenticated;
grant select,insert on public.vault_versions to authenticated;
grant usage on sequence public.vault_versions_id_seq to authenticated;
create function public.preserve_vault_version() returns trigger language plpgsql security invoker set search_path='' as $$
begin
 insert into public.vault_versions(file_id,path,content,revision) values(old.id,old.path,old.content,old.revision);
 new.revision=old.revision+1; new.updated_at=now();
 return new;
end;$$;
create trigger preserve_version before update on public.vault_files for each row execute function public.preserve_vault_version();
create function public.vault_save(p_path text,p_content text,p_revision integer) returns jsonb language plpgsql security invoker set search_path='' as $$
declare r public.vault_files;
begin
 update public.vault_files set content=p_content,size=octet_length(p_content),sha256=null
 where path=p_path and revision=p_revision and content is not null returning * into r;
 if not found then raise sqlstate 'PT409' using message='This file changed elsewhere. Your edits have not overwritten it.'; end if;
 return jsonb_build_object('success',true,'revision',r.revision);
end;$$;
create function public.vault_move(p_from text,p_to text) returns jsonb language plpgsql security invoker set search_path='' as $$
declare n integer;
begin
 if p_to='' or p_to like '/%' or p_to ~ '(^|/)\.\.(/|$)' or p_to=p_from or left(p_to,length(p_from)+1)=p_from||'/' then raise sqlstate 'PT400' using message='Invalid destination'; end if;
 if exists(select 1 from public.vault_files where path=p_to or left(path,length(p_to)+1)=p_to||'/') then raise sqlstate 'PT409' using message='Destination already exists'; end if;
 update public.vault_files set path=p_to||substring(path from length(p_from)+1)
 where path=p_from or left(path,length(p_from)+1)=p_from||'/';
 get diagnostics n=row_count;
 if n=0 then raise sqlstate 'PT404' using message='Source not found'; end if;
 return jsonb_build_object('success',true,'new_path',p_to,'count',n);
end;$$;
create function public.vault_search(p_query text) returns table(path text,preview text,matches integer) language sql stable security invoker set search_path='' as $$
 select path,substring(content from greatest(1,strpos(lower(content),lower(p_query))-60) for 220),
 ((length(lower(content))-length(replace(lower(content),lower(p_query),'')))/greatest(1,length(p_query)))::integer
 from public.vault_files where p_query<>'' and content ilike '%'||replace(replace(replace(p_query,'\','\\'),'%','\%'),'_','\_')||'%'
 order by 3 desc,path limit 200;
$$;
revoke all on function public.vault_save(text,text,integer),public.vault_move(text,text),public.vault_search(text),public.preserve_vault_version() from public,anon;
grant execute on function public.vault_save(text,text,integer),public.vault_move(text,text),public.vault_search(text) to authenticated;
insert into storage.buckets(id,name,public,file_size_limit) values('vault-original','vault-original',false,52428800);
create policy member_storage_read on storage.objects for select to authenticated using(bucket_id='vault-original' and exists(select 1 from public.vault_members));
