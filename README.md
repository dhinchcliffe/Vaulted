# Vaulted

A minimal, elegant web-based viewer and editor for Obsidian vaults.

## Features

- **Tree View**: Browse your vault's directory structure on the left
- **Markdown Editor**: View and edit markdown files on the right
- **Auto-save**: Changes are saved automatically
- **Undo Support**: Ctrl+Z to undo changes
- **Last Opened**: Remembers which file you were editing

## Setup

1. Install dependencies:
   ```bash
   pip install flask
   ```

2. Run the app:
   ```bash
   python app.py
   ```

3. Open http://localhost:5005 in your browser

## Configuration

The vault path is configured in `app.py`:
```python
VAULT_PATH = os.path.expanduser("~/Dropbox/Apps/remotely_save/DPH Research")
```

## Auto-start

The app includes a LaunchAgent for macOS auto-start:
```bash
# Load the LaunchAgent
launchctl load ~/Library/LaunchAgents/com.openclaw.vaulted.plist
```
