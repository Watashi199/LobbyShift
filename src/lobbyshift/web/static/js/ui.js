// Shared UI building blocks: flags, cards, toasts, modals.

import { html, nothing } from '../vendor/lit-html.js';
import twemoji from '../vendor/twemoji.esm.js';
import { ApiError } from './api.js';
import { flagEmoji, normalizeCode } from './format.js';
import { t } from './i18n.js';
import { state, toggleCollapsed, update } from './state.js';

// ------------------------------------------------------------------- flags

function onFlagError(event) {
    // Image CDN unreachable: fall back to the native emoji glyph.
    const img = event.currentTarget;
    img.hidden = true;
    const fallback = img.nextElementSibling;
    if (fallback) fallback.hidden = false;
}

/** Twemoji flag for a country code (codes are validated, never raw input). */
export function flag(code, size = '') {
    const emoji = flagEmoji(code);
    const src = `${twemoji.base}svg/${twemoji.convert.toCodePoint(emoji)}.svg`;
    const label = normalizeCode(code) || '??';
    return html`<span class="flag ${size}" title=${label}
        ><img class="emoji" src=${src} alt=${emoji} draggable="false" loading="lazy" @error=${onFlagError}
        /><span class="flag-text" hidden>${emoji}</span></span>`;
}

// ------------------------------------------------------------------- cards

export function card({ key, title, badge = nothing, actions = nothing, summary = nothing, body, cls = '' }) {
    const collapsible = Boolean(key);
    const collapsed = collapsible && state.collapsed.has(key);
    const header = collapsible
        ? html`<button type="button" class="card-header collapsible" aria-expanded=${String(!collapsed)}
              @click=${() => toggleCollapsed(key)}>
              <span class="card-title">${title}</span>
              <span class="card-header-right">${badge}<span class="collapse-icon" aria-hidden="true">▼</span></span>
          </button>`
        : html`<div class="card-header"><span class="card-title">${title}</span>
              <span class="card-header-right">${badge}${actions}</span></div>`;
    return html`<section class="card ${cls} ${collapsed ? 'is-collapsed' : ''}">
        ${header}
        ${collapsed ? summary : html`<div class="card-body">${body}</div>`}
    </section>`;
}

export function spinner() {
    return html`<span class="spinner" aria-hidden="true"></span>`;
}

// ------------------------------------------------------------------ toasts

let toastSeq = 0;

export function toast(message, kind = 'success', details = []) {
    const id = ++toastSeq;
    state.toasts = [...state.toasts, { id, message, kind, details }];
    update();
    const ttl = kind === 'error' ? 7000 : 3500;
    setTimeout(() => dismissToast(id), ttl + details.length * 1000);
}

export function dismissToast(id) {
    state.toasts = state.toasts.filter((x) => x.id !== id);
    update();
}

/** Show an error from api.js (or anything else) as a toast. */
export function toastError(err) {
    if (err instanceof ApiError) {
        if (err.status === 401) return; // handled globally: back to login
        const message = err.status === 0 ? t('networkError') : err.message;
        const details = err.errors.map((e) => `${e.file}: ${e.error}`);
        toast(message, 'error', details);
        return;
    }
    console.error(err);
    toast(String(err?.message || err), 'error');
}

export function toastsView() {
    return html`<div class="toasts" role="status" aria-live="polite">
        ${state.toasts.map(
            (x) => html`<div class="toast ${x.kind}" @click=${() => dismissToast(x.id)}>
                <div>${x.message}</div>
                ${x.details.length
                    ? html`<ul class="toast-details">${x.details.slice(0, 8).map((d) => html`<li>${d}</li>`)}</ul>`
                    : nothing}
            </div>`,
        )}
    </div>`;
}

// ------------------------------------------------------------------ modals

let modalResolve = null;

/** Open a modal; resolves with the value passed to closeModal(). */
export function openModal(modal) {
    if (modalResolve) modalResolve(undefined);
    return new Promise((resolve) => {
        modalResolve = resolve;
        update({ modal });
    });
}

export function closeModal(value) {
    const resolve = modalResolve;
    modalResolve = null;
    update({ modal: null });
    if (resolve) resolve(value);
}

export function confirmDialog({ title, message, confirmLabel, danger = false }) {
    return openModal({ type: 'confirm', title, message, confirmLabel, danger }).then(Boolean);
}

export function promptDialog({ title, message, value = '', placeholder = '', maxlength = 64 }) {
    return openModal({ type: 'prompt', title, message, value, placeholder, maxlength });
}

export function infoDialog({ title, lines }) {
    return openModal({ type: 'info', title, lines });
}

document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && state.modal && !state.modal.locked) closeModal(undefined);
});

export function modalFrame({ title, body, footer, wide = false }) {
    const onBackdrop = (event) => {
        if (event.target === event.currentTarget && !state.modal?.locked) closeModal(undefined);
    };
    return html`<div class="modal" @mousedown=${onBackdrop}>
        <div class="modal-content ${wide ? 'wide' : ''}" role="dialog" aria-modal="true" aria-label=${title}>
            <div class="modal-header">
                <h3>${title}</h3>
                <button type="button" class="modal-close" aria-label=${t('close')} @click=${() => closeModal(undefined)}>×</button>
            </div>
            <div class="modal-body">${body}</div>
            ${footer ? html`<div class="modal-footer">${footer}</div>` : nothing}
        </div>
    </div>`;
}

function confirmView(m) {
    return modalFrame({
        title: m.title,
        body: html`<p class="modal-text">${m.message}</p>`,
        footer: html`
            <button type="button" class=${m.danger ? 'btn-danger' : 'btn-primary'} @click=${() => closeModal(true)}>
                ${m.confirmLabel || t('confirm')}</button>
            <button type="button" class="btn-secondary" @click=${() => closeModal(false)}>${t('cancel')}</button>`,
    });
}

function promptView(m) {
    const submit = (event) => {
        event.preventDefault();
        const input = event.currentTarget.elements.namedItem('value');
        closeModal(input.value);
    };
    return modalFrame({
        title: m.title,
        body: html`<form id="prompt-form" @submit=${submit}>
            ${m.message ? html`<p class="modal-text">${m.message}</p>` : nothing}
            <input class="input" name="value" type="text" autocomplete="off" maxlength=${m.maxlength}
                .value=${m.value} placeholder=${m.placeholder} autofocus>
        </form>`,
        footer: html`
            <button type="submit" form="prompt-form" class="btn-primary">${t('save')}</button>
            <button type="button" class="btn-secondary" @click=${() => closeModal(undefined)}>${t('cancel')}</button>`,
    });
}

function infoView(m) {
    return modalFrame({
        title: m.title,
        body: html`${m.lines.map((line) => html`<p class="modal-text">${line}</p>`)}`,
        footer: html`<button type="button" class="btn-primary" @click=${() => closeModal(true)}>${t('rogerThat')}</button>`,
    });
}

const modalViews = { confirm: confirmView, prompt: promptView, info: infoView };

export function registerModal(type, view) {
    modalViews[type] = view;
}

export function modalView() {
    const m = state.modal;
    if (!m) return nothing;
    const view = modalViews[m.type];
    return view ? view(m) : nothing;
}

/** Focus the first autofocus field after a modal renders. */
export function focusModal() {
    requestAnimationFrame(() => {
        const el = document.querySelector('.modal [autofocus]');
        if (el && document.activeElement !== el && !el.dataset.focused) {
            el.dataset.focused = '1';
            el.focus();
            if (typeof el.select === 'function' && el.tagName === 'INPUT') el.select();
        }
    });
}
