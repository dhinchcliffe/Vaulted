# 2026-11-28 — isolated Reddit on-phone capture experiment

- Add a separately named, signed Reddit to Vaulted Test Shortcut. The existing signed Save to Vaulted file and workflow are unchanged. Preserve baseline/before-reddit-phone-fetch-2026-11-28 at 86b2f8b.
- Resolve Reddit app short links on the phone as needed and request public post data from the phone through Reddit's info endpoint. No Vaulted token is sent to Reddit. No Safari fallback or new third-party runtime service is added.
- Accept bounded phone-supplied Reddit JSON in the existing authenticated capture pipeline; match the post ID to the source URL and reuse post parsing, private image archival and editable Autofile. Skip the server Reddit lookup for these captures. Reject block pages, malformed/empty data and mismatched posts without saving a note.
- Validation: 124 tests passed; three unrelated browser suites skipped without Playwright. Shortcut URL patterns, token isolation, block-response rejection and source identity are covered.
- Add experiment installation instructions and reproducible source/signing metadata. Compilation and backend tests do not establish whether Reddit permits the user's iPhone; a real-device trial is required before promoting this into the standard Shortcut.

# 2026-11-28 — Reddit iOS share capture

- Existing Save to Vaulted Shortcut now recognizes Reddit posts, galleries, redd.it and native-app /s/ share links. No Shortcut reinstall or new credentials.
- Preserve full public post text, title, source URL and ordered still-image galleries; resolve inline Reddit image IDs. Linked article posts include the article when accessible and keep both sources. Reuse existing private image archival and editable Autofile review. No comments or video imports.
- Bound public retrieval, validate post identity, restrict shortlink redirects to Reddit hosts, and retain Safari-shared content with an explicit warning when Reddit denies access. Restricted/deleted posts and linked-article failures never silently count as complete captures.
- Validation: 111 Python tests and the image-migration UI regression passed (three unrelated browser suites skipped without Playwright). Vercel preview confirmed Reddit currently denies server retrieval; URL-only captures explicitly report failure and Safari-supplied content survives. Native app URL capture is therefore best effort, not guaranteed.
- No schema, authentication or layout changes. Recovery point: `baseline/before-reddit-capture-2026-11-28` at `7d1c7ed`.

# 2026-11-27 — keep renamed pages visible and editable

- Rename edits the title of a Markdown page. The server preserves the lowercase .md suffix, including for older clients. Folder names retain their original semantics, and the existing move operation rejects occupied destinations.
- Carry the open editor's revision forward by the single move-trigger increment, preserving concurrent edit detection. When reopening the vault, recover a stale last-file path from the recent page's stable ID.
- The live repair restored the suffix on two records in place. Both document bodies matched pre-rename versions, and all seven referenced archived images matched their stored SHA-256 hashes.
- Recovery point: `baseline/before-rename-safety-2026-11-27` at `e1dee58`.

# 2026-11-27 — reveal recent pages in the physical tree

- Selecting a recent page opens the original by ID, expands its parent folders and brings the selected physical row into view. On phones, Browse stays open for this action. Ordinary file taps still return to the document.
- Recovery point: `baseline/before-recent-tree-reveal-2026-11-27` at `b07493a`.

# 2026-11-27 — phone navigation and touch tree menus

- On narrow touch screens, Browse opens the existing vault tree and search over the full-width editor. Edit or Preview stays on the toolbar. More contains Paste, Web, Auto-File and a remembered full-layout option. Dismissing Browse preserves the draft and reading position. A failed save keeps the drawer open and reports the conflict.
- Tap a physical row's ellipsis or hold its label to open the existing actions. Folders support Add Page and Rename. Pages support Rename. Scrolling cancels a hold. Recently used entries continue to link to their originals.
- The compact presentation is in `phone-layout.css` and `phone-layout.js`. Full-size iPad and desktop use the existing layout. Browser tests use synthetic notes for touch gestures, creation and renaming, search, rotation, layout preferences, share review and edit conflicts.
- Recovery point: `baseline/before-phone-layout-2026-11-27` at `13b6bc5`, the production version with the 100-page history.

# 2026-11-27 — longer recent page history

- Raised the browser's recently used page limit from 10 to 100. Existing entries carry over and new visits fill the remaining slots.
- Recovery point: `baseline/before-recent-limit-100-2026-11-27` at `f1793fe`.

# 2026-11-27 — recently used pages

- Added an expandable dark green section at the top of the navigation tree. It lists the last 10 distinct pages opened in this browser, newest first, and remembers when collapsed.
- Recent entries store only file IDs locally. They open the original at its current path through the existing authenticated file endpoint, including after a rename or folder move. The section uses the tree already loaded and adds no database writes or schema changes.
- Recovery point: `baseline/before-recent-pages-2026-11-27` at `30e991f`.

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
