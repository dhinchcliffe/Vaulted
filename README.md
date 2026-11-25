# Vaulted

The official Vaulted application is the Vercel/Supabase version on `main`: https://vaulted-sable.vercel.app

Browse, search and edit the research vault, capture webpages and X posts, then use Autofile to suggest a destination you can adjust before filing.

## Save from iPhone or iPad

Open https://vaulted-sable.vercel.app/share/setup, create your capture-only token, and install the signed Save to Vaulted shortcut. Share a Safari page or X post to save it and open Autofile. Source URLs and available still images are preserved; videos are excluded. See [shortcut instructions](shortcuts/README.md) for limitations and reproducible build steps.

## Development

Install `requirements.txt` plus pytest; run `python -m pytest -q`. Configure the variables in `.env.example` through your deployment settings. `app.py` runs Flask; modules under `vaulted/` own authentication, storage, capture and filing.

The original cloud schema is in `migrations/001_vault.sql`. Subsequent changes are in `supabase/migrations/`. Never reapply the initial schema to an existing vault. See `MIGRATION.md` for cloud data and recovery details.

## Recovery baselines

Desktop hosting: `baseline/desktop-last-known-good-2026-11-25`, commit `3b4a49679394feb36ce9c78134f6742a3fbfd384`. This preserves the Mac/Dropbox application and its original setup instructions.

Cloud before iOS capture: `baseline/cloud-before-ios-share-2026-11-25`, commit `2f05fafa65d650e02d8ab80af0b89d84bb57d5fa`.
