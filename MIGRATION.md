# Vaulted cloud migration

## Baseline

The uploaded Mac app matches commit `3b4a49679394feb36ce9c78134f6742a3fbfd384`; only the executable permission differed after ZIP extraction. GitHub branch `baseline/mac-mini-2026-11-15` preserves it. The unchanged uploaded archives are the recovery source. Never commit research data, logs, credentials, Obsidian configuration, or virtual environments to this public source repository.

## Separation of concerns

- `app.py`: HTTP routes retaining the existing frontend API contracts.
- `vaulted/storage.py`: user-token-scoped Supabase access and path handling.
- `vaulted/auth.py`: Supabase Auth, HttpOnly session cookies, renewal, membership checks and CSRF protection.
- `vaulted/capture.py`: bounded public-web fetching with address validation, DNS pinning and redirect checks.
- `migrations/001_vault.sql`: schema, RLS, immutable original bucket, revision history, compare-and-swap save and atomic move functions.

Markdown text is editable in Postgres; original file bytes remain in private object storage under content hashes. Binary attachments stay in Storage. Metadata maps original relative paths to object keys. The original snapshot is immutable to web users. Edits record prior versions. Folder moves update paths transactionally without copying blobs. Search preserves substring semantics with a trigram index. No privileged Supabase key is deployed to Vercel.

## Access

Only explicitly enrolled UUIDs in `vault_members` can read or modify the vault. Sign-up alone does not grant access. Login uses Supabase email/password authentication. Change the initial password at `/account`. Vercel deployment protection adds another access boundary during testing. Preview and production currently use the same dedicated vault: preview edits are real edits.

## Validation and recovery

Verify all uploaded objects against SHA-256, compare original counts and byte totals, test anonymous and nonmember denial, then test reading, editing, stale-write rejection, search, renames, attachments and web capture. Code rollback uses the baseline branch; the local baseline still requires the original Dropbox folder. Do not repoint cloud code to local storage or delete originals. Restore note content using `vault_versions`; return current notes to Markdown when exporting. Supabase database backups do not cover Storage bytes. Retain both original ZIPs and arrange independent ongoing database plus object backups before treating this as the sole archive.

## Known differences / setup

AI filing requires `OPENAI_API_KEY`, which was not present in the uploaded app. Existing external images remain external; migration does not claim they have been archived. X pages that refuse server fetching can still be added using Quick Paste. Obsidian device sync remains on Dropbox until explicitly migrated; cloud edits are not bidirectionally synced back to Dropbox. Restarting a Mac server is no longer applicable.
