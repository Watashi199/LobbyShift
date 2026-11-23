import { html, nothing } from '../../vendor/lit-html.js';
import { clearEvents, loadEvents } from '../actions.js';
import { formatDateTime } from '../format.js';
import { t } from '../i18n.js';
import { state } from '../state.js';
import { card } from '../ui.js';

const ICONS = {
    connected: '▲',
    reconnected: '↻',
    disconnected: '■',
    imported: '⬇',
    edited: '✎',
    deleted: '✕',
    error: '⚠',
    migrated: '⇪',
};

function eventLabel(action) {
    const key = `event_${action}`;
    const label = t(key);
    return label === key ? String(action) : label;
}

export function eventsView() {
    const events = state.events;
    const body = html`
        <div class="toolbar toolbar-end">
            <button type="button" class="btn-secondary btn-small" @click=${loadEvents}>${t('refresh')}</button>
            <button type="button" class="btn-danger btn-small" ?disabled=${!events.length} @click=${clearEvents}>${t('clear')}</button>
        </div>
        <div class="logs-container">
            ${events.length
                ? events.map((e) => html`<div class="log-entry">
                    <span class="log-icon log-${ICONS[e.action] ? e.action : 'other'}" aria-hidden="true">${ICONS[e.action] || '•'}</span>
                    <div class="log-body">
                        <div>
                            <span class="log-action">${eventLabel(e.action)}</span>
                            ${e.config ? html` <span class="log-config">${e.config}</span>` : nothing}
                        </div>
                        ${e.details ? html`<div class="log-details">${e.details}</div>` : nothing}
                        <div class="log-time">${formatDateTime(e.ts)}</div>
                    </div>
                </div>`)
                : html`<div class="empty-logs">${t('noLogs')}</div>`}
        </div>`;
    return card({
        key: 'logs',
        title: t('operationLog'),
        badge: events.length ? html`<span class="count">${events.length}</span>` : nothing,
        body,
    });
}
