// Single mutable app state + batched re-render scheduling.

import { storage } from './storage.js';

export const state = {
    booted: false,
    authenticated: false,
    version: '',

    status: null,
    statusError: false,
    configs: [],
    configsLoaded: false,
    events: [],
    settings: null,
    proton: null,
    doctor: null,

    filter: '',
    expanded: new Set(), // region names with details unfolded
    collapsed: new Set(storage.getJSON('collapsed', ['logs', 'settings', 'proton'])),
    busy: new Set(), // keys of running actions (disables buttons)
    uploadReport: null, // {imported: n, errors: [{file, error}]}
    dragover: false,

    modal: null,
    toasts: [],
};

let renderFn = () => {};
let scheduled = false;

export function setRenderer(fn) {
    renderFn = fn;
}

export function update(patch) {
    if (patch) Object.assign(state, patch);
    if (scheduled) return;
    scheduled = true;
    queueMicrotask(() => {
        scheduled = false;
        renderFn();
    });
}

export function isBusy(key) {
    return state.busy.has(key);
}

/** Run an async action with a busy flag; returns its result or undefined on error. */
export async function withBusy(key, fn) {
    if (state.busy.has(key)) return undefined;
    state.busy.add(key);
    update();
    try {
        return await fn();
    } finally {
        state.busy.delete(key);
        update();
    }
}

export function toggleCollapsed(key) {
    if (state.collapsed.has(key)) state.collapsed.delete(key);
    else state.collapsed.add(key);
    storage.setJSON('collapsed', [...state.collapsed]);
    update();
}
