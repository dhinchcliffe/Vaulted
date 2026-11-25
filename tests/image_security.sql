begin;
select set_config('request.jwt.claim.sub',(select user_id::text from public.vault_members limit 1),true);
select set_config('vaulted.test_token',rtrim(translate(encode(extensions.gen_random_bytes(32),'base64'),'+/','-_'),'='),true);
select set_config('vaulted.test_request',gen_random_uuid()::text,true);
select set_config('vaulted.test_png','iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aXXsAAAAASUVORK5CYII=',true);
set local role authenticated;
select set_config('vaulted.test_token_id',(public.vault_share_create_token(encode(extensions.digest(current_setting('vaulted.test_token'),'sha256'),'hex'))->>'id'),true);
set local role anon;
do $$begin
 begin perform public.vault_read_image(gen_random_uuid());raise exception 'Anon read allowed';exception when insufficient_privilege then null;end;
 begin perform public.vault_store_image(current_setting('vaulted.test_png'),'image/png');raise exception 'Anon arbitrary write allowed';exception when insufficient_privilege then null;end;
 begin perform public.vault_share_image(current_setting('vaulted.test_token'),gen_random_uuid(),current_setting('vaulted.test_png'),'image/png');raise exception 'Unreserved image allowed';exception when sqlstate 'PT403' then null;end;
end$$;
select public.vault_share_claim(current_setting('vaulted.test_token'),current_setting('vaulted.test_request')::uuid);
select set_config('vaulted.test_image',(public.vault_share_image(current_setting('vaulted.test_token'),current_setting('vaulted.test_request')::uuid,current_setting('vaulted.test_png'),'image/png'))->>'id',true);
do $$declare result jsonb;begin
 result=public.vault_share_image(current_setting('vaulted.test_token'),current_setting('vaulted.test_request')::uuid,current_setting('vaulted.test_png'),'image/png');
 if result->>'id'<>current_setting('vaulted.test_image') or result->>'path' not like 'Attachments/Web/%.png' then raise exception 'Dedup/path failed';end if;
 begin perform public.vault_share_image(current_setting('vaulted.test_token'),current_setting('vaulted.test_request')::uuid,encode(convert_to('<svg>','UTF8'),'base64'),'image/png');raise exception 'SVG allowed';exception when sqlstate 'PT400' then null;end;
end$$;
select set_config('vaulted.test_file',(public.vault_share_finish(current_setting('vaulted.test_token'),current_setting('vaulted.test_request')::uuid,'Image test','![image](/Attachments/Web/test.png)'))->>'file_id',true);
do $$begin
 begin perform public.vault_share_image(current_setting('vaulted.test_token'),current_setting('vaulted.test_request')::uuid,current_setting('vaulted.test_png'),'image/png');raise exception 'Finished capture upload allowed';exception when sqlstate 'PT403' then null;end;
end$$;
set local role authenticated;
do $$declare original_path text; original_image_path text;begin
 select path into original_path from public.vault_files where id=current_setting('vaulted.test_file')::uuid;
 select path into original_image_path from public.vault_files where id=current_setting('vaulted.test_image')::uuid;
 perform public.vault_move(original_path,'Image-Test-Moved/'||current_setting('vaulted.test_file')||'.md');
 if not exists(select 1 from public.vault_files where id=current_setting('vaulted.test_image')::uuid and path=original_image_path) then raise exception 'Note move changed image path';end if;
 if decode(public.vault_read_image(current_setting('vaulted.test_image')::uuid)->>'data','base64')<>decode(current_setting('vaulted.test_png'),'base64') then raise exception 'Image read mismatch';end if;
 perform public.vault_share_revoke(current_setting('vaulted.test_token_id')::uuid);
end$$;
set local role anon;
do $$begin
 begin perform public.vault_share_image(current_setting('vaulted.test_token'),current_setting('vaulted.test_request')::uuid,current_setting('vaulted.test_png'),'image/png');raise exception 'Revoked token allowed';exception when sqlstate 'PT401' then null;end;
end$$;
reset role;
rollback;
select 'Image authorization, bytes, deduplication, note moves, finished-capture denial and revocation passed; all test writes rolled back' as result;
