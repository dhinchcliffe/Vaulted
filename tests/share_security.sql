-- Run as database administrator. Everything, including test notes, rolls back.
begin;
select set_config('request.jwt.claim.sub',(select user_id::text from public.vault_members limit 1),true);
select set_config('vaulted.test_token',rtrim(translate(encode(extensions.gen_random_bytes(32),'base64'),'+/','-_'),'='),true);
select set_config('vaulted.test_request',gen_random_uuid()::text,true);
set local role authenticated;
select set_config('vaulted.test_token_id',(public.vault_share_create_token(encode(extensions.digest(current_setting('vaulted.test_token'),'sha256'),'hex'))->>'id'),true);
do $$begin
 if jsonb_array_length(public.vault_share_tokens())<1 then raise exception 'Token missing'; end if;
end$$;
set local role anon;
do $$begin
 begin
  perform * from vaulted_private.share_tokens;
  raise exception 'Anonymous token-table read was allowed';
 exception when insufficient_privilege then null; end;
 begin
  perform public.vault_share_create_token(repeat('a',64));
  raise exception 'Anonymous token creation was allowed';
 exception when insufficient_privilege then null; end;
 begin
  perform public.vault_share_finish(current_setting('vaulted.test_token'),gen_random_uuid(),'Test','Test');
  raise exception 'Unreserved capture was allowed';
 exception when sqlstate 'PT403' then null; end;
 begin
  perform public.vault_share_claim(repeat('b',43),gen_random_uuid());
  raise exception 'Invalid token was allowed';
 exception when sqlstate 'PT401' then null; end;
end$$;
select public.vault_share_claim(current_setting('vaulted.test_token'),current_setting('vaulted.test_request')::uuid);
select set_config('vaulted.test_file',(public.vault_share_finish(current_setting('vaulted.test_token'),current_setting('vaulted.test_request')::uuid,'../Test/Title','Test capture content')->>'file_id'),true);
do $$declare result jsonb; begin
 result=public.vault_share_finish(current_setting('vaulted.test_token'),current_setting('vaulted.test_request')::uuid,'Overwrite attempt','Changed content');
 if result->>'file_id'<>current_setting('vaulted.test_file') then raise exception 'Retry duplicated note'; end if;
end$$;
reset role;
do $$begin
 if not exists(select 1 from public.vault_files where id=current_setting('vaulted.test_file')::uuid and path like 'ReadItLater Inbox/%' and content='Test capture content') then
  raise exception 'Capture path or idempotency failed'; end if;
end$$;
set local role authenticated;
select public.vault_share_revoke(current_setting('vaulted.test_token_id')::uuid);
set local role anon;
do $$begin
 begin
  perform public.vault_share_claim(current_setting('vaulted.test_token'),gen_random_uuid());
  raise exception 'Revoked token was accepted';
 exception when sqlstate 'PT401' then null; end;
end$$;
reset role;
rollback;
select 'Capture authorization, idempotency, Inbox confinement and revocation passed; test data rolled back' as result;
