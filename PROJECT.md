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
2. **No image support** - Markdown images not handled (would need file serving)
3. **No wiki-links** - Obsidian [[links]] not specially handled
4. **Single vault** - Hardcoded to one vault path

## Future Enhancements (Ideas)
- [ ] Image/file attachment support
- [ ] Obsidian wiki-link parsing
- [ ] Full-text search
- [ ] Tag browser
- [ ] Mobile-responsive improvements
- [ ] Multiple vault support

## Version History
- **v0.9** (2026-04-04) - Baseline release with vault sync support
  - Tree view, markdown editor, auto-save, undo
  - Sparse sync handling for Dropbox
  - Sync status indicator
  - 830 files in DPH Research vault
