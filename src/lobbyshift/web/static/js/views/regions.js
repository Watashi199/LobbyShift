import { html, nothing } from '../../vendor/lit-html.js';
import {
    deploy, labelOf, measureLatency, openEditor, remove, rename, toggleFavorite, uploadFiles,
} from '../actions.js';
import { countryName, latencyClass, localTimeFor, normalizeCode } from '../format.js';
import { getLang, t } from '../i18n.js';
import { isBusy, state, update } from '../state.js';
import { card, flag, spinner } from '../ui.js';

function sortConfigs(configs) {
    const collator = new Intl.Collator(getLang(), { sensitivity: 'base', numeric: true });
    return [...configs].sort((a, b) =>
        (b.active - a.active)
        || (b.favorite - a.favorite)
        || collator.compare(labelOf(a), labelOf(b)));
}

function matches(cfg, query) {
    if (!query) return true;
    const q = query.toLowerCase();
    const code = cfg.country?.code || '';
    return [cfg.name, cfg.display_name, code, countryName(code), cfg.endpoint, cfg.meta?.server, cfg.provider]
        .some((v) => v && String(v).toLowerCase().includes(q));
}

function latencyBadge(ms) {
    const cls = latencyClass(ms);
    const text = ms == null ? '-' : `${Math.round(ms)} ms`;
    return html`<span class="latency latency-${cls}" title=${t('latency')}>${text}</span>`;
}

function adviceText(tip, meta) {
    const key = `advice_${tip.code}`;
    const translated = t(key, { entry: countryName(meta?.entry_country) });
    return translated === key ? tip.message : translated;
}

function notes(cfg) {
    const meta = cfg.meta || {};
    const advice = Array.isArray(meta.advice) ? meta.advice : [];
    const ignored = Array.isArray(meta.ignored_keys) ? meta.ignored_keys : [];
    if (!advice.length && !ignored.length) return nothing;

    const open = state.expanded.has(cfg.name);
    const warnings = advice.filter((a) => a.level === 'warning').length + ignored.length;
    const toggle = () => {
        if (open) state.expanded.delete(cfg.name);
        else state.expanded.add(cfg.name);
        update();
    };
    return html`<div class="notes">
        <button type="button" class="notes-toggle ${warnings ? 'has-warning' : ''}" aria-expanded=${String(open)} @click=${toggle}>
            ${warnings ? '⚠' : 'ℹ'} ${t('notesCount', { n: advice.length + (ignored.length ? 1 : 0) })} ${open ? '▴' : '▾'}
        </button>
        ${open
            ? html`<ul class="notes-list">
                ${advice.map((tip) => html`<li class="note note-${tip.level === 'warning' ? 'warning' : 'info'}">${adviceText(tip, meta)}</li>`)}
                ${ignored.length
                    ? html`<li class="note note-info">${t('ignoredKeys', { keys: ignored.join(', ') })}</li>`
                    : nothing}
              </ul>`
            : nothing}
    </div>`;
}

function regionItem(cfg) {
    const code = cfg.country?.code;
    const busy = isBusy(`cfg:${cfg.name}`);
    const tunnelBusy = isBusy('tunnel');
    const localTime = localTimeFor(code);
    const meta = cfg.meta || {};
    const cls = ['config-item', cfg.active ? 'active' : '', cfg.favorite ? 'favorite' : ''].join(' ');

    return html`<li class=${cls}>
        <div class="config-main">
            <button type="button" class="favorite-btn ${cfg.favorite ? 'on' : ''}"
                aria-pressed=${String(Boolean(cfg.favorite))}
                title=${cfg.favorite ? t('unfavorite') : t('favorite')}
                ?disabled=${isBusy(`fav:${cfg.name}`)} @click=${() => toggleFavorite(cfg)}>${cfg.favorite ? '★' : '☆'}</button>
            ${flag(code, 'lg')}
            <div class="config-details">
                <div class="config-name">
                    <span class="ellipsis">${labelOf(cfg)}</span>
                    ${cfg.active ? html`<span class="tag tag-active">${t('active')}</span>` : nothing}
                    ${cfg.provider === 'proton' ? html`<span class="tag tag-provider">Proton</span>` : nothing}
                    ${meta.secure_core
                        ? html`<span class="tag tag-warning" title=${t('secureCoreHelp')}>Secure Core${normalizeCode(meta.entry_country) ? ` · ${meta.entry_country}` : ''}</span>`
                        : nothing}
                </div>
                <div class="config-meta">
                    <span class="config-country">${countryName(code)}${normalizeCode(code) ? ` · ${code}` : ''}</span>
                    ${cfg.display_name ? html`<span class="config-id mono">${cfg.name}</span>` : nothing}
                    ${meta.server ? html`<span class="config-id mono">${meta.server}</span>` : nothing}
                    <span class="config-endpoint mono">${cfg.endpoint || '-'}</span>
                    ${localTime ? html`<span class="config-time" title=${t('localTime')}>🕐 ${localTime}</span>` : nothing}
                    ${latencyBadge(cfg.latency_ms)}
                </div>
                ${notes(cfg)}
            </div>
        </div>
        <div class="config-actions">
            <button type="button" class="btn-primary" ?disabled=${cfg.active || tunnelBusy || busy}
                @click=${() => deploy(cfg)}>${cfg.active ? t('active') : t('deploy')}</button>
            <button type="button" class="btn-secondary" ?disabled=${busy} @click=${() => openEditor(cfg)}>${t('edit')}</button>
            <button type="button" class="btn-secondary" ?disabled=${busy} @click=${() => rename(cfg)}>${t('rename')}</button>
            <button type="button" class="btn-danger" ?disabled=${busy} @click=${() => remove(cfg)}>${t('delete')}</button>
        </div>
    </li>`;
}

function uploadZone() {
    const busy = isBusy('upload');
    const onDrop = (e) => {
        e.preventDefault();
        update({ dragover: false });
        if (e.dataTransfer?.files?.length) uploadFiles(e.dataTransfer.files);
    };
    const onDragOver = (e) => {
        e.preventDefault();
        if (!state.dragover) update({ dragover: true });
    };
    const onDragLeave = (e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) update({ dragover: false });
    };
    const onPick = (e) => {
        const input = e.currentTarget;
        uploadFiles(input.files);
        input.value = '';
    };
    return html`<label class="upload-zone ${state.dragover ? 'dragover' : ''} ${busy ? 'busy' : ''}"
            @dragover=${onDragOver} @dragleave=${onDragLeave} @drop=${onDrop}>
        <input class="visually-hidden" type="file" name="files" multiple accept=".conf,.zip" ?disabled=${busy} @change=${onPick}>
        <div class="upload-icon">${busy ? spinner() : '📡'}</div>
        <div class="upload-text">
            <strong>${t('deployNewRegion')}</strong><br>
            <span>${t('dropConfig')}</span>
        </div>
    </label>
    ${uploadReport()}`;
}

function uploadReport() {
    const r = state.uploadReport;
    if (!r) return nothing;
    const cls = r.errors.length ? (r.imported ? 'banner-warning' : 'banner-danger') : 'banner-success';
    return html`<div class="banner ${cls} upload-report">
        <button type="button" class="banner-close" aria-label=${t('close')} @click=${() => update({ uploadReport: null })}>×</button>
        <div class="banner-title">${t('importedCount', { n: r.imported })}</div>
        ${r.errors.length
            ? html`<ul>${r.errors.map((e) => html`<li><span class="mono">${e.file}</span> — ${e.error}</li>`)}</ul>`
            : nothing}
    </div>`;
}

function activeSummary() {
    const cfg = state.configs.find((c) => c.active);
    if (!cfg) return html`<div class="active-summary muted">${t('noActiveRegion')}</div>`;
    const localTime = localTimeFor(cfg.country?.code);
    return html`<div class="active-summary">
        ${flag(cfg.country?.code)}
        <span class="ellipsis strong">${labelOf(cfg)}</span>
        <span class="mono muted">${cfg.endpoint || ''}</span>
        ${localTime ? html`<span class="config-time">🕐 ${localTime}</span>` : nothing}
    </div>`;
}

export function regionsView() {
    const visible = sortConfigs(state.configs.filter((c) => matches(c, state.filter)));
    const busyLatency = isBusy('latency');

    const toolbar = html`<div class="toolbar">
        <input class="input filter" type="search" name="filter" placeholder=${t('filterPlaceholder')} aria-label=${t('filterPlaceholder')}
            .value=${state.filter} @input=${(e) => update({ filter: e.currentTarget.value })}>
        <button type="button" class="btn-secondary" ?disabled=${busyLatency || !state.configs.length}
            @click=${measureLatency}>${busyLatency ? spinner() : nothing}${t('measureLatency')}</button>
    </div>`;

    let list;
    if (!state.configsLoaded) list = html`<p class="empty">${spinner()}</p>`;
    else if (!state.configs.length) list = html`<p class="empty">${t('noRegions')}</p>`;
    else if (!visible.length) list = html`<p class="empty">${t('noMatch')}</p>`;
    else list = html`<ul class="config-list">${visible.map(regionItem)}</ul>`;

    return card({
        key: 'regions',
        title: t('vpnRegions'),
        badge: html`<span class="count">${state.configs.length}</span>`,
        summary: activeSummary(),
        body: html`${state.configs.length ? toolbar : nothing}${list}${uploadZone()}`,
    });
}
