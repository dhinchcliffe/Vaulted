/**
 * Vaulted - Main Application Logic
 */

let currentFile = null;
let currentRevision = null;
let saveInFlight = null;
let switchingFile = false;
let currentContent = '';
let isEditing = false;
let saveTimeout = null;
let undoStack = [];
let undoIndex = -1;

// Same-origin API writes and expired-session handling.
const originalFetch = window.fetch.bind(window);
window.fetch = async (url, options = {}) => {
    options.headers = { ...options.headers, 'X-Vaulted-Request': '1' };
    const response = await originalFetch(url, options);
    if (response.status === 401) {
        saveStatus.textContent = 'Session expired. Copy any unsaved text, then sign in again.';
    }
    return response;
};
window.addEventListener('beforeunload', event => {
    if (currentFile && editor.value !== currentContent) { event.preventDefault(); event.returnValue = ''; }
});
// DOM Elements
const physicalTree = document.getElementById('physicalTree');
const recentPages = document.getElementById('recentPages');
const recentPageList = document.getElementById('recentPageList');
const pagePaths = new Map();
const recentLimit = 100;
const recentKey = 'vaulted_recentPageIds';
const preview = document.getElementById('preview');
const editor = document.getElementById('editor');
const currentFileLabel = document.getElementById('currentFile');
const editBtn = document.getElementById('editBtn');
const previewBtn = document.getElementById('previewBtn');
const saveStatus = document.getElementById('saveStatus');
const imageMigration = window.VaultedImageMigration.create({
    banner: document.getElementById('imageMigrationBanner'),
    message: document.getElementById('imageMigrationMessage'),
    migrate: document.getElementById('migrateImagesBtn'),
    dismiss: document.getElementById('dismissImageMigrationBtn'),
    getState: () => ({path: currentFile, revision: currentRevision, dirty: editor.value !== currentContent}),
    save: () => saveFile(),
    apply: data => {
        currentContent = data.content; currentRevision = data.revision;
        editor.value = data.content; pushUndo(data.content); renderPreview(data.content);
        saveStatus.textContent = 'Images saved'; saveStatus.className = 'save-status saved';
    },
    lock: busy => { editor.readOnly = busy; editBtn.disabled = busy; }
});


// Keep the ordinary vault available while a cached shell or optional phone asset catches up.
const phoneLayout = document.getElementById('browseBtn') && window.createPhoneLayout?.({
    readPreference, writePreference, openSearch, openTreeMenu,
    refreshTitle: () => displayCurrentPath(currentFile)
});
currentFileLabel.style.cursor = 'pointer';
currentFileLabel.title = 'Click to reveal in tree';
currentFileLabel.addEventListener('click', revealCurrentFileInTree);

function displayCurrentPath(path) {
    if (path) currentFileLabel.textContent = document.body.classList.contains('phone-layout')
        ? path.slice(path.lastIndexOf('/') + 1) : path;
}

// Browser preferences are optional. The editor also works when storage is unavailable.
function readPreference(key) {
    try { return localStorage.getItem(key); } catch { return null; }
}

function writePreference(key, value) {
    try { localStorage.setItem(key, value); } catch { /* Keep using the in-memory state. */ }
}

function readRecentIds() {
    try {
        const ids = JSON.parse(readPreference(recentKey));
        return Array.isArray(ids) ? [...new Set(ids.filter(id => typeof id === 'string'))].slice(0, recentLimit) : [];
    } catch { return []; }
}

let recentIds = readRecentIds();
recentPages.open = readPreference('vaulted_recentCollapsed') !== 'true';
recentPages.addEventListener('toggle', () => writePreference('vaulted_recentCollapsed', String(!recentPages.open)));
window.addEventListener('storage', event => {
    if (event.key === recentKey || event.key === null) {
        recentIds = readRecentIds();
        renderRecentPages();
    }
});

function renderRecentPages() {
    const focusedId = document.activeElement?.dataset.recentId;
    const fragment = document.createDocumentFragment();
    const pages = recentIds.filter(id => pagePaths.has(id));
    const names = pages.map(id => pagePaths.get(id).split('/').pop());
    pages.forEach((id, index) => {
        const path = pagePaths.get(id);
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'tree-item recent-page';
        button.dataset.recentId = id;
        button.title = path;
        if (path === currentFile) {
            button.classList.add('active');
            button.setAttribute('aria-current', 'page');
        }
        const icon = document.createElement('span');
        icon.className = 'icon';
        icon.setAttribute('aria-hidden', 'true');
        icon.textContent = '📝';
        const name = names[index];
        button.append(icon, names.indexOf(name) === names.lastIndexOf(name) ? name : path);
        button.addEventListener('click', () => loadFile(path, id));
        fragment.append(button);
    });
    if (!pages.length) {
        const empty = document.createElement('div');
        empty.className = 'recent-empty';
        empty.textContent = 'No recent pages';
        fragment.append(empty);
    }
    recentPageList.replaceChildren(fragment);
    if (focusedId) recentPageList.querySelector(`[data-recent-id="${CSS.escape(focusedId)}"]`)?.focus({preventScroll: true});
}

// Initialize
async function init() {
    await loadVaultStatus();
    await loadFileTree();
    
    // Try to load last opened file from localStorage
    const capturePath = document.body.dataset.capturePath;
    const lastFile = readPreference('vaulted_lastFile');
    if (capturePath) {
        await loadFile(capturePath);
    } else if (lastFile) {
        const lastRow = physicalTree.querySelector(`.file[data-path="${CSS.escape(lastFile)}"]`);
        // A rename in another session or a repaired filename can stale the saved path.
        await loadFile(lastRow ? lastFile : pagePaths.get(recentIds[0]) || lastFile);
    } else {
        // Load first markdown file
        await loadFirstFile();
    }
    
    setupEventListeners();
    if (capturePath && currentFile === capturePath) {
        await autoFileDocument();
    }
    
    // Refresh status periodically
    setInterval(loadVaultStatus, 60000);
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
        if (!response.ok || !Array.isArray(tree)) throw new Error('Invalid tree response');
        pagePaths.clear();
        renderTree(tree, physicalTree);
        renderRecentPages();
    } catch (error) {
        physicalTree.innerHTML = '<div class="loading">Error loading vault</div>';
        console.error('Failed to load file tree:', error);
    }
}

// Render tree recursively
function renderTree(items, container, level = 0, savedExpanded = null) {
    if (level === 0) {
        container.innerHTML = '';
        // Get saved expanded state at root level and pass it down
        savedExpanded = getSavedTreeState();
    }
    
    items.forEach(item => {
        const div = document.createElement('div');
        div.className = `tree-item ${item.type}`;
        div.style.paddingLeft = `${16 + level * 12}px`;
        div.dataset.path = item.path;
        
        if (item.type === 'directory') {
            // Check if we have saved state for this directory
            const isExpanded = savedExpanded ? savedExpanded.includes(item.path) : true;
            div.classList.add(isExpanded ? 'expanded' : 'collapsed');
            div.innerHTML = `
                <span class="icon icon-folder"></span>
                <span>${escapeHtml(item.name)}</span>
            `;
            div.addEventListener('click', (e) => {
                e.stopPropagation();
                toggleDirectory(div, item);
            });
            setupTreeItemContextMenu(div, item.path, 'directory');
        } else {
            if (item.id) pagePaths.set(item.id, item.path);
            div.classList.toggle('active', item.path === currentFile);
            div.innerHTML = `
                <span class="icon">📝</span>
                <span>${escapeHtml(item.name)}</span>
            `;
            div.addEventListener('click', () => loadFile(item.path));
            setupTreeItemContextMenu(div, item.path, 'file');
        }
        
        phoneLayout?.addNodeAction(div);
        container.appendChild(div);
        
        if (item.type === 'directory' && item.children) {
            const childrenContainer = document.createElement('div');
            childrenContainer.className = 'tree-children';
            // Hide children if directory is collapsed
            if (div.classList.contains('collapsed')) {
                childrenContainer.style.display = 'none';
            }
            renderTree(item.children, childrenContainer, level + 1, savedExpanded);
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
    // Save tree state after toggle
    saveTreeState();
}

// Save expanded/collapsed state of all directories to localStorage
function saveTreeState() {
    const expandedPaths = [];
    document.querySelectorAll('.tree-item.directory.expanded').forEach(el => {
        expandedPaths.push(el.dataset.path);
    });
    writePreference('vaulted_expandedPaths', JSON.stringify(expandedPaths));
}

// Get saved tree state from localStorage
function getSavedTreeState() {
    try {
        return JSON.parse(readPreference('vaulted_expandedPaths') || '[]');
    } catch (e) {
        return [];
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
async function loadFile(path, recentId = null) {
    if (switchingFile) return;
    switchingFile = true;
    clearTimeout(saveTimeout);
    try {
        if (currentFile && editor.value !== currentContent && !await saveFile()) {
            phoneLayout?.navigationError(saveStatus.textContent);
            return;
        }
        const query = recentId ? {id: recentId} : {path};
        const response = await fetch('/api/file?' + new URLSearchParams(query));
        const data = await response.json();
        
        if (!response.ok || data.error) {
            if (recentId && response.status === 404) {
                pagePaths.delete(recentId);
                renderRecentPages();
            }
            saveStatus.textContent = data.error;
            phoneLayout?.navigationError(data.error);
            console.error('Error loading file:', data.error);
            return;
        }
        
        const pathChanged = recentId && path !== data.path;
        path = data.path;
        currentFile = path;
        currentContent = data.content;
        currentRevision = data.revision;
        
        // Update UI
        displayCurrentPath(path);
        editor.value = currentContent;
        renderPreview(currentContent);
        
        // Save to localStorage
        writePreference('vaulted_lastFile', path);
        
        // Highlight in tree
        physicalTree.querySelector('.tree-item.active')?.classList.remove('active');
        const treeItem = physicalTree.querySelector(`.tree-item.file[data-path="${CSS.escape(path)}"]`);
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
        imageMigration.show(data.external_image_count || 0);
        if (data.id) {
            pagePaths.set(data.id, path);
            if (recentIds[0] !== data.id) {
                recentIds = [data.id, ...recentIds.filter(id => id !== data.id)].slice(0, recentLimit);
                writePreference(recentKey, JSON.stringify(recentIds));
            }
            renderRecentPages();
        }
        if (recentId) {
            if (pathChanged || !treeItem) await loadFileTree();
            highlightTreeItem(path, {focus: true});
        } else {
            phoneLayout?.closeDrawer();
        }
        
    } catch (error) {
        phoneLayout?.navigationError('Could not open the page. Try again.');
        console.error('Failed to load file:', error);
    } finally { switchingFile = false; }
}

// Render markdown preview
function renderPreview(content) {
    // Get the base path for the current file (for standard markdown images)
    const vaultBase = currentFile ? currentFile.substring(0, currentFile.lastIndexOf('/') + 1) : '';
    
    // Parse YAML frontmatter to extract source_url for external pages
    let sourceUrl = null;
    let sourceOrigin = null;
    const frontmatterMatch = content.match(/^---\s*\n([\s\S]*?)\n---\s*\n/);
    if (frontmatterMatch) {
        const sourceUrlMatch = frontmatterMatch[1].match(/^source_url:\s*(.+)$/m);
        if (sourceUrlMatch) {
            sourceUrl = sourceUrlMatch[1].trim();
            try {
                sourceOrigin = new URL(sourceUrl).origin;
            } catch (e) {
                // Invalid URL, ignore
            }
        }
    }
    
    // Fallback: parse "Saved from" line for older pages without YAML frontmatter
    if (!sourceOrigin) {
        const savedFromMatch = content.match(/\*Saved from\s+(https?:\/\/[^\s]+)\s+on/i);
        if (savedFromMatch) {
            sourceUrl = savedFromMatch[1].trim();
            try {
                sourceOrigin = new URL(sourceUrl).origin;
            } catch (e) {
                // Invalid URL, ignore
            }
        }
    }
    
    // Pre-process Obsidian wiki-link style images: ![[image.png]] -> <img> tag directly
    // Wiki-links try multiple locations: explicit path -> local folder -> vault root
    const currentFileForContext = currentFile || '';
    let processedContent = content.replace(
        /!\[\[([^\]]+)\]\]/g,
        (match, imagePath) => {
            imagePath = imagePath.split('|')[0];
            let fullPath = imagePath;
            if (!imagePath.match(/^https?:\/\//)) {
                // Remove leading ./ if present
                if (imagePath.startsWith('./')) {
                    imagePath = imagePath.substring(2);
                }
                // Pass current file context so backend can try local folder
                const fromParam = currentFileForContext ? `&from=${encodeURIComponent(currentFileForContext)}` : '';
                fullPath = '/api/attachment?path=' + encodeURIComponent(imagePath) + fromParam;
            }
            return `<img src="${escapeHtml(fullPath)}" alt="${escapeHtml(imagePath)}" style="max-width: 100%;">`;
        }
    );
    
    // Custom renderer for standard markdown images
    const renderer = new marked.Renderer();
    renderer.image = (href, title, text) => {
        // Handle protocol-relative URLs (//example.com/image.jpg -> https://example.com/image.jpg)
        if (href && href.startsWith('/Attachments/Web/')) {
            href = '/api/attachment?path=' + encodeURIComponent(href.substring(1));
        }
        else if (href && href.startsWith('//')) {
            href = 'https:' + href;
        }
        // Root-relative URLs (starting with /) - convert to absolute using source URL if available
        else if (href && href.startsWith('/') && sourceOrigin) {
            href = sourceOrigin + href;
        }
        // If href is a relative path (not URL), rewrite it to use our attachment endpoint
        else if (href && !href.match(/^https?:\/\//)) {
            let imagePath = href;
            if (imagePath.startsWith('./')) {
                imagePath = imagePath.substring(2);
            }
            if (!imagePath.startsWith('/')) {
                imagePath = vaultBase + imagePath;
            }
            href = '/api/attachment?path=' + encodeURIComponent(imagePath);
        }
        // External URLs (https://) pass through unchanged
        const titleAttr = title ? ` title="${escapeHtml(title)}"` : '';
        return `<img src="${escapeHtml(href || "")}" alt="${escapeHtml(text || "")}"${titleAttr} style="max-width: 100%;">`;
    };
    
    preview.innerHTML = DOMPurify.sanitize(marked.parse(processedContent, { renderer, mangle: false, headerIds: false }));
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
    if (imageMigration.isBusy(currentFile)) return;
    saveStatus.textContent = 'Saving...';
    saveStatus.className = 'save-status saving';
    
    clearTimeout(saveTimeout);
    saveTimeout = setTimeout(() => {
        saveFile();
    }, 1000);
}

// Save file to server
async function saveFile() {
    if (imageMigration.isBusy(currentFile)) return false;
    if (saveInFlight) { await saveInFlight; if (editor.value === currentContent) return true; }
    if (!currentFile || editor.value === currentContent) return true;
    const path = currentFile, content = editor.value, revision = currentRevision;
    saveInFlight = (async () => {
        try {
            const response = await fetch('/api/file', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({path,content,revision}) });
            const data = await response.json();
            if (!response.ok || !data.success) throw new Error(data.error || 'Save failed');
            if (currentFile === path) {
                currentContent = content; currentRevision = data.revision;
                imageMigration.show(data.external_image_count || 0);
            }
            saveStatus.textContent = 'Saved'; saveStatus.className = 'save-status saved';
            return true;
        } catch (error) {
            saveStatus.textContent = error.message + ' Your edits remain in the editor.';
            saveStatus.className = 'save-status error';
            return false;
        }
    })();
    const ok = await saveInFlight; saveInFlight = null;
    if (ok && editor.value !== currentContent) return saveFile();
    return ok;
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
    if (imageMigration.isBusy(currentFile)) return;
    if (undoIndex > 0) {
        undoIndex--;
        editor.value = undoStack[undoIndex];
        queueSave();
    }
}

// Redo
function redo() {
    if (imageMigration.isBusy(currentFile)) return;
    if (undoIndex < undoStack.length - 1) {
        undoIndex++;
        editor.value = undoStack[undoIndex];
        queueSave();
    }
}

// Setup event listeners
function setupEventListeners() {
    // Search button
    const searchBtn = document.getElementById('searchBtn');
    if (searchBtn) {
        searchBtn.addEventListener('click', openSearch);
    }

    // Search close button
    const searchCloseBtn = document.getElementById('searchCloseBtn');
    if (searchCloseBtn) {
        searchCloseBtn.addEventListener('click', closeSearch);
    }

    // Search input
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('input', debounce(performSearch, 300));
        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                closeSearch();
            }
        });
    }

    // Quick Paste button
    const quickPasteBtn = document.getElementById('quickPasteBtn');
    if (quickPasteBtn) {
        quickPasteBtn.addEventListener('click', quickPaste);
    }

    // Add Web Page button
    const addWebBtn = document.getElementById('addWebBtn');
    if (addWebBtn) {
        addWebBtn.addEventListener('click', addWebPage);
    }

    // Global keyboard shortcuts (not just in editor)
    document.addEventListener('keydown', (e) => {
        // Cmd/Ctrl + Shift + S for Search
        if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === 's') {
            e.preventDefault();
            openSearch();
        }
        // Cmd/Ctrl + Shift + V for Quick Paste
        if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === 'v') {
            e.preventDefault();
            quickPaste();
        }
        // Cmd/Ctrl + Shift + U for Add Web Page
        if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === 'u') {
            e.preventDefault();
            addWebPage();
        }
        // Cmd/Ctrl + Shift + F for Auto-File
        if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === 'f') {
            e.preventDefault();
            autoFileDocument();
        }
    });
    
    // Auto-File button
    const autoFileBtn = document.getElementById('autoFileBtn');
    if (autoFileBtn) {
        autoFileBtn.addEventListener('click', autoFileDocument);
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
        if (imageMigration.isBusy(currentFile)) return;
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

// Quick Paste Modal Functions
function openQuickPasteModal() {
    const modal = document.getElementById('quickPasteModal');
    const pasteArea = document.getElementById('quickPasteArea');

    modal.style.display = 'flex';
    pasteArea.innerHTML = '';
    pasteArea.focus();

    // Try to auto-paste from clipboard if API is available
    if (navigator.clipboard && navigator.clipboard.read) {
        navigator.clipboard.read().then(clipboardItems => {
            for (const item of clipboardItems) {
                if (item.types.includes('text/html')) {
                    item.getType('text/html').then(blob => {
                        blob.text().then(html => {
                            pasteArea.innerHTML = DOMPurify.sanitize(html);
                        });
                    });
                    return;
                } else if (item.types.includes('text/plain')) {
                    item.getType('text/plain').then(blob => {
                        blob.text().then(text => {
                            pasteArea.textContent = text;
                        });
                    });
                    return;
                }
            }
        }).catch(err => {
            console.log('Auto-paste failed, waiting for manual paste:', err);
        });
    }
}

function closeQuickPasteModal() {
    const modal = document.getElementById('quickPasteModal');
    modal.style.display = 'none';
}

async function confirmQuickPaste() {
    const pasteArea = document.getElementById('quickPasteArea');
    const btn = document.getElementById('confirmQuickPasteBtn');

    const htmlContent = pasteArea.innerHTML;
    const textContent = pasteArea.textContent;

    if (!textContent || !textContent.trim()) {
        closeQuickPasteModal();
        return;
    }

    btn.textContent = 'Creating...';
    btn.disabled = true;

    try {
        // Check if there's actual HTML formatting or just plain text
        const hasRealHtml = htmlContent !== textContent && htmlContent.includes('<');
        await sendQuickPaste(hasRealHtml ? htmlContent : textContent, hasRealHtml);
        closeQuickPasteModal();
    } catch (error) {
        console.error('Quick paste failed:', error);
        alert('Error: Failed to paste. Check console for details.');
    } finally {
        btn.textContent = 'Create Page';
        btn.disabled = false;
    }
}

// Quick paste from clipboard
async function quickPaste() {
    openQuickPasteModal();
}

async function sendQuickPaste(content, isHtml) {
    const response = await fetch('/api/quick-paste', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            content: content,
            is_html: isHtml
        })
    });

    const data = await response.json();

    if (data.success) {
        // Refresh file tree to show new file
        await loadFileTree();
        // Load the new file
        await loadFile(data.path);
        // Show success
        saveStatus.textContent = `Pasted: ${data.title}`;
        saveStatus.className = 'save-status saved';
        setTimeout(() => { saveStatus.textContent = ''; }, 3000);
    } else {
        alert('Error: ' + (data.error || 'Failed to paste'));
    }
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
    return div.innerHTML.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// Auto-File Modal Functions
function openAutoFileModal() {
    const modal = document.getElementById('autoFileModal');
    const loading = document.getElementById('autoFileLoading');
    const result = document.getElementById('autoFileResult');
    const error = document.getElementById('autoFileError');
    
    modal.style.display = 'flex';
    loading.style.display = 'block';
    result.style.display = 'none';
    error.style.display = 'none';
}

function closeAutoFileModal() {
    const modal = document.getElementById('autoFileModal');
    modal.style.display = 'none';
}

function showAutoFileResult(suggestion, reasoning) {
    const loading = document.getElementById('autoFileLoading');
    const result = document.getElementById('autoFileResult');
    const suggestionInput = document.getElementById('autoFileSuggestionInput');
    const reasoningEl = document.getElementById('autoFileReasoning');
    const confirmBtn = document.getElementById('confirmFileBtn');

    loading.style.display = 'none';
    result.style.display = 'block';

    suggestionInput.value = suggestion;
    reasoningEl.textContent = reasoning;

    // Setup confirm button - reads from input to allow editing
    confirmBtn.onclick = () => {
        const editedLocation = suggestionInput.value.trim();
        if (editedLocation) {
            confirmAutoFile(editedLocation);
        }
    };

    // Allow Enter key to trigger filing
    suggestionInput.onkeydown = (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            confirmBtn.click();
        }
    };
    suggestionInput.focus();
}

function showAutoFileError(message) {
    const loading = document.getElementById('autoFileLoading');
    const error = document.getElementById('autoFileError');
    const errorMsg = document.getElementById('autoFileErrorMsg');
    
    loading.style.display = 'none';
    error.style.display = 'block';
    errorMsg.textContent = message;
}

let pendingAutoFileSuggestion = null;

async function autoFileDocument() {
    if (!currentFile) {
        alert('No file is currently open');
        return;
    }
    
    openAutoFileModal();
    pendingAutoFileSuggestion = null;
    
    try {
        const response = await fetch('/api/suggest-file-location', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                path: currentFile,
                content: editor.value
            })
        });
        
        const data = await response.json();
        
        if (data.error) {
            showAutoFileError(data.error);
        } else {
            pendingAutoFileSuggestion = data.suggestion;
            showAutoFileResult(data.suggestion, data.reasoning);
        }
    } catch (error) {
        console.error('Auto-file failed:', error);
        showAutoFileError('Failed to get suggestion. Check console for details.');
    }
}

async function confirmAutoFile(targetFolder) {
    if (!await saveFile()) return;
    if (!currentFile || !targetFolder) return;
    
    const confirmBtn = document.getElementById('confirmFileBtn');
    confirmBtn.textContent = 'Moving...';
    confirmBtn.disabled = true;
    
    try {
        const response = await fetch('/api/move-file', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                from_path: currentFile,
                to_folder: targetFolder
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            closeAutoFileModal();
            // Refresh tree and load file at new location
            await loadFileTree();
            await loadFile(data.new_path);
            // Show success
            saveStatus.textContent = `Moved to ${targetFolder}`;
            saveStatus.className = 'save-status saved';
            setTimeout(() => { saveStatus.textContent = ''; }, 3000);
        } else {
            showAutoFileError(data.error || 'Failed to move file');
        }
    } catch (error) {
        console.error('Move failed:', error);
        showAutoFileError('Failed to move file. Check console for details.');
    } finally {
        confirmBtn.textContent = '📁 File Here';
        confirmBtn.disabled = false;
    }
}

// Close modal on backdrop click
document.addEventListener('click', (e) => {
    const autoFileModal = document.getElementById('autoFileModal');
    if (e.target === autoFileModal) {
        closeAutoFileModal();
    }
    const quickPasteModal = document.getElementById('quickPasteModal');
    if (e.target === quickPasteModal) {
        closeQuickPasteModal();
    }
    // Close context menu when clicking elsewhere
    const contextMenu = document.getElementById('contextMenu');
    if (contextMenu && !contextMenu.contains(e.target)) {
        contextMenu.style.display = 'none';
    }
});

// Highlight a tree item and scroll it into view
function highlightTreeItem(path, {focus = false} = {}) {
    // Expand parent directories
    const pathParts = path.split('/');
    pathParts.pop(); // Remove the item itself, keep parent dirs

    let currentPath = '';
    for (const part of pathParts) {
        currentPath = currentPath ? `${currentPath}/${part}` : part;
        const dirEl = physicalTree.querySelector(`.tree-item.directory[data-path="${CSS.escape(currentPath)}"]`);
        if (dirEl && dirEl.classList.contains('collapsed')) {
            dirEl.classList.remove('collapsed');
            dirEl.classList.add('expanded');
            const childrenContainer = dirEl.nextElementSibling;
            if (childrenContainer) {
                childrenContainer.style.display = 'block';
            }
        }
    }
    saveTreeState();

    // Find and highlight the item
    const itemEl = physicalTree.querySelector(`.tree-item[data-path="${CSS.escape(path)}"]`);
    if (itemEl) {
        if (focus) {
            // The loaded file already has the persistent active highlight.
            itemEl.tabIndex = -1;
            itemEl.focus({preventScroll: true});
            itemEl.scrollIntoView({block: 'center', inline: 'nearest'});
            return;
        }
        itemEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
        // Flash highlight effect
        itemEl.style.transition = 'background 0.3s';
        const originalBg = itemEl.style.background;
        itemEl.style.background = '#0e639c';
        setTimeout(() => {
            itemEl.style.background = originalBg;
        }, 1500);
    }
}

// Reveal current file in tree view
function revealCurrentFileInTree() {
    if (!currentFile) return;
    phoneLayout?.openDrawer();
    if (document.body.classList.contains('phone-layout') && isSearchActive) {
        closeSearch(); // Reveals and scrolls to the physical tree item.
        return;
    }

    // Get all path components except the filename
    const pathParts = currentFile.split('/');
    pathParts.pop(); // Remove filename, keep directories

    // Expand each directory in the path
    let currentPath = '';
    for (const part of pathParts) {
        currentPath = currentPath ? `${currentPath}/${part}` : part;
        const dirEl = document.querySelector(`.tree-item.directory[data-path="${CSS.escape(currentPath)}"]`);
        if (dirEl && dirEl.classList.contains('collapsed')) {
            dirEl.classList.remove('collapsed');
            dirEl.classList.add('expanded');
            const childrenContainer = dirEl.nextElementSibling;
            if (childrenContainer) {
                childrenContainer.style.display = 'block';
            }
        }
    }

    // Save expanded state
    saveTreeState();

    // Scroll the file into view
    const fileEl = document.querySelector(`.tree-item[data-path="${CSS.escape(currentFile)}"]`);
    if (fileEl) {
        fileEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
        // Flash highlight effect
        fileEl.style.transition = 'background 0.3s';
        const originalBg = fileEl.style.background;
        fileEl.style.background = '#0e639c';
        setTimeout(() => {
            fileEl.style.background = originalBg;
        }, 800);
    }
}

// Context menu state
let contextMenuTarget = null;

// Show context menu
function openTreeMenu(path, type, x, y) {
    contextMenuTarget = { path, type };

    const menu = document.getElementById('contextMenu');
    const addPageItem = document.getElementById('contextAddPage');

    // Show/hide Add Page based on type (only for directories)
    if (type === 'directory') {
        addPageItem.style.display = 'block';
    } else {
        addPageItem.style.display = 'none';
    }

    menu.style.display = 'block';
    menu.style.left = `${x}px`;
    menu.style.top = `${y}px`;

    // Ensure menu stays within viewport
    const rect = menu.getBoundingClientRect();
    if (rect.right > window.innerWidth) {
        menu.style.left = `${Math.max(0, x - rect.width)}px`;
    }
    if (rect.bottom > window.innerHeight) {
        menu.style.top = `${Math.max(0, y - rect.height)}px`;
    }
}

// Setup context menu on tree items
function setupTreeItemContextMenu(element, path, type) {
    element.addEventListener('contextmenu', event => {
        event.preventDefault();
        event.stopPropagation();
        openTreeMenu(path, type, event.clientX, event.clientY);
    });
}

// Rename modal functions
function openRenameModal() {
    const modal = document.getElementById('renameModal');
    const input = document.getElementById('renameInput');
    const menu = document.getElementById('contextMenu');

    menu.style.display = 'none';
    modal.style.display = 'flex';

    // Set current name as default
    const name = contextMenuTarget.path.split('/').pop();
    input.value = contextMenuTarget.type === 'file' ? name.replace(/\.md$/, '') : name;
    input.defaultValue = input.value;
    input.focus();
    input.select();
}

function closeRenameModal() {
    const modal = document.getElementById('renameModal');
    modal.style.display = 'none';
    contextMenuTarget = null;
}

async function confirmRename() {
    const btn = document.getElementById('confirmRenameBtn');
    if (btn.disabled || !contextMenuTarget) return;
    const target = contextMenuTarget;
    const oldPath = target.path;

    const input = document.getElementById('renameInput');
    const newName = input.value.trim();
    if (!newName || newName === input.defaultValue) {
        closeRenameModal();
        return;
    }

    btn.textContent = 'Renaming...';
    btn.disabled = true;

    try {
        if (!await saveFile()) return;
        const response = await fetch('/api/rename', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                path: oldPath,
                new_name: newName
            })
        });

        const data = await response.json();

        if (data.success) {
            const newPath = data.new_path;
            if (contextMenuTarget === target) closeRenameModal();
            // Update the open path before refreshing both navigation views.
            if (currentFile === oldPath || (currentFile && currentFile.startsWith(oldPath + '/'))) {
                currentFile = newPath + currentFile.slice(oldPath.length);
                // The move trigger adds one revision. Keep any concurrent edit ahead
                // of this editor's revision so the normal save conflict check still works.
                if (newPath !== oldPath) currentRevision += 1;
                writePreference('vaulted_lastFile', currentFile);
                displayCurrentPath(currentFile);
            }
            await loadFileTree();
            // Highlight and scroll to the renamed item
            highlightTreeItem(newPath);
            saveStatus.textContent = 'Renamed';
            saveStatus.className = 'save-status saved';
            setTimeout(() => { saveStatus.textContent = ''; }, 3000);
        } else {
            alert('Error: ' + (data.error || 'Failed to rename'));
        }
    } catch (error) {
        console.error('Rename failed:', error);
        alert('Error: Failed to rename. Check console for details.');
    } finally {
        btn.textContent = 'Rename';
        btn.disabled = false;
    }
}

// Add Page modal functions
function openAddPageModal() {
    const modal = document.getElementById('addPageModal');
    const input = document.getElementById('addPageInput');
    const menu = document.getElementById('contextMenu');

    menu.style.display = 'none';
    modal.style.display = 'flex';

    // Clear input and focus
    input.value = '';
    input.focus();
}

function closeAddPageModal() {
    const modal = document.getElementById('addPageModal');
    modal.style.display = 'none';
    contextMenuTarget = null;
}

async function confirmAddPage() {
    if (!contextMenuTarget || contextMenuTarget.type !== 'directory') return;

    const input = document.getElementById('addPageInput');
    const filename = input.value.trim();
    if (!filename) {
        closeAddPageModal();
        return;
    }

    const btn = document.getElementById('confirmAddPageBtn');
    btn.textContent = 'Creating...';
    btn.disabled = true;

    try {
        const response = await fetch('/api/create-page', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                folder: contextMenuTarget.path,
                filename: filename
            })
        });

        const data = await response.json();

        if (data.success) {
            closeAddPageModal();
            // Refresh tree
            await loadFileTree();
            // Load the new file
            await loadFile(data.path);
            // Highlight in tree
            highlightTreeItem(data.path);
            saveStatus.textContent = 'Created: ' + data.filename;
            saveStatus.className = 'save-status saved';
            setTimeout(() => { saveStatus.textContent = ''; }, 3000);
        } else {
            alert('Error: ' + (data.error || 'Failed to create page'));
        }
    } catch (error) {
        console.error('Create page failed:', error);
        alert('Error: Failed to create page. Check console for details.');
    } finally {
        btn.textContent = 'Create Page';
        btn.disabled = false;
    }
}

// Setup rename context menu handler
document.addEventListener('DOMContentLoaded', () => {
    const renameItem = document.getElementById('contextRename');
    if (renameItem) {
        renameItem.addEventListener('click', openRenameModal);
    }

    const addPageItem = document.getElementById('contextAddPage');
    if (addPageItem) {
        addPageItem.addEventListener('click', openAddPageModal);
    }

    const confirmBtn = document.getElementById('confirmRenameBtn');
    if (confirmBtn) {
        confirmBtn.addEventListener('click', confirmRename);
    }

    const renameInput = document.getElementById('renameInput');
    if (renameInput) {
        renameInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                confirmRename();
            } else if (e.key === 'Escape') {
                closeRenameModal();
            }
        });
    }

    const confirmAddPageBtn = document.getElementById('confirmAddPageBtn');
    if (confirmAddPageBtn) {
        confirmAddPageBtn.addEventListener('click', confirmAddPage);
    }

    const addPageInput = document.getElementById('addPageInput');
    if (addPageInput) {
        addPageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                confirmAddPage();
            } else if (e.key === 'Escape') {
                closeAddPageModal();
            }
        });
    }

    // Quick Paste modal handlers
    const confirmQuickPasteBtn = document.getElementById('confirmQuickPasteBtn');
    if (confirmQuickPasteBtn) {
        confirmQuickPasteBtn.addEventListener('click', confirmQuickPaste);
    }

    const quickPasteArea = document.getElementById('quickPasteArea');
    if (quickPasteArea) {
        quickPasteArea.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                confirmQuickPaste();
            } else if (e.key === 'Escape') {
                closeQuickPasteModal();
            }
        });
        // Handle paste event to capture rich text
        quickPasteArea.addEventListener('paste', (e) => {
            // Let the default paste happen, then we'll read the HTML
            setTimeout(() => {
                // Content is now pasted, modal will use innerHTML
            }, 0);
        });
    }
});

// Debounce utility
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Search state
let isSearchActive = false;
let lastSearchQuery = '';

// Open search panel
function openSearch() {
    phoneLayout?.openDrawer();
    const searchPanel = document.getElementById('searchPanel');
    const fileTree = document.getElementById('fileTree');
    const searchInput = document.getElementById('searchInput');
    
    isSearchActive = true;
    searchPanel.style.display = 'flex';
    fileTree.style.display = 'none';
    
    // Focus input and select any existing text
    searchInput.focus();
    searchInput.select();
    
    // If there's already a query, refresh results
    if (searchInput.value.trim()) {
        performSearch();
    }
}

// Close search panel
function closeSearch() {
    const searchPanel = document.getElementById('searchPanel');
    const fileTree = document.getElementById('fileTree');
    const searchInput = document.getElementById('searchInput');
    
    isSearchActive = false;
    searchPanel.style.display = 'none';
    fileTree.style.display = 'block';
    
    // Clear search input
    searchInput.value = '';
    
    // Highlight current file in tree
    if (currentFile) {
        highlightTreeItem(currentFile);
    }
}

// Perform search
async function performSearch() {
    const searchInput = document.getElementById('searchInput');
    const searchResults = document.getElementById('searchResults');
    const query = searchInput.value.trim();
    
    if (!query) {
        searchResults.innerHTML = '<div class="search-placeholder">Type to search...</div>';
        return;
    }
    
    lastSearchQuery = query;
    searchResults.innerHTML = '<div class="search-placeholder">Searching...</div>';
    
    try {
        const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
        const data = await response.json();
        
        if (data.error) {
            searchResults.innerHTML = `<div class="search-no-results">Error: ${escapeHtml(data.error)}</div>`;
            return;
        }
        
        if (data.count === 0) {
            searchResults.innerHTML = '<div class="search-no-results">No results found</div>';
            return;
        }
        
        // Render results
        let html = '';
        data.results.forEach(result => {
            const isActive = result.path === currentFile ? 'active' : '';
            html += `
                <div class="search-result-item ${isActive}" data-path="${escapeHtml(result.path)}">
                    <div class="search-result-path">${escapeHtml(result.path)}</div>
                    <div class="search-result-preview">${escapeHtml(result.preview)}</div>
                    <div class="search-result-count">${result.matches} match${result.matches !== 1 ? 'es' : ''}</div>
                </div>
            `;
        });
        
        searchResults.innerHTML = html;
        
        // Add click handlers to results
        document.querySelectorAll('.search-result-item').forEach(item => {
            item.addEventListener('click', () => {
                const path = item.dataset.path;
                loadFile(path);
                // Update active state
                document.querySelectorAll('.search-result-item').forEach(i => i.classList.remove('active'));
                item.classList.add('active');
            });
        });
        
    } catch (error) {
        console.error('Search failed:', error);
        searchResults.innerHTML = '<div class="search-no-results">Search failed. Check console for details.</div>';
    }
}

// Start
init();
