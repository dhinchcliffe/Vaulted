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