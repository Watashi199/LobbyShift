import { html, nothing } from '../../vendor/lit-html.js';
import {
    changePassword, labelOf, runDoctor, saveDevices, savePrefs, updateGeoip,
} from '../actions.js';
import { t } from '../i18n.js';
import { isBusy, state, update } from '../state.js';
import { card, spinner, toast } from '../ui.js';

// Local drafts (not yet saved to the server).
let devicesDraft = null; // [{ip, name}] while editing
let autostartChoice = ''; // config picked while autostart is off

function toggle({ checked, disabled, onChange, label }) {
    return html`<label class="toggle">
        <span class="toggle-switch">
            <input type="checkbox" name="toggle" .checked=${Boolean(checked)} ?disabled=${disabled}
                @change=${(e) => {
                    // Controlled input: show the server's value, not the click, until saved.
                    const wanted = e.currentTarget.checked;
                    e.currentTarget.checked = !wanted;
                    onChange(wanted);
                }}>
            <span class="toggle-slider"></span>
        </span>
        <span class="toggle-status ${checked ? 'active' : 'inactive'}">${checked ? t('on') : t('off')}</span>
        <span class="toggle-label">${label}</span>
    </label>`;
}

function prefsGroup(s) {
    const prefs = s.prefs || {};
    const busy = isBusy('prefs');
    const selected = prefs.autostart ? prefs.autostart_config : autostartChoice;

    const onAutostart = (on) => {
        if (on && !selected) {
            toast(t('autostartPick'), 'error');
            update();
            return;
        }
        savePrefs(on ? { autostart: true, autostart_config: selected } : { autostart: false });
    };
    const onPick = (e) => {
        autostartChoice = e.currentTarget.value;
        if (prefs.autostart && autostartChoice) savePrefs({ autostart_config: autostartChoice });
        update();
    };

    return html`<div class="setting-group">
        <h4>🚀 ${t('autostartConfig')}</h4>
        <div class="setting-row">
            ${toggle({ checked: prefs.autostart, disabled: busy, onChange: onAutostart, label: t('autostartLabel') })}
        </div>
        <div class="setting-row">
            <label class="setting-label" for="autostart-config">${t('region')}</label>
            <select id="autostart-config" name="autostart_config" class="setting-select" ?disabled=${busy} @change=${onPick}>
                <option value="" ?selected=${!selected}>${t('selectConfig')}</option>
                ${state.configs.map((c) => html`<option value=${c.name} ?selected=${c.name === selected}>${labelOf(c)}</option>`)}
            </select>
        </div>
        <p class="help">${t('autostartInfo')}</p>

        <h4>🛡 ${t('protection')}</h4>
        <div class="setting-row">
            ${toggle({ checked: prefs.kill_switch, disabled: busy, onChange: (v) => savePrefs({ kill_switch: v }), label: t('killSwitch') })}
        </div>
        <p class="help">${t('killSwitchHelp')}</p>
        <div class="setting-row">
            ${toggle({ checked: prefs.auto_reconnect, disabled: busy, onChange: (v) => savePrefs({ auto_reconnect: v }), label: t('autoReconnect') })}
        </div>
        <p class="help">${t('autoReconnectHelp')}</p>
    </div>`;
}

function devicesGroup(s) {
    const editing = devicesDraft !== null;
    const rows = editing ? devicesDraft : s.devices || [];
    const busy = isBusy('devices');

    const edit = () => {
        devicesDraft = (s.devices || []).map((d) => ({ ip: d.ip, name: d.name || '' }));
        if (!devicesDraft.length) devicesDraft.push({ ip: '', name: '' });
        update();
    };
    const cancel = () => {
        devicesDraft = null;
        update();
    };
    const setField = (i, field) => (e) => {
        devicesDraft[i] = { ...devicesDraft[i], [field]: e.currentTarget.value };
    };
    const addRow = () => {
        devicesDraft.push({ ip: '', name: '' });
        update();
    };
    const removeRow = (i) => () => {
        devicesDraft.splice(i, 1);
        update();
    };
    const save = async () => {
        const devices = devicesDraft
            .map((d) => ({ ip: d.ip.trim(), name: d.name.trim() }))
            .filter((d) => d.ip);
        const bad = devices.find((d) => !/^\d{1,3}(\.\d{1,3}){3}$/.test(d.ip));
        if (bad) {
            toast(t('invalidIp', { ip: bad.ip }), 'error');
            return;
        }
        if (await saveDevices(devices)) {
            devicesDraft = null;
            update();
        }
    };

    return html`<div class="setting-group">
        <h4>🎮 ${t('devices')}</h4>
        <p class="help">${t('devicesHelp')}</p>
        ${s.lan ? html`<p class="help">${t('lanSubnet')}: <code>${s.lan.subnet}</code> (${s.lan.interface}) · ${t('gateway')}: <code>${s.lan.address}</code></p>` : nothing}
        ${editing
            ? html`<div class="device-list">
                ${rows.map((d, i) => html`<div class="device-row">
                    <input class="input mono" type="text" name="ip" inputmode="decimal" maxlength="15" placeholder="192.168.1.50"
                        aria-label=${t('deviceIp')} .value=${d.ip} @input=${setField(i, 'ip')}>
                    <input class="input" type="text" name="device_name" maxlength="64" placeholder=${t('deviceNamePlaceholder')}
                        aria-label=${t('deviceName')} .value=${d.name} @input=${setField(i, 'name')}>
                    <button type="button" class="btn-secondary btn-small" aria-label=${t('remove')} @click=${removeRow(i)}>✕</button>
                </div>`)}
              </div>
              <div class="settings-actions">
                <button type="button" class="btn-secondary" ?disabled=${rows.length >= 64} @click=${addRow}>+ ${t('addDevice')}</button>
                <button type="button" class="btn-primary" ?disabled=${busy} @click=${save}>${busy ? spinner() : nothing}${t('save')}</button>
                <button type="button" class="btn-secondary" @click=${cancel}>${t('cancel')}</button>
              </div>`
            : html`${rows.length
                ? html`<ul class="device-view">${rows.map((d) => html`<li><code>${d.ip}</code> ${d.name ? html`<span>${d.name}</span>` : nothing}</li>`)}</ul>`
                : html`<p class="banner banner-info">${t('devicesAllLan')}</p>`}
              <div class="settings-actions">
                <button type="button" class="btn-primary" @click=${edit}>${t('editDevices')}</button>
              </div>`}
    </div>`;
}

function rangesGroup(s) {
    const ranges = s.routed_ranges || [];
    return html`<div class="setting-group">
        <h4>🧭 ${t('routedRanges')}</h4>
        <p class="help">${t('routedRangesHelp')}</p>
        <details class="ranges">
            <summary>${t('showRanges', { n: ranges.length })}</summary>
            <div class="range-chips">${ranges.map((r) => html`<code>${r}</code>`)}</div>
        </details>
    </div>`;
}

function passwordGroup() {
    const busy = isBusy('password');
    const submit = async (e) => {
        e.preventDefault();
        const form = e.currentTarget;
        const current = form.elements.namedItem('current').value;
        const next = form.elements.namedItem('new').value;
        const confirm = form.elements.namedItem('confirm').value;
        if (next.length < 8) return toast(t('passwordTooShort'), 'error');
        if (next !== confirm) return toast(t('passwordMismatch'), 'error');
        if (await changePassword(current, next)) form.reset();
        return undefined;
    };
    return html`<div class="setting-group">
        <h4>🔑 ${t('changePassword')}</h4>
        <form class="password-form" @submit=${submit}>
            <input type="text" name="username" autocomplete="username" value="admin" hidden>
            <input class="input" type="password" name="current" required autocomplete="current-password" placeholder=${t('currentPassword')} aria-label=${t('currentPassword')}>
            <input class="input" type="password" name="new" required minlength="8" maxlength="256" autocomplete="new-password" placeholder=${t('newPassword')} aria-label=${t('newPassword')}>
            <input class="input" type="password" name="confirm" required minlength="8" maxlength="256" autocomplete="new-password" placeholder=${t('confirmPassword')} aria-label=${t('confirmPassword')}>
            <button type="submit" class="btn-primary" ?disabled=${busy}>${busy ? spinner() : nothing}${t('changePassword')}</button>
        </form>
    </div>`;
}

function doctorGroup() {
    const d = state.doctor;
    return html`<div class="setting-group">
        <h4>🩺 ${t('systemCheck')}</h4>
        <div class="settings-actions">
            <button type="button" class="btn-primary" ?disabled=${isBusy('doctor')} @click=${runDoctor}>
                ${isBusy('doctor') ? spinner() : nothing}${t('runChecks')}</button>
            <button type="button" class="btn-secondary" ?disabled=${isBusy('geoip')} @click=${updateGeoip}>
                ${isBusy('geoip') ? spinner() : nothing}${t('updateGeoip')}</button>
        </div>
        ${d
            ? html`<ul class="checks">
                ${d.checks.map((c) => html`<li class=${c.ok ? 'ok' : 'fail'}>
                    <span class="check-mark">${c.ok ? 'OK' : '!!'}</span>
                    <span class="check-name">${c.check}</span>
                    ${c.detail ? html`<span class="check-detail mono">${c.detail}</span>` : nothing}
                </li>`)}
              </ul>
              <p class=${d.ok ? 'help ok-text' : 'help fail-text'}>${d.ok ? t('allChecksOk') : t('someChecksFailed')}</p>`
            : nothing}
    </div>`;
}

export function settingsView() {
    const s = state.settings;
    const body = s
        ? html`<div class="settings-form">
            ${prefsGroup(s)}
            ${devicesGroup(s)}
            ${rangesGroup(s)}
            ${passwordGroup()}
            ${doctorGroup()}
          </div>`
        : html`<p class="empty">${spinner()}</p>`;
    return card({ key: 'settings', title: t('settings'), body });
}
