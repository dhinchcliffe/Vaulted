# 2026-11-25 — migrate external images on existing pages

- Baseline: baseline/before-image-migration-prompt-2026-11-25 at d36a3b8.
- Add a dismissible page banner offering to save external images inside Vaulted. Detection runs on the already-loaded/saved page only, with no remote image downloads or vault-wide scans.
- Reuse the capture downloader, image validation, deduplication and Attachments/Web storage. Cover Markdown images, reference images, external wiki embeds and HTML images/picture renditions; skip code examples and normal hyperlinks.
- Process bounded batches automatically after the user clicks. Preserve failed image references for retry; keep prose, note location and revision history. Compare revisions before downloading and atomically when saving to prevent overwriting concurrent edits.
- Allow navigation during migration; keep the page being migrated read-only and never apply its response to another page or overwrite local edits. Add backend and UI regression tests for these cases. No schema or credential changes.

# 2026-11-25 — English translations for X shares

- Baseline: baseline/before-x-translation-2026-11-25 at 925ad72.
- Add English-first translations for foreign-language X captures, retain original content and source URL, and use an English title. Known-English posts skip translation.
- Use the public post translation endpoint with original-text matching, then the existing AI service as fallback; handle long posts in bounded chunks and reject truncated output. Failures keep the captured original with a visible notice. Model output is escaped to prevent new image embeds.
- No Shortcut reinstall, schema change or rewrite of existing research notes. Validation: 73 tests passed, including translation fallback, English bypass, full originals, images, truncation and note-size handling.

# 2026-11-25 — self-contained captured images

- Baseline: baseline/before-local-images-2026-11-25 at 8d809ad.
- Archive Safari/X shares, Fetch Web and Quick Paste images into Attachments/Web, using content hashes and vault-root references that survive note moves. Store immutable image bytes privately alongside the vault database; keep attachment metadata in vault_files and existing imported Storage assets unchanged.
- Bound image fetches and writes, reject non-raster payloads/private-network URLs, deduplicate identical images, and mark failed captures with original-source links. No video.
- Keep anonymous Shortcut image writes restricted to an active reserved capture. Image reads still require vault membership. Regression and rollback-only SQL tests cover bytes, deduplication, authorization and note movement.

# 2026-11-25 — iOS share capture and official cloud version

- Preserved desktop and cloud baselines on GitHub before changes. Main becomes the official cloud code line.
- Added a signed Save to Vaulted share-sheet Shortcut, token setup/revocation page, capture-only Inbox API and authenticated review links that open Autofile automatically.
- Capture Safari content and source URL; attempt complete public X post text and still photos through FxTwitter. Keep links/shared text with explicit warnings when retrieval fails. No video. Images remain linked.
- Added private hashed capabilities, quota reservation and atomic idempotent capture insertion. Existing research records, buckets and file-access policies are unchanged.
- Preserve review destination across login; retain existing mutation CSRF controls. Added backend regression tests and rollback-only SQL authorization tests.

- Production verification: capture, idempotency and login handoff passed. Scoped the build-source exclusion to the root shortcuts directory so the signed installer remains available under public/static/shortcuts.

## [Unreleased]

### Added
- **Search Feature**: Implemented a new search functionality within the Vaulted app.
  - Added a new API endpoint `/api/search` to search through the vault for specified terms in markdown files.
  - UI update to include a search button and modal for entering search terms.
  - Navigation tree hides while search is active, displaying search results with clickable links to files.
  - Implemented keyboard shortcuts to facilitate usage (Escape key for closing search).

### Fixed
- Ensured existing functionality remains unchanged while introducing the new search feature.

### Notes
- Tests were conducted and the feature behaves as expected, with thorough functionality.
- All updates were securely saved and marked as the last known good with a git tag.