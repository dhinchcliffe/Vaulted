-- Image bytes live with the vault database, never on the ephemeral web host.
-- Metadata stays in vault_files; private bytes are excluded from tree/search queries.
create table vaulted_private.capture_images (
 file_id uuid primary key references public.vault_files(id),
 sha256 text unique not null,
 data bytea not null check(octet_length(data) between 1 and 3145728)
);
alter table vaulted_private.capture_images enable row level security;
revoke all on vaulted_private.capture_images from public,anon,authenticated;
alter table vaulted_private.share_requests add column image_count integer not null default 0,
 add column image_bytes bigint not null default 0;

create function vaulted_private.put_image(p_data text,p_mime text) returns jsonb
language plpgsql security definer set search_path='' as $$
declare bytes bytea; digest text; ext text; fid uuid; path text;
begin
 if p_data is null or length(p_data)>4194304 then raise sqlstate 'PT400' using message='Image exceeds 3 MiB'; end if;
 bytes=decode(p_data,'base64');
 if octet_length(bytes) not between 1 and 3145728 then raise sqlstate 'PT400' using message='Invalid image size'; end if;
 ext=case
 when p_mime='image/png' and substring(bytes from 1 for 8)=decode('89504e470d0a1a0a','hex') then 'png'
 when p_mime='image/jpeg' and substring(bytes from 1 for 3)=decode('ffd8ff','hex') then 'jpg'
 when p_mime='image/gif' and substring(bytes from 1 for 6) in (convert_to('GIF87a','UTF8'),convert_to('GIF89a','UTF8')) then 'gif'
 when p_mime='image/webp' and substring(bytes from 1 for 4)=convert_to('RIFF','UTF8') and substring(bytes from 9 for 4)=convert_to('WEBP','UTF8') then 'webp'
 when p_mime='image/avif' and substring(bytes from 5 for 4)=convert_to('ftyp','UTF8') and substring(bytes from 9 for 4) in (convert_to('avif','UTF8'),convert_to('avis','UTF8')) then 'avif'
 else null end;
 if ext is null then raise sqlstate 'PT400' using message='Unsupported image bytes'; end if;
 digest=encode(extensions.digest(bytes,'sha256'),'hex');
 -- Serialize identical uploads so no duplicate metadata rows or overwrites occur.
 perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(digest,0));
 select i.file_id,f.path into fid,path from vaulted_private.capture_images i join public.vault_files f on f.id=i.file_id where i.sha256=digest;
 if fid is null then
  path='Attachments/Web/'||digest||'.'||ext;
  insert into public.vault_files(path,mime,size,sha256) values(path,p_mime,octet_length(bytes),digest) returning id into fid;
  insert into vaulted_private.capture_images(file_id,sha256,data) values(fid,digest,bytes);
 end if;
 return jsonb_build_object('path',path,'id',fid);
end;$$;

create function vaulted_private.store_image(p_data text,p_mime text) returns jsonb
language plpgsql security definer set search_path='' as $$
begin
 if auth.uid() is null or not exists(select 1 from public.vault_members where user_id=auth.uid()) then raise sqlstate 'PT403' using message='Vault membership required'; end if;
 return vaulted_private.put_image(p_data,p_mime);
end;$$;

create function vaulted_private.share_image(p_token text,p_request uuid,p_data text,p_mime text) returns jsonb
language plpgsql security definer set search_path='' as $$
declare tid uuid; r vaulted_private.share_requests; bytes_size bigint;
begin
 if p_token is null or p_token !~ '^[A-Za-z0-9_-]{43}$' then raise sqlstate 'PT401' using message='Invalid shortcut token'; end if;
 select s.id into tid from vaulted_private.share_tokens s where s.token_hash=encode(extensions.digest(p_token,'sha256'),'hex') and s.revoked_at is null and s.expires_at>now()
 and exists(select 1 from public.vault_members where user_id=s.user_id) for update;
 if tid is null then raise sqlstate 'PT401' using message='Shortcut token expired or revoked'; end if;
 select * into r from vaulted_private.share_requests where token_id=tid and request_id=p_request for update;
 if not found or r.file_id is not null or r.created_at<now()-interval '1 hour' then raise sqlstate 'PT403' using message='Active unfinished capture required'; end if;
 if p_data is null or length(p_data)>4194304 then raise sqlstate 'PT400' using message='Invalid image size'; end if;
 bytes_size=octet_length(decode(p_data,'base64'));
 if r.image_count>=32 or r.image_bytes+bytes_size>20971520 then raise sqlstate 'PT429' using message='Capture image limit reached'; end if;
 update vaulted_private.share_requests set image_count=image_count+1,image_bytes=image_bytes+bytes_size where token_id=tid and request_id=p_request;
 return vaulted_private.put_image(p_data,p_mime);
end;$$;

create function vaulted_private.read_image(p_id uuid) returns jsonb
language plpgsql security definer set search_path='' as $$
declare result jsonb;
begin
 if auth.uid() is null or not exists(select 1 from public.vault_members where user_id=auth.uid()) then raise sqlstate 'PT403' using message='Vault membership required'; end if;
 select jsonb_build_object('data',encode(data,'base64')) into result from vaulted_private.capture_images where file_id=p_id;
 if result is null then raise sqlstate 'PT404' using message='Image not found'; end if;
 return result;
end;$$;
revoke all on function vaulted_private.put_image(text,text),vaulted_private.store_image(text,text),vaulted_private.share_image(text,uuid,text,text),vaulted_private.read_image(uuid) from public,anon,authenticated;
grant execute on function vaulted_private.store_image(text,text),vaulted_private.read_image(uuid) to authenticated;
grant execute on function vaulted_private.share_image(text,uuid,text,text) to anon,authenticated;
create function public.vault_store_image(p_data text,p_mime text) returns jsonb language sql security invoker set search_path='' as $$select vaulted_private.store_image(p_data,p_mime);$$;
create function public.vault_share_image(p_token text,p_request uuid,p_data text,p_mime text) returns jsonb language sql security invoker set search_path='' as $$select vaulted_private.share_image(p_token,p_request,p_data,p_mime);$$;
create function public.vault_read_image(p_id uuid) returns jsonb language sql security invoker set search_path='' as $$select vaulted_private.read_image(p_id);$$;
revoke all on function public.vault_store_image(text,text),public.vault_share_image(text,uuid,text,text),public.vault_read_image(uuid) from public,anon,authenticated;
grant execute on function public.vault_store_image(text,text),public.vault_read_image(uuid) to authenticated;
grant execute on function public.vault_share_image(text,uuid,text,text) to anon,authenticated;
