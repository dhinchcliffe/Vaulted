# Save to Vaulted

Install from https://vaulted-sable.vercel.app/share/setup while signed in. Create a capture-only token, copy it, download the signed shortcut, open in Shortcuts and paste the token into its setup question. Share one Safari page or X post. Review Autofile in Vaulted and adjust the destination before File Here.

Safari extraction runs in the user's visible page. Enable Allow Running Scripts in Settings → Apps → Shortcuts → Advanced if prompted. X app shares normally provide a URL: the server uses FxTwitter's public API, selecting the longer returned text and still photos only. Shared Safari content takes precedence over a shorter public excerpt. If retrieval fails, preserve supplied content and the source link with a warning. Images are archived inside Vaulted under Attachments/Web, deduplicated by SHA-256, and referenced from the vault root so moving the note does not break them. Failures become explicit original-source links, not remote image embeds. Threads and X Articles are not guaranteed.

## Rebuild

Use Cherri **v2.4.0** from its official release, then:

```sh
python shortcuts/build_shortcut.py
cherri shortcuts/save-to-vaulted.cherri --skip-sign --derive-uuids
mv 'shortcuts/Save to Vaulted_unsigned.shortcut' shortcuts/Save-to-Vaulted.unsigned.shortcut
python shortcuts/build_shortcut.py --embed
```

The final step embeds the exact Safari JavaScript, binds it explicitly to Shortcut Input, and installs the token import question. The compiler's custom-action syntax differs across versions, so this small plist finalization is intentional. Request IDs use the MD5 hash of two random values and the payload solely as an idempotency identifier, not as a security credential. Capture tokens are independent cryptographically random values whose SHA-256 hashes are stored in the database.

On a Mac, sign locally:

```sh
shortcuts sign --mode anyone --input shortcuts/Save-to-Vaulted.unsigned.shortcut --output public/static/shortcuts/Save-to-Vaulted.shortcut
```

This initial release was signed using Shortcuty's documented signing service. Only the generic, credential-free template was submitted. No token or vault data is sent to the signer. `signing-manifest.json` records input and signed SHA-256 values. The signed file has the Apple AEA1 container header. Final installation/execution still requires an actual iPhone or iPad test; server tests do not emulate iOS.

## Security and deployment

- Only `/api/share/capture` accepts a capture bearer token. It validates and reserves quota before remote fetching and saves through restricted database functions.
- Tokens expire after one year, are revocable, limited to ten active tokens per member and 120 capture attempts/hour per token. Raw tokens are never stored.
- The private tables have no direct client grants and deny all through RLS. Public RPC wrappers use SECURITY INVOKER; narrowly scoped private SECURITY DEFINER functions enforce membership or capability checks.
- The capability cannot read, update, move or overwrite any existing note. Duplicate request IDs return the same file ID.
- Review links contain a file UUID, never a token. Login preserves the review path; SameSite=Lax permits incoming GET navigation while existing POST origin/header/form-CSRF protections remain.
- Production's custom application authentication protects the vault. Vercel Standard Protection protects previews/deployment URLs while allowing the production domain to receive authenticated Shortcut requests.
- Run `python -m pytest -q`. Run `tests/share_security.sql` against the dedicated Vaulted database as an administrator; it rolls back all test writes.

## Self-contained images

Capture archives PNG, JPEG, WebP, GIF and AVIF bytes in a private database table, with normal vault_files attachment metadata under Attachments/Web/<sha256>.<extension>. Image bytes are excluded from note search/tree queries and are served only after vault sign-in. This keeps the capture-only credential scoped without adding a service-role secret or public storage bucket. Root-relative Markdown image references are independent of the note folder. The database backup includes these new image bytes. Original imported attachments still use their existing private Storage bucket.

Bounds: 3 MiB per image, 32 unique image URLs / 20 MiB per capture, and a 40-second image-fetch budget. Redirects and DNS are checked for public addresses, responses are size-bounded, and raster signatures are checked. Blocked, unsupported or oversized images become clearly marked original-source links. SVG and video are not imported. A token can append images only to its reserved, unfinished capture; it cannot retrieve bytes, overwrite images, or upload after finishing. Identical image bytes share one immutable attachment. SQL authorization tests are in tests/image_security.sql.

## English translations for X captures

New foreign-language X captures put an explicitly labeled English translation first, preserving the complete original captured content, source URL and archived images below. The saved title uses the English opening so Autofile and search see English first. The translation can differ from the one displayed inside X; the share-sheet URL does not include that UI state. No Shortcut reinstall is needed.

Use FxTwitter’s /status/<id>/en translation when it accompanies the exact same complete original and targets English. Fall back to the existing OpenRouter connection (OPENROUTER_API_KEY; optional OPENROUTER_TRANSLATION_MODEL, default openai/gpt-4o-mini). Known-English posts skip both translation calls. Unknown-language or fuller shared Safari text is detected/translated by AI. The model receives only the selected source text, never credentials or other vault records. Generated text is rendered literally and cannot introduce image embeds.

AI translation handles at most 40,000 characters in 6,000-character chunks, with a 55-second total time budget and no retries. Non-stop/truncated responses and incomplete chunks are rejected as a whole. Translation failure or size limits preserve the original with a visible notice. Image archival and editable Autofile remain unchanged. Existing notes are not rewritten automatically.

## Reddit captures

Use the existing Save to Vaulted Shortcut from Reddit's Share menu or Safari. No reinstall is required. Public post URLs, redd.it short URLs, /s/ app-share links and galleries are recognized server-side. Capture preserves title, complete returned post Markdown, author/subreddit and canonical Reddit source; linked article posts also attempt the destination article and keep its URL. Galleries and inline Reddit images use the existing private Attachments/Web archival. Autofile remains editable before final placement.

Retrieval makes bounded public Reddit requests without cookies or an OAuth account. Reddit can deny automated requests, especially from hosted servers; private, deleted, age-gated or otherwise inaccessible posts are not bypassed. If denied, preserve shared Safari content and flag the capture as incomplete. Open the post in Safari and share visible content/selected text as the fallback. No comments or video are imported. This does not add Reddit translation.

Regression coverage: tests/test_reddit.py (post URLs, native shortlink redirects, redirect boundary, full text, galleries, inline images, source URLs, blocked/deleted posts, linked articles and video omission), plus existing capture/storage/security tests.

## Isolated Reddit on-phone experiment

Install **Reddit to Vaulted Test** from /share/setup#reddit-test with a capture token. Keep the existing Save to Vaulted shortcut. Start in Reddit → Share → More → Reddit to Vaulted Test. Allow Reddit/Vaulted network access if asked. This experiment requests Reddit public post data on the phone, then sends serialized JSON plus the canonical source URL to Vaulted. It has no automatic Safari fallback. Reddit may still deny access or iOS may stop on a networking error; report the exact error, not merely that the capture failed.

Normal post IDs are extracted without a network call; app /s/ links use Expand URL on the phone first. The only Reddit content request is GET https://www.reddit.com/api/info.json?id=t3_<id>&raw_json=1. The capture token is used solely for the POST to Vaulted. Vaulted enforces the existing one-megabyte input bound, validates identity, skips server Reddit retrieval, rejects error pages before saving, and reuses the existing image/Autofile path. Linked external articles and image bytes are still fetched by Vaulted, with existing failure notices. No Reddit session or OAuth credentials are requested or forwarded.

Build with Cherri v2.4.0:

```sh
cherri shortcuts/reddit-phone-test.cherri --skip-sign --derive-uuids
python shortcuts/finalize_reddit_shortcut.py
shortcuts sign --mode anyone --input shortcuts/Reddit-to-Vaulted-Test.unsigned.shortcut --output public/static/shortcuts/Reddit-to-Vaulted-Test.shortcut
```

The finalizer adds the import question, workflow name and distinct deterministic conditional groups. The public credential-free template was signed through the same Shortcuty signing API used for the original template; hashes are in reddit-test-signing-manifest.json. No user content or tokens go to the signer. Keep both source and unsigned/signed artifacts in Git. Do not promote this experiment to the normal Shortcut until a real iPhone capture succeeds.
