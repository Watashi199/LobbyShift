import { html, nothing } from '../../vendor/lit-html.js';
import { labelOf, loadStatus, tunnelDown, tunnelUp } from '../actions.js';
import { countryName, formatTime, humanBytes, humanDuration, localTimeFor, timezoneFor } from '../format.js';
import { t } from '../i18n.js';
import { isBusy, state } from '../state.js';
import { card, flag, spinner } from '../ui.js';
import { healthState, statusBadge } from './header.js';

function problemsBanner(problems) {
    if (!problems?.length) return nothing;
    return html`<div class="banner banner-danger" role="alert">
        <div class="banner-title">⚠ ${t('problemsTitle')}</div>
        <ul>${problems.map((p) => html`<li>${p}</li>`)}</ul>
        <div class="banner-hint">${t('problemsHint')}</div>
    </div>`;
}

function regionClock(cfg) {
    const code = cfg?.country?.code;
    const tz = timezoneFor(code);
    if (!cfg || !tz) return nothing;
    return html`<div class="region-time">
        <div class="region-info">
            ${flag(code, 'xl')}
            <div class="region-details">
                <h3>${countryName(code)}</h3>
                <span>${tz.replaceAll('_', ' ')}</span>
            </div>
        </div>
        <div class="region-clock">
            <div class="time">${localTimeFor(code, { seconds: true })}</div>
            <div class="label">${t('localTime')}</div>
        </div>
    </div>`;
}

function item(label, value, cls = '') {
    return html`<div class="status-item ${cls}"><span class="status-label">${label}</span>
        <span class="status-value">${value}</span></div>`;
}

export function statusView() {
    const s = state.status;
    const cfg = s?.config;
    const tunnel = s?.tunnel || {};
    const busy = isBusy('tunnel');
    const health = healthState();
    const now = Date.now() / 1000;

    const regionValue = cfg
        ? html`<span class="inline-flag">${flag(cfg.country?.code)}<span class="ellipsis">${labelOf(cfg)}</span></span>`
        : t('none');

    const handshake = tunnel.handshake_age != null
        ? t('agoSeconds', { d: humanDuration(tunnel.handshake_age) })
        : s?.active ? t('noHandshakeYet') : '-';

    const body = html`
        ${problemsBanner(s?.problems)}
        ${s?.active && (health === 'stale' || health === 'down')
            ? html`<div class="banner banner-warning">${t(`healthHelp_${health}`)}${s.health?.error ? html` (${s.health.error})` : nothing}</div>`
            : nothing}
        ${regionClock(cfg)}
        <div class="status-grid">
            ${item(t('activeRegion'), regionValue, 'wide')}
            ${item(t('country'), cfg ? `${countryName(cfg.country?.code)} (${cfg.country?.code || '??'})` : '-')}
            ${item(t('endpoint'), html`<span class="mono">${tunnel.endpoint || cfg?.endpoint || '-'}</span>`)}
            ${item(t('lastHandshake'), handshake, health === 'stale' ? 'warn' : '')}
            ${item(t('transfer'), s?.active ? `↓ ${humanBytes(tunnel.rx_bytes)} · ↑ ${humanBytes(tunnel.tx_bytes)}` : '-')}
            ${item(t('connectedSince'), s?.connected_at
                ? `${formatTime(s.connected_at)} (${humanDuration(now - s.connected_at)})`
                : '-')}
        </div>
        <div class="actions">
            <button type="button" class="btn-primary" ?disabled=${busy || s?.active || !state.configs.length}
                @click=${tunnelUp}>${busy && !s?.active ? spinner() : nothing}${t('connect')}</button>
            <button type="button" class="btn-danger" ?disabled=${busy || !s?.active}
                @click=${tunnelDown}>${busy && s?.active ? spinner() : nothing}${t('disconnect')}</button>
            <button type="button" class="btn-secondary" @click=${loadStatus}>${t('refresh')}</button>
        </div>`;

    return card({ title: t('systemStatus'), badge: statusBadge(), body });
}

export function consoleSetupView() {
    const lan = state.status?.lan || state.settings?.lan;
    if (!lan) return nothing;
    return html`<div class="setup-info">
        <h3>⚙ ${t('consoleConfig')}</h3>
        <p>${t('consoleConfigDesc')}</p>
        <dl class="kv">
            <dt>${t('gateway')}</dt><dd><code>${lan.address}</code></dd>
            <dt>${t('dns')}</dt><dd><code>1.1.1.1</code> ${t('orRouterIp')}</dd>
            <dt>${t('lanSubnet')}</dt><dd><code>${lan.subnet}</code> (${lan.interface})</dd>
        </dl>
    </div>`;
}
