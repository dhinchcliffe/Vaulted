/**
 * Vaulted - Main Application Logic
 */

let currentFile = null;
let currentContent = '';
let isEditing = false;
let saveTimeout = null;
let undoStack = [];
let undoIndex = -1;

// DOM Elements
const fileTree = document.getElementById('fileTree');
const preview = document.getElementById('preview');
const editor = document.getElementById('editor');
const currentFileLabel = document.getElementById('currentFile');
const editBtn = document.getElementById('editBtn');
const previewBtn = document.getElementById('previewBtn');
const saveStatus = document.getElementById('saveStatus');

// Initialize
async function init() {
    await loadVaultStatus();
    await loadFileTree();
    
    // Try to load last opened file from localStorage
    const lastFile = localStorage.getItem('vaulted_lastFile');
    if (lastFile) {
        await loadFile(lastFile);
    } else {
        // Load first markdown file
        await loadFirstFile();
    }
    
    setupEventListeners();
    
    // Refresh status periodically
    setInterval(loadVaultStatus, 10000);
}

// Load vault status
async function loadVaultStatus() {
    try {
        const response = await fetch('/api/status');
        const status = await response.json();
        
        const dot = document.getElementById('statusDot');
        const text = document.getElementById('statusText');
        
        if (status.sync_status === 'synced') {
            dot.className = 'status-dot synced';
            text.textContent = `${status.accessible_files} files`;
        } else {
            dot.className = 'status-dot syncing';
            text.textContent = `Syncing ${status.accessible_files}/${status.total_markdown_files}`;
        }
    } catch (error) {
        console.error('Failed to load status:', error);
    }
}

// Load file tree
async function loadFileTree() {
    try {
        const response = await fetch('/api/tree');
        const tree = await response.json();
        renderTree(tree);
    } catch (error) {
        fileTree.innerHTML = '<div class="loading">Error loading vault</div>';
        console.error('Failed to load file tree:', error);
    }
}

// Render tree recursively
function renderTree(items, container = fileTree, level = 0) {
    if (level === 0) {
        container.innerHTML = '';
    }
    
    items.forEach(item => {
        const div = document.createElement('div');
        div.className = `tree-item ${item.type}`;
        div.style.paddingLeft = `${16 + level * 12}px`;
        div.dataset.path = item.path;
        
        if (item.type === 'directory') {
            div.classList.add('expanded');
            div.innerHTML = `
                <span class="icon icon-folder"></span>
                <span>${escapeHtml(item.name)}</span>
            `;
            div.addEventListener('click', (e) => {
                e.stopPropagation();
                toggleDirectory(div, item);
            });
        } else {
            div.innerHTML = `
                <span class="icon">📝</span>
                <span>${escapeHtml(item.name)}</span>
            `;
            div.addEventListener('click', () => loadFile(item.path));
        }
        
        container.appendChild(div);
        
        if (item.type === 'directory' && item.children) {
            const childrenContainer = document.createElement('div');
            childrenContainer.className = 'tree-children';
            renderTree(item.children, childrenContainer, level + 1);
            container.appendChild(childrenContainer);
        }
    });
}

// Toggle directory expansion
function toggleDirectory(element, item) {
    element.classList.toggle('collapsed');
    element.classList.toggle('expanded');
    const childrenContainer = element.nextElementSibling;
    if (childrenContainer) {
        childrenContainer.style.display = element.classList.contains('collapsed') ? 'none' : 'block';
    }
}

// Load first markdown file
async function loadFirstFile() {
    try {
        const response = await fetch('/api/first');
        const data = await response.json();
        if (data.path) {
            await loadFile(data.path);
        } else {
            preview.innerHTML = '<div class="empty-state">No markdown files found</div>';
        }
    } catch (error) {
        console.error('Failed to load first file:', error);
    }
}

// Load a file
async function loadFile(path) {
    try {
        const response = await fetch(`/api/file?path=${encodeURIComponent(path)}`);
        const data = await response.json();
        
        if (data.error) {
            console.error('Error loading file:', data.error);
            return;
        }
        
        currentFile = path;
        currentContent = data.content;
        
        // Update UI
        currentFileLabel.textContent = path;
        editor.value = currentContent;
        renderPreview(currentContent);
        
        // Save to localStorage
        localStorage.setItem('vaulted_lastFile', path);
        
        // Highlight in tree
        document.querySelectorAll('.tree-item').forEach(el => el.classList.remove('active'));
        const treeItem = document.querySelector(`.tree-item[data-path="${CSS.escape(path)}"]`);
        if (treeItem) {
            treeItem.classList.add('active');
        }
        
        // Reset undo stack
        undoStack = [currentContent];
        undoIndex = 0;
        
        // Show edit button
        editBtn.style.display = 'inline-block';
        previewBtn.style.display = 'none';
        isEditing = false;
        updateView();
        
    } catch (error) {
        console.error('Failed to load file:', error);
    }
}

// Render markdown preview
function renderPreview(content) {
    // Get the base path for the current file (for standard markdown images)
    const vaultBase = currentFile ? currentFile.substring(0, currentFile.lastIndexOf('/') + 1) : '';
    
    // Pre-process Obsidian wiki-link style images: ![[image.png]] -> <img> tag directly
    // Wiki-links try multiple locations: explicit path -> local folder -> vault root
    const currentFileForContext = currentFile || '';
    let processedContent = content.replace(
        /!\[\[([^\]]+)\]\]/g,
        (match, imagePath) => {
            let fullPath = imagePath;
            if (!imagePath.match(/^https?:\/\//)) {
                // Remove leading ./ if present
                if (imagePath.startsWith('./')) {
                    imagePath = imagePath.substring(2);
                }
                // Pass current file context so backend can try local folder
                const fromParam = currentFileForContext ? `?from=${encodeURIComponent(currentFileForContext)}` : '';
                fullPath = '/api/attachment/' + encodeURIComponent(imagePath) + fromParam;
            }
            return `<img src="${fullPath}" alt="${imagePath}" style="max-width: 100%;">`;
        }
    );
    
    // Custom renderer for standard markdown images
    const renderer = new marked.Renderer();
    renderer.image = ({ href, title, text }) => {
        // If href is a relative path (not URL), rewrite it to use our attachment endpoint
        if (href && !href.match(/^https?:\/\//)) {
            let imagePath = href;
            if (imagePath.startsWith('./')) {
                imagePath = imagePath.substring(2);
            }
            if (!imagePath.startsWith('/')) {
                imagePath = vaultBase + imagePath;
            }
            href = '/api/attachment/' + encodeURIComponent(imagePath);
        }
        // External URLs (https://) pass through unchanged
        const titleAttr = title ? ` title="${title}"` : '';
        return `<img src="${href}" alt="${text}"${titleAttr} style="max-width: 100%;">`;
    };
    
    preview.innerHTML = marked.parse(processedContent, { renderer, mangle: false, headerIds: false });
}

// Update view based on editing state
function updateView() {
    if (isEditing) {
        preview.style.display = 'none';
        editor.style.display = 'block';
        editBtn.style.display = 'none';
        previewBtn.style.display = 'inline-block';
        editor.focus();
    } else {
        preview.style.display = 'block';
        editor.style.display = 'none';
        editBtn.style.display = 'inline-block';
        previewBtn.style.display = 'none';
    }
}

// Auto-save functionality
function queueSave() {
    saveStatus.textContent = 'Saving...';
    saveStatus.className = 'save-status saving';
    
    clearTimeout(saveTimeout);
    saveTimeout = setTimeout(() => {
        saveFile();
    }, 1000);
}

// Save file to server
async function saveFile() {
    if (!currentFile) return;
    
    try {
        const response = await fetch('/api/file', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                path: currentFile,
                content: editor.value
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            currentContent = editor.value;
            saveStatus.textContent = 'Saved';
            saveStatus.className = 'save-status saved';
            setTimeout(() => {
                saveStatus.textContent = '';
            }, 2000);
        } else {
            saveStatus.textContent = 'Error';
            console.error('Save failed:', data.error);
        }
    } catch (error) {
        saveStatus.textContent = 'Error';
        console.error('Failed to save:', error);
    }
}

// Push to undo stack
function pushUndo(content) {
    // Remove any redo states
    undoStack = undoStack.slice(0, undoIndex + 1);
    undoStack.push(content);
    undoIndex++;
    
    // Limit stack size
    if (undoStack.length > 50) {
        undoStack.shift();
        undoIndex--;
    }
}

// Undo
function undo() {
    if (undoIndex > 0) {
        undoIndex--;
        editor.value = undoStack[undoIndex];
        queueSave();
    }
}

// Redo
function redo() {
    if (undoIndex < undoStack.length - 1) {
        undoIndex++;
        editor.value = undoStack[undoIndex];
        queueSave();
    }
}

// Setup event listeners
function setupEventListeners() {
    // Add Web Page button
    const addWebBtn = document.getElementById('addWebBtn');
    if (addWebBtn) {
        addWebBtn.addEventListener('click', addWebPage);
    }
    
    // Edit/Preview buttons
    editBtn.addEventListener('click', () => {
        isEditing = true;
        updateView();
    });
    
    previewBtn.addEventListener('click', () => {
        isEditing = false;
        renderPreview(editor.value);
        updateView();
    });
    
    // Editor input
    editor.addEventListener('input', () => {
        pushUndo(editor.value);
        queueSave();
    });
    
    // Keyboard shortcuts
    editor.addEventListener('keydown', (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === 'z') {
            e.preventDefault();
            if (e.shiftKey) {
                redo();
            } else {
                undo();
            }
        }
        
        if ((e.metaKey || e.ctrlKey) && e.key === 's') {
            e.preventDefault();
            clearTimeout(saveTimeout);
            saveFile();
        }
        
        if (e.key === 'Escape') {
            isEditing = false;
            renderPreview(editor.value);
            updateView();
        }
    });
}

// Add web page by URL
async function addWebPage() {
    const url = prompt('Enter URL to fetch:');
    if (!url || !url.trim()) return;
    
    const btn = document.getElementById('addWebBtn');
    const originalText = btn.textContent;
    btn.textContent = 'Fetching...';
    btn.disabled = true;
    
    try {
        const response = await fetch('/api/fetch-web', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: url.trim() })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Refresh file tree to show new file
            await loadFileTree();
            // Load the new file
            await loadFile(data.path);
            // Show success
            saveStatus.textContent = `Saved: ${data.title}`;
            saveStatus.className = 'save-status saved';
            setTimeout(() => { saveStatus.textContent = ''; }, 3000);
        } else {
            alert('Error: ' + (data.error || 'Failed to fetch page'));
        }
    } catch (error) {
        console.error('Failed to fetch web page:', error);
        alert('Error: Failed to fetch page. Check console for details.');
    } finally {
        btn.textContent = originalText;
        btn.disabled = false;
    }
}

// Utility: Escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Start
init();
