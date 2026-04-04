#!/Users/dhinchcliffe/openclaw/vaulted/venv/bin/python3
"""
Vaulted - A minimal Obsidian vault viewer and editor
"""

import os
import json
from pathlib import Path
from flask import Flask, render_template, jsonify, request, send_from_directory

app = Flask(__name__)

# Vault path - your Obsidian vault
VAULT_PATH = os.path.expanduser("~/Dropbox/Apps/remotely-save/DPH Research")

def get_file_tree(path, relative_to=None):
    """Build a tree structure of the vault directory."""
    if relative_to is None:
        relative_to = path
    
    tree = []
    try:
        entries = sorted(os.listdir(path))
    except (OSError, PermissionError) as e:
        app.logger.warning(f"Could not list directory {path}: {e}")
        return tree
    
    for entry in entries:
        if entry.startswith('.'):
            continue
            
        full_path = os.path.join(path, entry)
        rel_path = os.path.relpath(full_path, relative_to)
        
        try:
            if os.path.isdir(full_path):
                children = get_file_tree(full_path, relative_to)
                tree.append({
                    'name': entry,
                    'path': rel_path,
                    'type': 'directory',
                    'children': children
                })
            elif entry.endswith('.md'):
                tree.append({
                    'name': entry,
                    'path': rel_path,
                    'type': 'file'
                })
        except (OSError, PermissionError) as e:
            # Skip files that can't be accessed (sparse sync)
            app.logger.debug(f"Skipping {full_path}: {e}")
            continue
    
    return tree

def find_first_markdown(path):
    """Find the first accessible markdown file in the vault."""
    try:
        for root, dirs, files in os.walk(path):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for file in sorted(files):
                if file.endswith('.md'):
                    full_path = os.path.join(root, file)
                    # Verify file is accessible (not sparse)
                    try:
                        with open(full_path, 'rb') as f:
                            f.read(1)
                        return os.path.relpath(full_path, path)
                    except (OSError, IOError):
                        continue
    except Exception:
        pass
    return None

@app.route('/')
def index():
    """Main page."""
    return render_template('index.html')

@app.route('/api/tree')
def get_tree():
    """Get the vault directory tree."""
    tree = get_file_tree(VAULT_PATH)
    return jsonify(tree)

@app.route('/api/file')
def get_file():
    """Get the contents of a markdown file."""
    filepath = request.args.get('path', '')
    if not filepath:
        return jsonify({'error': 'No path provided'}), 400
    
    # Security: ensure the path stays within the vault
    full_path = os.path.normpath(os.path.join(VAULT_PATH, filepath))
    if not full_path.startswith(os.path.normpath(VAULT_PATH)):
        return jsonify({'error': 'Invalid path'}), 403
    
    try:
        # Check if file is accessible (not sparse)
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify({'content': content, 'path': filepath})
    except FileNotFoundError:
        return jsonify({'error': 'File not found'}), 404
    except OSError as e:
        if e.errno == 11:  # EDEADLK - Resource deadlock avoided (sparse file)
            return jsonify({'error': 'File not downloaded yet. Please open in Finder to download.'}), 503
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/file', methods=['POST'])
def save_file():
    """Save changes to a markdown file."""
    data = request.get_json()
    if not data or 'path' not in data or 'content' not in data:
        return jsonify({'error': 'Missing path or content'}), 400
    
    filepath = data['path']
    content = data['content']
    
    # Security: ensure the path stays within the vault
    full_path = os.path.normpath(os.path.join(VAULT_PATH, filepath))
    if not full_path.startswith(os.path.normpath(VAULT_PATH)):
        return jsonify({'error': 'Invalid path'}), 403
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    
    try:
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/first')
def get_first():
    """Get the first markdown file path."""
    first = find_first_markdown(VAULT_PATH)
    return jsonify({'path': first})

@app.route('/api/status')
def get_status():
    """Get vault status info."""
    try:
        total_files = 0
        accessible_files = 0
        for root, dirs, files in os.walk(VAULT_PATH):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for file in files:
                if file.endswith('.md'):
                    total_files += 1
                    try:
                        full_path = os.path.join(root, file)
                        # Try to read first byte to check if file is accessible
                        with open(full_path, 'rb') as f:
                            f.read(1)
                        accessible_files += 1
                    except (OSError, PermissionError, IOError):
                        pass
        
        return jsonify({
            'vault_path': VAULT_PATH,
            'total_markdown_files': total_files,
            'accessible_files': accessible_files,
            'sync_status': 'syncing' if accessible_files < total_files else 'synced'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print(f"Vaulted starting...")
    print(f"Vault path: {VAULT_PATH}")
    print(f"Open http://localhost:5006 in your browser")
    app.run(host='0.0.0.0', port=5006, debug=True)
