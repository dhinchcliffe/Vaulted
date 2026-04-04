# Vaulted Changelog

## 2026-04-04

### Added
- **Add Web Page by URL feature**: New "+ Web" button in toolbar
  - Prompts for URL input
  - Fetches web page content with proper headers
  - Extracts main content and converts HTML to Markdown
  - Saves to `ReadItLater Inbox/` folder with timestamped filename
  - Auto-refreshes file tree and opens new file
  - Handles duplicate filenames by appending numbers

### Technical
- Added `/api/fetch-web` endpoint with HTML-to-Markdown parser
- Added `HTMLToMarkdown` class for content extraction
- Added primary button styling for "+ Web" button
- Server temporarily running on port 5007 due to port conflict

## 2026-04-04 (Earlier)

### Fixed
- Wikipedia page rendering and external images now work correctly
- Fixed `renderPreview()` function that had duplicate variable declarations
- External URLs (Wikimedia Commons, etc.) now pass through unchanged
- Local wiki-link images (`![[...]]`) still work as before

