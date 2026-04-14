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