/* Page-local, opt-in archival. No vault scan and no downloads until clicked. */
window.VaultedImageMigration = {
    create({banner, message, migrate, dismiss, getState, save, apply, lock, request = window.fetch.bind(window)}) {
        const dismissed = new Set();
        const counts = new Map();
        const results = new Map();
        let busyPath = null;
        let starting = false;
        function draw() {
            const {path} = getState();
            lock(busyPath === path && !!path);
            const count = counts.get(path) || 0;
            const result = results.get(path);
            banner.hidden = !path || (dismissed.has(path) && busyPath !== path) || (!count && !result && busyPath !== path);
            if (banner.hidden) return;
            const here = busyPath === path;
            message.textContent = here ? 'Copying images into Vaulted… You can keep reading or open another page.' :
                result || `${count} image${count === 1 ? ' is' : 's are'} stored outside Vaulted. Save copies so this page stays self-contained.`;
            migrate.hidden = !count || here;
            migrate.disabled = !!busyPath || starting;
            migrate.textContent = result ? 'Retry remaining images' : 'Save images in Vaulted';
            dismiss.hidden = here;
            dismiss.textContent = count ? 'Not now' : 'Dismiss';
        }
        async function run() {
            if (busyPath || starting) return;
            const selected = getState().path;
            starting = true; draw();
            try {
                if (!await save() || getState().path !== selected) return;
                let snapshot = getState();
                if (snapshot.dirty) return;
                busyPath = selected;
                dismissed.delete(selected); results.delete(selected); draw();
                const failed = new Set();
                let migrated = 0;
                while (true) {
                    const response = await request('/api/migrate-images', {
                        method: 'POST', headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({path: selected, revision: snapshot.revision, skip_urls: [...failed]})
                    });
                    const data = await response.json();
                    if (!response.ok || !data.success) throw new Error(data.error || 'Image migration failed.');
                    migrated += data.migrated;
                    for (const url of data.failed_urls) failed.add(url);
                    counts.set(selected, data.remaining);
                    // Never apply a response to another page or overwrite local edits.
                    const now = getState();
                    if (now.path === selected) {
                        if (now.revision !== snapshot.revision || now.dirty) {
                            throw new Error('Images were saved, but this page changed locally. Reload it to see them; your editor text was kept.');
                        }
                        apply(data);
                    }
                    snapshot = {path: selected, revision: data.revision};
                    if (!data.deferred) {
                        results.set(selected, data.remaining ?
                            `${migrated} image${migrated === 1 ? '' : 's'} saved. ${data.remaining} could not be copied and remain unchanged. You can retry them.` :
                            `${migrated} image${migrated === 1 ? '' : 's'} saved in Vaulted. Their references will survive moving this page.`);
                        break;
                    }
                    if (!data.migrated && !data.failed_urls.length) throw new Error('Image copying paused. Try the remaining images again.');
                    // Continue bounded batches automatically for the user's one action.
                }
            } catch (error) {
                results.set(selected, error.message + ' Existing page text has not been overwritten.');
            } finally {
                busyPath = null; starting = false; draw();
            }
        }
        migrate.addEventListener('click', run);
        dismiss.addEventListener('click', () => { dismissed.add(getState().path); draw(); });
        return {
            show(count) { const {path} = getState(); counts.set(path, count); results.delete(path); draw(); },
            isBusy(path) { return !!path && busyPath === path; },
            run
        };
    }
};
