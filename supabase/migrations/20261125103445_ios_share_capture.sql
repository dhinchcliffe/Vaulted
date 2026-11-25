-- Additive capture-only capabilities. Existing notes/policies/buckets are untouched.
create schema if not exists vaulted_private;
revoke all on schema vaulted_private from public;
grant usage on schema vaulted_private to anon, authenticated;

create table vaulted_private.share_tokens (
 id uuid primary key default gen_random_uuid(),
 user_id uuid not null references auth.users(id),
 token_hash text unique not null check(token_hash ~ '^[a-f0-9]{64}$'),
 created_at timestamptz not null default now(),
 expires_at timestamptz not null default now()+interval '1 year',
 revoked_at timestamptz,
 window_start timestamptz not null default now(),
 attempts integer not null default 0
);
create index share_tokens_user_idx on vaulted_private.share_tokens(user_id);
create table vaulted_private.share_requests (
 token_id uuid not null references vaulted_private.share_tokens(id),
 request_id uuid not null,
 created_at timestamptz not null default now(),
 file_id uuid references public.vault_files(id),
 primary key(token_id,request_id)
);
create index share_requests_file_idx on vaulted_private.share_requests(file_id);
alter table vaulted_private.share_tokens enable row level security;
alter table vaulted_private.share_requests enable row level security;
revoke all on vaulted_private.share_tokens,vaulted_private.share_requests from public,anon,authenticated;

create function vaulted_private.share_create_token(p_hash text) returns jsonb
language plpgsql security definer set search_path='' as $$
declare token_id uuid;
begin
 if auth.uid() is null or not exists(select 1 from public.vault_members where user_id=auth.uid()) then
  raise sqlstate 'PT403' using message='Vault membership required'; end if;
 -- Serialize token creation per user, including the ten-token ceiling.
 perform 1 from public.vault_members where user_id=auth.uid() for update;
 if (select count(*) from vaulted_private.share_tokens where user_id=auth.uid() and revoked_at is null and expires_at>now())>=10 then
  raise sqlstate 'PT429' using message='Revoke an old shortcut token before creating another'; end if;
 insert into vaulted_private.share_tokens(user_id,token_hash) values(auth.uid(),p_hash) returning id into token_id;
 return jsonb_build_object('id',token_id);
end;$$;
create function vaulted_private.share_tokens_list() returns jsonb
language plpgsql security definer set search_path='' as $$
begin
 if auth.uid() is null or not exists(select 1 from public.vault_members where user_id=auth.uid()) then
  raise sqlstate 'PT403' using message='Vault membership required'; end if;
 return coalesce((select jsonb_agg(jsonb_build_object('id',id,'created_at',created_at,'expires_at',expires_at) order by created_at desc)
 from vaulted_private.share_tokens where user_id=auth.uid() and revoked_at is null and expires_at>now()),'[]'::jsonb);
end;$$;
create function vaulted_private.share_revoke(p_id uuid) returns void
language plpgsql security definer set search_path='' as $$
begin
 if auth.uid() is null or not exists(select 1 from public.vault_members where user_id=auth.uid()) then
  raise sqlstate 'PT403' using message='Vault membership required'; end if;
 update vaulted_private.share_tokens set revoked_at=now() where id=p_id and user_id=auth.uid();
end;$$;

-- These two functions deliberately authenticate a capability instead of auth.uid().
-- They only reserve a bounded capture and insert a NEW Inbox note. No vault reads,
-- updates, arbitrary paths or service-role credentials are exposed to the shortcut.
create function vaulted_private.share_claim(p_token text,p_request uuid) returns jsonb
language plpgsql security definer set search_path='' as $$
declare t vaulted_private.share_tokens; f uuid;
begin
 if p_token is null or p_token !~ '^[A-Za-z0-9_-]{43}$' or p_request is null then
  raise sqlstate 'PT401' using message='Invalid shortcut token'; end if;
 select * into t from vaulted_private.share_tokens where token_hash=encode(extensions.digest(p_token,'sha256'),'hex')
 and revoked_at is null and expires_at>now() for update;
 if not found or not exists(select 1 from public.vault_members where user_id=t.user_id) then
  raise sqlstate 'PT401' using message='Shortcut token expired or revoked. Create a new one in Vaulted.'; end if;
 if t.window_start<now()-interval '1 hour' then t.attempts=0; t.window_start=now(); end if;
 if t.attempts>=120 then raise sqlstate 'PT429' using message='Capture limit reached. Try again later.'; end if;
 update vaulted_private.share_tokens set window_start=t.window_start,attempts=t.attempts+1 where id=t.id;
 insert into vaulted_private.share_requests(token_id,request_id) values(t.id,p_request) on conflict do nothing;
 select file_id into f from vaulted_private.share_requests where token_id=t.id and request_id=p_request;
 return jsonb_build_object('file_id',f);
end;$$;
create function vaulted_private.share_finish(p_token text,p_request uuid,p_title text,p_content text) returns jsonb
language plpgsql security definer set search_path='' as $$
declare t uuid; r vaulted_private.share_requests; new_id uuid; title text;
begin
 if p_token is null or p_token !~ '^[A-Za-z0-9_-]{43}$' then raise sqlstate 'PT401' using message='Invalid shortcut token'; end if;
 select s.id into t from vaulted_private.share_tokens s
 where s.token_hash=encode(extensions.digest(p_token,'sha256'),'hex') and s.revoked_at is null and s.expires_at>now()
 and exists(select 1 from public.vault_members where user_id=s.user_id) for update;
 if not found then raise sqlstate 'PT401' using message='Shortcut token expired or revoked'; end if;
 select * into r from vaulted_private.share_requests where token_id=t and request_id=p_request for update;
 if not found then raise sqlstate 'PT403' using message='Capture was not reserved'; end if;
 if r.file_id is not null then return jsonb_build_object('file_id',r.file_id); end if;
 if r.created_at<now()-interval '1 hour' then raise sqlstate 'PT410' using message='Capture expired. Share again.'; end if;
 if p_content is null or octet_length(p_content)>1000000 or length(trim(p_content))=0 then
  raise sqlstate 'PT400' using message='Invalid capture content'; end if;
 title=left(trim(regexp_replace(coalesce(p_title,'Shared note'),'[[:cntrl:]\\/:*?"<>|]','','g')),120);
 if title='' then title='Shared note'; end if;
 new_id=gen_random_uuid();
 insert into public.vault_files(id,path,content,mime,size)
 values(new_id,'ReadItLater Inbox/'||title||' - '||new_id::text||'.md',p_content,'text/markdown',octet_length(p_content));
 update vaulted_private.share_requests set file_id=new_id where token_id=t and request_id=p_request;
 return jsonb_build_object('file_id',new_id);
end;$$;

revoke all on all functions in schema vaulted_private from public,anon,authenticated;
grant execute on function vaulted_private.share_create_token(text),vaulted_private.share_tokens_list(),vaulted_private.share_revoke(uuid) to authenticated;
grant execute on function vaulted_private.share_claim(text,uuid),vaulted_private.share_finish(text,uuid,text,text) to anon,authenticated;
create function public.vault_share_create_token(p_hash text) returns jsonb language sql security invoker set search_path='' as $$select vaulted_private.share_create_token(p_hash);$$;
create function public.vault_share_tokens() returns jsonb language sql security invoker set search_path='' as $$select vaulted_private.share_tokens_list();$$;
create function public.vault_share_revoke(p_id uuid) returns void language sql security invoker set search_path='' as $$select vaulted_private.share_revoke(p_id);$$;
create function public.vault_share_claim(p_token text,p_request uuid) returns jsonb language sql security invoker set search_path='' as $$select vaulted_private.share_claim(p_token,p_request);$$;
create function public.vault_share_finish(p_token text,p_request uuid,p_title text,p_content text) returns jsonb language sql security invoker set search_path='' as $$select vaulted_private.share_finish(p_token,p_request,p_title,p_content);$$;
revoke all on function public.vault_share_create_token(text),public.vault_share_tokens(),public.vault_share_revoke(uuid),public.vault_share_claim(text,uuid),public.vault_share_finish(text,uuid,text,text) from public,anon,authenticated;
grant execute on function public.vault_share_create_token(text),public.vault_share_tokens(),public.vault_share_revoke(uuid) to authenticated;
grant execute on function public.vault_share_claim(text,uuid),public.vault_share_finish(text,uuid,text,text) to anon,authenticated;
