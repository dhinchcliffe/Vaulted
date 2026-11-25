# Vaulted development rules

- The Vercel/Supabase application is the official version. New work targets `main`.
- Preserve a remote last-known-good baseline before production changes. Desktop recovery is `baseline/desktop-last-known-good-2026-11-25` at `3b4a49679394feb36ce9c78134f6742a3fbfd384`.
- Make targeted changes; keep capture, authentication, storage and filing separate. Avoid unrelated rewrites.
- Never drop tables or remove original research data. Use additive migrations and scoped verification with test data rolled back or cleaned up.
- Preview and production share the same vault. Preview writes are real writes.
- Run relevant regression/security tests, update CHANGELOG.md, and commit all source. Never commit credentials, tokens, research contents or environment files.
- Share tokens only permit new Inbox captures. Browser sign-in and membership checks remain required for reading, editing, Autofile and moves.
- Shortcut templates must contain no credentials. Sign the generic template before distribution; configure tokens on the user's device.
- Preserve complete source text and source URL. Flag failed/incomplete capture. Still images may be linked; do not import video.
