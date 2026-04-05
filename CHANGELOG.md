# Vaulted Changelog

## 2026-04-05

### Added
- **Persist tree expansion state**: Folder open/closed state is now saved to localStorage
  - Automatically saves when you expand/collapse folders
  - Restores same state on next visit
  - New folders (not in saved state) default to expanded
  - Per-client storage (each browser/device has its own state)

- **`/api/restart` endpoint**: Graceful server restart for code updates
  - POST to `/api/restart` to trigger shutdown
  - LaunchAgent auto-restarts within 10 seconds with latest code
  - CLI tool: `restart-app.sh vaulted`
  - Supported apps tracked in endpoint docstring

- **Wikipedia images support**: Web fetch now preserves images
  - Uses MediaWiki API to get HTML content
  - Converts to Markdown with `markdownify` (preserves images)
  - Images included as `![](url)` markdown
  - Lists all page images at bottom of article

### Changed
- **Improved web page fetching with specialized extractors**:
  - **Wikipedia pages**: Uses MediaWiki API for full HTML content
    - No edit buttons, navigation, or language links
    - Clean text with proper section headers
    - Images preserved and converted to markdown
  - **General sites**: Uses `markdownify` library for better HTML-to-Markdown conversion
    - Better handling of article content
    - Cleaner markdown output
  - **Fallback**: Legacy parser still available if libraries not installed

### Fixed
- **Protocol-relative image URLs**: Images with `//domain.com/path` now convert to `https://domain.com/path`
  - Fixes Wikipedia images that use protocol-relative URLs
  - All 4 image URL types now handled: wiki-links, relative paths, absolute paths, protocol-relative
- **Filename format for saved web pages**: Now `Title - Date.md` instead of `Date - Title.md`
  - Easier to scan and find articles in ReadItLater Inbox
- **Wiki-link images try multiple locations**: `![[image.png]]` now finds images in:
  1. Explicit path (if specified: `![[folder/image.png]]`)
  2. Current file's directory (local folder)
  3. Vault root
  
  Previously only resolved from vault root. Now matches Obsidian's flexible behavior.
  Standard markdown images `![](path)` still resolve relative to file location only.

### Changed
- **Folder-first sorting in file tree**: Directories now appear before files at every level
  - Root folders sorted alphabetically appear first
  - Root files sorted alphabetically appear after all folders
  - Same sorting applies recursively to all subdirectories
  - Case-insensitive alphabetical sorting

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

