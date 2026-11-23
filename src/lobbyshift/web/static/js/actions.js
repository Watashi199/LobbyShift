// Data loading and mutations. Views call these; they update state and toast.

import { api } from './api.js';
import { t } from './i18n.js';
import { state, update, withBusy } from './state.js';
import { confirmDialog, infoDialog, promptDialog, toast, toastError } from './ui.js';

export function labelOf(cfg) {
    return cfg?.display_name || cfg?.name || '-';
}

// ------------------------------------------------------------------ loading

export async function loadStatus() {
    try {
        const status = await api.status();
        const prevActive = state.status?.config?.name ?? null;
        const nowActive = status.config?.name ?? null;
        update({ status, statusError: false });
        // The tunnel may have changed elsewhere (CLI, watchdog): keep the list in sync.
        if (prevActive !== nowActive && state.configsLoaded) loadConfigs();
    } catch (err) {
        if (err.status !== 401) update({ statusError: true });
    }
}

export async function loadConfigs() {
    try {
        const { configs } = await api.configs();
        update({ configs: configs || [], configsLoaded: true });
    } catch (err) {
        toastError(err);
    }
}

export async function loadEvents() {
    try {
        const { events } = await api.events(50);
        update({ events: events || [] });
    } catch (err) {
        if (err.status !== 401) toastError(err);
    }
}

export async function loadSettings() {
    try {
        update({ settings: await api.settings() });
    } catch (err) {
        toastError(err);
    }
}

export async function loadProton() {
    try {
        update({ proton: await api.proton() });
    } catch (err) {
        if (err.status !== 401) toastError(err);
    }
}

export async function refreshAll() {
    await Promise.all([loadStatus(), loadConfigs(), loadEvents(), loadSettings(), loadProton()]);
}

// ------------------------------------------------------------------- tunnel

async function afterTunnelChange() {
    await Promise.all([loadStatus(), loadConfigs(), loadEvents()]);
}

function announceDeployed(cfg) {
    infoDialog({
        title: t('missionUpdated'),
        lines: [t('deployedTo', { name: labelOf(cfg) }), t('restartGame'), t('newLobbies')],
    });
}

export function tunnelUp() {
    return withBusy('tunnel', async () => {
        try {
            const { config } = await api.up();
            await afterTunnelChange();
            announceDeployed(config);
        } catch (err) {
            toastError(err);
            afterTunnelChange();
        }
    });
}

export function tunnelDown() {
    return withBusy('tunnel', async () => {
        try {
            await api.down();
            toast(t('disconnected'));
        } catch (err) {
            toastError(err);
        }
        await afterTunnelChange();
    });
}

export function deploy(cfg) {
    return withBusy('tunnel', async () => {
        try {
            const { config } = await api.connect(cfg.name);
            await afterTunnelChange();
            announceDeployed(config);
        } catch (err) {
            toastError(err);
            afterTunnelChange();
        }
    });
}

// ------------------------------------------------------------------ configs

function replaceConfig(updated) {
    update({ configs: state.configs.map((c) => (c.name === updated.name ? updated : c)) });
}

export function toggleFavorite(cfg) {
    return withBusy(`fav:${cfg.name}`, async () => {
        try {
            replaceConfig(await api.patchConfig(cfg.name, { favorite: !cfg.favorite }));
        } catch (err) {
            toastError(err);
        }
    });
}

export async function rename(cfg) {
    const value = await promptDialog({
        title: t('renameTitle'),
        message: t('renameHelp', { name: cfg.name }),
        value: cfg.display_name || '',
        placeholder: cfg.name,
        maxlength: 64,
    });
    if (value === undefined) return;
    await withBusy(`cfg:${cfg.name}`, async () => {
        try {
            replaceConfig(await api.patchConfig(cfg.name, { display_name: value.trim() }));
            toast(t('renamed'));
            if (state.status?.config?.name === cfg.name) loadStatus();
        } catch (err) {
            toastError(err);
        }
    });
}

export async function remove(cfg) {
    const ok = await confirmDialog({
        title: t('deleteTitle'),
        message: cfg.active ? t('deleteActiveConfirm', { name: labelOf(cfg) }) : t('deleteConfirm', { name: labelOf(cfg) }),
        confirmLabel: t('delete'),
        danger: true,
    });
    if (!ok) return;
    await withBusy(`cfg:${cfg.name}`, async () => {
        try {
            await api.deleteConfig(cfg.name);
            toast(t('deleted'));
        } catch (err) {
            toastError(err);
        }
        await Promise.all([loadConfigs(), loadStatus(), loadEvents(), loadSettings(), loadProton()]);
    });
}

export function measureLatency() {
    return withBusy('latency', async () => {
        try {
            const { configs } = await api.latency();
            update({ configs: configs || [] });
            toast(t('latencyDone'));
        } catch (err) {
            toastError(err);
        }
    });
}

export function uploadFiles(fileList) {
    const files = [...fileList].filter((f) => f && f.name);
    if (!files.length) return undefined;
    const accepted = files.filter((f) => /\.(conf|zip)$/i.test(f.name));
    const rejected = files
        .filter((f) => !accepted.includes(f))
        .map((f) => ({ file: f.name, error: t('badExtension') }));
    if (!accepted.length) {
        update({ uploadReport: { imported: 0, errors: rejected } });
        return undefined;
    }
    return withBusy('upload', async () => {
        try {
            const res = await api.upload(accepted);
            const imported = (res.imported || []).length;
            update({ uploadReport: { imported, errors: [...rejected, ...(res.errors || [])] } });
            toast(t('importedCount', { n: imported }));
        } catch (err) {
            if (err.errors?.length || rejected.length) {
                update({ uploadReport: { imported: 0, errors: [...rejected, ...(err.errors || [])], message: err.message } });
                if (err.status === 401) return;
                toast(err.message || t('importFailed'), 'error');
            } else {
                toastError(err);
            }
        }
        await Promise.all([loadConfigs(), loadEvents(), loadProton()]);
    });
}

export async function openEditor(cfg) {
    update({ modal: { type: 'editor', name: cfg.name, label: labelOf(cfg), loading: true, text: '' } });
    try {
        const data = await api.config(cfg.name);
        if (state.modal?.type === 'editor' && state.modal.name === cfg.name) {
            update({ modal: { ...state.modal, loading: false, text: data.text || '' } });
        }
    } catch (err) {
        toastError(err);
        update({ modal: null });
    }
}

export function saveEditor(text) {
    const m = state.modal;
    if (!m || m.type !== 'editor') return undefined;
    return withBusy('editor', async () => {
        try {
            const updated = await api.putText(m.name, text);
            replaceConfig(updated);
            update({ modal: null });
            toast(t('configSaved'));
            await Promise.all([loadStatus(), loadEvents()]);
        } catch (err) {
            toastError(err);
        }
    });
}

// ------------------------------------------------------------------- events

export async function clearEvents() {
    const ok = await confirmDialog({ title: t('clearLogTitle'), message: t('clearLogConfirm'), confirmLabel: t('clear'), danger: true });
    if (!ok) return;
    try {
        await api.clearEvents();
        update({ events: [] });
        toast(t('logCleared'));
    } catch (err) {
        toastError(err);
    }
}

// ----------------------------------------------------------------- settings

export function savePrefs(patch) {
    return withBusy('prefs', async () => {
        try {
            const { prefs } = await api.putPrefs(patch);
            if (state.settings) update({ settings: { ...state.settings, prefs } });
            toast(t('settingsSaved'));
        } catch (err) {
            toastError(err);
            await loadSettings(); // revert toggles to the server truth
        }
    });
}

export function saveDevices(devices) {
    return withBusy('devices', async () => {
        try {
            const res = await api.putDevices(devices);
            if (state.settings) update({ settings: { ...state.settings, devices: res.devices } });
            toast(t('devicesSaved'));
            loadStatus();
            return true;
        } catch (err) {
            toastError(err);
            return false;
        }
    });
}

export function changePassword(current, next) {
    return withBusy('password', async () => {
        try {
            await api.changePassword(current, next);
            toast(t('passwordChanged'));
            return true;
        } catch (err) {
            toastError(err);
            return false;
        }
    });
}

export function runDoctor() {
    return withBusy('doctor', async () => {
        try {
            update({ doctor: await api.doctor() });
        } catch (err) {
            toastError(err);
        }
    });
}

export function updateGeoip() {
    return withBusy('geoip', async () => {
        try {
            const res = await api.geoipUpdate();
            if (res.updated) toast(t('geoipUpdated'));
            else toast(res.available ? t('geoipFailedKept') : t('geoipFailed'), 'error');
            await Promise.all([loadConfigs(), state.doctor ? api.doctor().then((d) => update({ doctor: d })) : null]);
        } catch (err) {
            toastError(err);
        }
    });
}
