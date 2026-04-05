# Vaulted - Project Documentation

## Overview
Vaulted is a minimal, elegant web-based viewer and editor for Obsidian vaults. Built with Flask backend and vanilla JavaScript frontend.

## Quick Reference
- **Location:** `~/openclaw/vaulted/`
- **URL:** http://localhost:5006
- **Vault Path:** `~/Dropbox/Apps/remotely-save/DPH Research`
- **Git:** `~/openclaw/vaulted/.git` (tag v0.9 baselined)
- **Auto-start:** `com.openclaw.vaulted` LaunchAgent

## Architecture

### Backend (Flask)
- **Entry:** `app.py` (port 5006)
- **Virtual Env:** `~/openclaw/vaulted/venv/`
- **Key Functions:**
  - `get_file_tree()` - Builds directory tree, skips hidden files
  - `find_first_markdown()` - Finds first accessible (non-sparse) .md file
  - `/api/tree` - Returns vault structure as JSON
  - `/api/file` - GET/POST for reading/writing files
  - `/api/first` - Returns first accessible file path
  - `/api/status` - Returns sync status (total vs accessible files)

### Frontend
- **Stack:** Vanilla JS, Marked.js for markdown rendering
- **Key Files:**
  - `templates/index.html` - Main UI
  - `static/css/style.css` - Dark theme styling
  - `static/js/app.js` - All client logic

### Key Features
1. **Tree View** - Left sidebar with collapsible folders
2. **Markdown Preview** - Rendered HTML on right
3. **Edit Mode** - Raw markdown textarea, monospace font
4. **Auto-save** - 1 second debounce after typing stops
5. **Undo/Redo** - Stack-based, 50 state limit
6. **Last Opened** - Persisted in localStorage
7. **Sync Status** - Shows accessible/total file count

## Sparse Sync Handling
The vault uses Dropbox sparse sync (files exist but content not downloaded). The app handles this:
- Files that can't be read return 503 with message "File not downloaded yet"
- Status API distinguishes total_files vs accessible_files
- Tree shows all files, but opening sparse files shows error
- User must open files in Finder or use "Make available offline" to download

## Keyboard Shortcuts
- `Ctrl+Z` - Undo
- `Ctrl+Shift+Z` - Redo
- `Ctrl+S` - Force save
- `Escape` - Exit edit mode, show preview

## Common Maintenance Tasks

### Restart Server
```bash
pkill -f "vaulted/app.py"
cd ~/openclaw/vaulted && source venv/bin/activate && python app.py
```

### Reload LaunchAgent
```bash
launchctl unload ~/Library/LaunchAgents/com.openclaw.vaulted.plist
launchctl load ~/Library/LaunchAgents/com.openclaw.vaulted.plist
```

### View Logs
```bash
tail -f ~/openclaw/vaulted/vaulted.log
```

### Update Dependencies
```bash
cd ~/openclaw/vaulted
source venv/bin/activate
pip install flask  # or other packages
```

## File Structure
```
vaulted/
├── app.py                 # Flask server
├── venv/                  # Python virtual environment
├── templates/
│   └── index.html         # Main UI template
├── static/
│   ├── css/
│   │   └── style.css      # Dark theme styles
│   └── js/
│       └── app.js         # Frontend logic
├── README.md              # User documentation
├── .gitignore
└── vaulted.log            # Runtime logs
```

## Security Notes
- Path traversal protection: all paths normalized and checked against VAULT_PATH
- Only .md files shown in tree (other files ignored)
- Hidden files/dirs (starting with .) excluded from tree

## Known Issues / Limitations
1. **Sparse sync** - Files must be downloaded before editing (Dropbox limitation)
2. ~~No image support~~ - Fixed in v0.9.1
3. **No wiki-links** - Obsidian [[links]] not specially handled
4. **Single vault** - Hardcoded to one vault path

## Future Enhancements (Ideas)
- [x] Image/file attachment support (added v0.9.1)
- [ ] Obsidian wiki-link parsing
- [ ] Full-text search
- [ ] Tag browser
- [ ] Mobile-responsive improvements
- [ ] Multiple vault support

## Version History
- **v0.10.12** (2026-04-05) - LAST KNOWN GOOD - Complete rename + Wikipedia links
  - Right-click rename for files and directories in tree
  - Renamed item is highlighted and scrolled into view after operation
  - Preserve Wikipedia links in fetched pages (removed strip=['a'])

- **v0.10.11** (2026-04-05) - Fix rename error handling
  - Store paths before modal closes to prevent null reference error

- **v0.10.10** (2026-04-05) - Highlight renamed items
  - After rename, tree expands parent dirs and highlights the renamed item

- **v0.10.9** (2026-04-05) - Right-click rename feature
  - Context menu on tree nodes (right-click)
  - Rename files and directories while preserving parent path
  - Backend /api/rename endpoint with security checks

- **v0.10.8** (2026-04-05) - Infobox image preservation
  - Extract infobox images before markdown conversion (markdownify strips images in tables)
  - Images prepended to content so Wikipedia infobox photos are preserved

- **v0.10.7** (2026-04-05) - Wikipedia URL encoding fix
  - Decode URL-encoded characters (like `%27` apostrophe) in Wikipedia page titles
  - Fixes pages like "Lorenzo_de%27_Medici" that previously failed

- **v0.10.6** (2026-04-05) - Enter key in auto-file dialog
  - Press Enter in the location input field to trigger "File Here" button
  - Input auto-focused when suggestion appears

- **v0.10.5** (2026-04-05) - Tree depth + path preference + slash fix
  - Tree depth increased from 4 to 5 levels for AI context
  - Prompt prefers deeper/more specific paths (e.g., "Personal Research/Sailing" over "Sailing")
  - Strip leading slashes from user input in move_file to fix "/Path" errors

- **v0.10.4** (2026-04-05) - Ancient History rule
  - Auto-file prompt: pre-1500 AD content → "Personal Research/Ancient History"
  - Prompt encourages creating new topical categories instead of defaulting to Inbox

- **v0.10.3** (2026-04-05) - Better auto-file categorization
  - Prompt changed to suggest NEW categories when existing folders don't fit
  - Removed "default to ReadItLater Inbox" instruction
  - Added "be liberal in accepting existing folders" guidance

- **v0.10.2** (2026-04-05) - Editable auto-file + reveal in tree
  - Auto-file location is now an editable text input
  - Create custom folders by typing new paths (directories auto-created)
  - Click file path in toolbar to reveal location in tree (expands folders, scrolls to file)

- **v0.10.1** (2026-04-05) - UI polish for shortcuts
  - Improved shortcut hint visibility (lighter, bolder, more opaque)
  - Button layout adjusted to keep hints on same line
  - Added `white-space: nowrap` to prevent wrapping

- **v0.10.0** (2026-04-05) - Keyboard shortcuts and Auto-File AI
  - **Add Web Page shortcut:** `Cmd+Shift+U` with visual hint (⌘⇧U)
  - **Auto-File feature:** AI-powered document organization
    - Button: "🗂️ Auto-File" with shortcut `Cmd+Shift+F` (⌘⇧F)
    - Uses `gpt-4o-mini` for cost efficiency (~$0.00007/suggestion)
    - Compressed tree context (~450 tokens per request)
    - Modal UI: shows suggestion + reasoning, "File Here" or Cancel
    - Backend: `/api/suggest-file-location`, `/api/move-file`
  - Tree compression algorithm for AI context (folders + counts, not full file list)
  - Content truncated to 800 chars to minimize tokens

- **v0.9.1** (2026-04-04) - Image rendering support
  - Added `/api/attachment/<path>` endpoint for serving images
  - Custom marked renderer to rewrite image paths
  - Supports relative paths and Obsidian-style image references

- **v0.9** (2026-04-04) - Baseline release with vault sync support
  - Tree view, markdown editor, auto-save, undo
  - Sparse sync handling for Dropbox
  - Sync status indicator
  - 830 files in DPH Research vault
