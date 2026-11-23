import { html, nothing } from '../../vendor/lit-html.js';
import { getLang, LANGUAGES, setLang, t } from '../i18n.js';
import { state } from '../state.js';

export function healthState() {
    const s = state.status;
    if (!s || !s.active) return 'down';
    return s.health?.state || 'checking';
}

export function statusBadge() {
    const s = state.status;
    if (state.statusError) {
        return html`<span class="status-badge unknown"><span class="status-dot"></span>${t('unreachable')}</span>`;
    }
    if (!s) return html`<span class="status-badge inactive"><span class="status-dot"></span>…</span>`;
    if (!s.active) {
        return html`<span class="status-badge inactive"><span class="status-dot"></span>${t('offline')}</span>`;
    }
    const health = healthState();
    return html`<span class="status-badge active health-${health}" title=${t(`healthHelp_${health}`)}>
        <span class="status-dot"></span>${t('online')}<span class="health-tag">${t(`health_${health}`)}</span>
    </span>`;
}

export function langSelect() {
    const onChange = (e) => setLang(e.currentTarget.value);
    return html`<select class="lang-select" name="lang" aria-label=${t('language')} @change=${onChange}>
        ${LANGUAGES.map((l) => html`<option value=${l.code} ?selected=${l.code === getLang()}>${l.label}</option>`)}
    </select>`;
}

export function headerView({ onLogout } = {}) {
    return html`<header class="app-header">
        <div class="header-tools">
            ${langSelect()}
            ${onLogout
                ? html`<button type="button" class="btn-secondary btn-small" @click=${onLogout}>${t('logout')}</button>`
                : nothing}
        </div>
        <div class="logo">LOBBY<span>SHIFT</span></div>
        <div class="tagline">${t('tagline')}</div>
        ${onLogout
            ? html`<div class="header-status">${statusBadge()}
                  ${state.version ? html`<span class="version">v${state.version}</span>` : nothing}</div>`
            : nothing}
    </header>`;
}
