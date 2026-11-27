// Presentation only. File reads, saves, searches and tree actions stay in app.js.
function createPhoneLayout({readPreference, writePreference, openSearch, openTreeMenu, refreshTitle}) {
    const byId = id => document.getElementById(id);
    const body = document.body;
    const tree = byId('physicalTree');
    const browse = byId('browseBtn');
    const more = byId('moreBtn');
    const menu = byId('contextMenu');
    const background = document.querySelectorAll('.toolbar, .editor-container, .image-migration-banner');
    const phoneSize = matchMedia('(any-pointer: coarse) and (max-width: 600px), (any-pointer: coarse) and (max-width: 960px) and (max-height: 500px)');
    let full = readPreference('vaulted_fullLayout') === 'true';
    let compact = false;
    let press = null;
    let heldRow = null;

    function setMore(open, restoreFocus = false) {
        body.classList.toggle('more-open', open);
        more.setAttribute('aria-expanded', String(open));
        if (open) byId('quickPasteBtn').focus();
        else if (restoreFocus) more.focus();
    }

    function closeDrawer() {
        if (!body.classList.contains('drawer-open')) return;
        cancelPress();
        body.classList.remove('drawer-open');
        browse.setAttribute('aria-expanded', 'false');
        menu.style.display = 'none';
        byId('drawerStatus').textContent = '';
        background.forEach(el => { el.inert = false; });
        browse.focus({preventScroll: true});
    }

    function openDrawer() {
        if (!compact || body.classList.contains('drawer-open')) return;
        setMore(false);
        body.classList.add('drawer-open');
        browse.setAttribute('aria-expanded', 'true');
        background.forEach(el => { el.inert = true; });
        byId('closeDrawer').focus({preventScroll: true});
    }

    function addNodeAction(row) {
        if (!compact || row.lastElementChild?.classList.contains('node-actions')) return;
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'phone-only node-actions';
        button.setAttribute('aria-label', 'Actions for ' + row.dataset.path);
        button.textContent = '⋯';
        row.append(button);
    }

    function updateLayout() {
        body.classList.toggle('phone-size', phoneSize.matches);
        const next = phoneSize.matches && !full;
        if (compact === next) return;
        closeDrawer();
        setMore(false);
        compact = next;
        body.classList.toggle('phone-layout', compact);
        refreshTitle();
        if (compact) tree.querySelectorAll('[data-path]').forEach(addNodeAction);
    }

    function chooseFullLayout(value) {
        full = value;
        writePreference('vaulted_fullLayout', String(value));
        updateLayout();
        (full ? byId('restorePhone') : browse).focus();
    }

    browse.addEventListener('click', openDrawer);
    byId('closeDrawer').addEventListener('click', closeDrawer);
    byId('drawerBackdrop').addEventListener('click', closeDrawer);
    byId('drawerSearch').addEventListener('click', openSearch);
    more.addEventListener('click', () => setMore(!body.classList.contains('more-open')));
    byId('useFull').addEventListener('click', () => chooseFullLayout(true));
    byId('restorePhone').addEventListener('click', () => chooseFullLayout(false));
    document.addEventListener('click', event => {
        if (body.classList.contains('more-open') && !more.contains(event.target)) setMore(false);
    });
    document.addEventListener('keydown', event => {
        if (menu.contains(event.target) && ['Enter', ' '].includes(event.key)) {
            event.preventDefault();
            event.target.click();
        }
        if (!compact || event.key !== 'Escape' || event.target.closest('.modal')) return;
        if (menu.style.display === 'block') {
            menu.style.display = 'none';
            byId('closeDrawer').focus();
        } else if (body.classList.contains('more-open')) setMore(false, true);
        else if (event.target !== byId('searchInput')) closeDrawer();
    });

    function showRowMenu(row, x, y) {
        openTreeMenu(row.dataset.path, row.classList.contains('directory') ? 'directory' : 'file', x, y);
        const firstAction = row.classList.contains('directory') ? 'contextAddPage' : 'contextRename';
        byId(firstAction).focus({preventScroll: true});
    }

    // Catch the action button or release after a hold before the row's ordinary click.
    tree.addEventListener('click', event => {
        if (!compact) return;
        const row = event.target.closest('.tree-item[data-path]');
        if (!row) return;
        const trigger = event.target.closest('.node-actions');
        if (!trigger && row !== heldRow) return;
        event.preventDefault();
        event.stopPropagation();
        heldRow = null;
        if (trigger) {
            const rect = trigger.getBoundingClientRect();
            showRowMenu(row, rect.right, rect.bottom);
        }
    }, true);

    function cancelPress() {
        if (press) clearTimeout(press.timer);
        press = null;
    }

    tree.addEventListener('pointerdown', event => {
        if (!compact) return;
        cancelPress();
        menu.style.display = 'none';
        heldRow = null;
        const row = event.target.closest('.tree-item[data-path]');
        if (!row || event.pointerType !== 'touch' || !event.isPrimary || event.target.closest('button')) return;
        const x = event.clientX, y = event.clientY;
        press = {x, y, timer: setTimeout(() => {
            heldRow = row;
            showRowMenu(row, x, y);
            press = null;
        }, 500)};
    });
    tree.addEventListener('pointermove', event => {
        if (press && Math.hypot(event.clientX - press.x, event.clientY - press.y) > 10) cancelPress();
    });
    ['pointerup', 'pointercancel', 'pointerleave'].forEach(type => tree.addEventListener(type, cancelPress));
    byId('fileTree').addEventListener('scroll', cancelPress);
    tree.addEventListener('contextmenu', event => {
        if (compact) {
            cancelPress();
            heldRow = event.target.closest('.tree-item[data-path]');
        }
    }, true);

    phoneSize.addEventListener('change', updateLayout);
    updateLayout();
    return {openDrawer, closeDrawer, addNodeAction, navigationError(message) {
        if (body.classList.contains('drawer-open')) byId('drawerStatus').textContent = message;
    }};
}
