// LobbyShift web UI entry point.

import { html, render } from '../vendor/lit-html.js';
import { api, onUnauthorized } from './api.js';
import { loadEvents, loadStatus, refreshAll } from './actions.js';
import { onLangChange, t } from './i18n.js';
import { setRenderer, state, update } from './state.js';
import { focusModal, modalView, toastError, toastsView } from './ui.js';
import './views/editor.js';
import { eventsView } from './views/events.js';
import { headerView } from './views/header.js';
import { loginView, resetLoginError } from './views/login.js';
import { protonView } from './views/proton.js';
import { regionsView } from './views/regions.js';
import { settingsView } from './views/settings.js';
import { consoleSetupView, statusView } from './views/status.js';

const STATUS_INTERVAL = 5000;
const EVENTS_INTERVAL = 15000;

const appRoot = document.getElementById('app');
const overlayRoot = document.getElementById('overlay');

// ----------------------------------------------------------------- polling

let statusTimer = null;
let eventsTimer = null;
let clockTimer = null;

function startPolling() {
    stopPolling();
    if (!state.authenticated || document.hidden) return;
    statusTimer = setInterval(loadStatus, STATUS_INTERVAL);
    eventsTimer = setInterval(() => {
        if (!state.collapsed.has('logs')) loadEvents();
    }, EVENTS_INTERVAL);
    // Region clocks and "connected since" tick every second.
    clockTimer = setInterval(() => update(), 1000);
}

function stopPolling() {
    clearInterval(statusTimer);
    clearInterval(eventsTimer);
    clearInterval(clockTimer);
    statusTimer = eventsTimer = clockTimer = null;
}

document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        stopPolling();
    } else if (state.authenticated) {
        loadStatus();
        startPolling();
    }
});

// -------------------------------------------------------------------- auth

async function enterApp() {
    resetLoginError();
    try {
        const me = await api.me();
        update({ version: me.version || state.version });
    } catch {
        /* version is cosmetic */
    }
    update({ authenticated: true });
    await refreshAll();
    startPolling();
}

function backToLogin() {
    if (!state.authenticated && state.booted) return;
    stopPolling();
    update({
        booted: true,
        authenticated: false,
        modal: null,
        status: null,
        configs: [],
        configsLoaded: false,
        events: [],
        settings: null,
        proton: null,
        doctor: null,
        uploadReport: null,
    });
}

onUnauthorized(backToLogin);

async function logout() {
    try {
        await api.logout();
    } catch (err) {
        toastError(err);
    }
    backToLogin();
}

// ------------------------------------------------------------------ render

function footerView() {
    return html`<footer class="footer">
        <p>${t('geoAttribution')} <a href="https://db-ip.com" target="_blank" rel="noopener noreferrer">DB-IP</a>
            (CC BY 4.0)</p>
        <p>${t('madeBy')} <a href="https://github.com/Smokimcpot" target="_blank" rel="noopener noreferrer">Smokimcpot</a></p>
    </footer>`;
}

function mainView() {
    return html`<div class="container">
        ${headerView({ onLogout: logout })}
        <main>
            ${statusView()}
            ${regionsView()}
            ${protonView()}
            ${eventsView()}
            ${settingsView()}
            ${consoleSetupView()}
        </main>
        ${footerView()}
    </div>`;
}

function rootView() {
    if (!state.booted) return html`<div class="boot"><div class="logo">LOBBY<span>SHIFT</span></div></div>`;
    if (!state.authenticated) return html`${loginView({ onSuccess: enterApp })}${footerView()}`;
    return mainView();
}

function renderAll() {
    render(rootView(), appRoot);
    render(html`${modalView()}${toastsView()}`, overlayRoot);
    document.body.classList.toggle('modal-open', Boolean(state.modal));
    if (state.modal) focusModal();
    if (!state.authenticated && state.booted) {
        const pw = document.getElementById('login-password');
        if (pw && !pw.dataset.focused) {
            pw.dataset.focused = '1';
            pw.focus();
        }
    }
}

setRenderer(renderAll);
onLangChange(() => update());

// -------------------------------------------------------------------- boot

async function boot() {
    appRoot.replaceChildren(); // drop the static boot screen; lit-html appends otherwise
    renderAll();
    let me = null;
    try {
        me = await api.me();
    } catch (err) {
        toastError(err);
    }
    update({ booted: true, version: me?.version || '' });
    if (me?.authenticated) await enterApp();
}

boot();
