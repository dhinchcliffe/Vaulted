const status = document.getElementById('status');
async function post(path, body = {}) {
    const response = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Vaulted-Request': '1'}, body: JSON.stringify(body)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Please sign in and try again.');
    return data;
}
document.getElementById('createToken').onclick = async function () {
    this.disabled = true;
    try {
        const data = await post('/api/share/token');
        document.getElementById('token').value = data.token;
        document.getElementById('newToken').hidden = false;
        status.textContent = 'Token created. Copy it and add the shortcut before leaving this page.';
    } catch (e) { status.textContent = e.message; this.disabled = false; }
};
document.getElementById('copyToken').onclick = async () => {
    const input = document.getElementById('token');
    try { await navigator.clipboard.writeText(input.value); status.textContent = 'Copied. Now download and set up the shortcut.'; }
    catch (_) { input.focus(); input.select(); status.textContent = 'Select and copy the token above.'; }
};
document.querySelectorAll('.revoke').forEach(button => button.onclick = async () => {
    if (!confirm('Revoke this token? Its shortcut will stop saving until you configure a new token.')) return;
    try { await post('/api/share/revoke', {id: button.dataset.id}); button.closest('.token-row').remove(); status.textContent = 'Token revoked.'; }
    catch (e) { status.textContent = e.message; }
});
