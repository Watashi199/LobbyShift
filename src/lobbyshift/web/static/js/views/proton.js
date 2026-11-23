import { html, nothing } from '../../vendor/lit-html.js';
import { countryName } from '../format.js';
import { t } from '../i18n.js';
import { state } from '../state.js';
import { card, flag } from '../ui.js';

const OPTION_ORDER = ['platform', 'netshield', 'moderate_nat', 'vpn_accelerator', 'port_forwarding', 'secure_core'];

function safeHttpsUrl(value) {
    try {
        const url = new URL(String(value));
        return url.protocol === 'https:' ? url.href : null;
    } catch {
        return null;
    }
}

function optionValue(value) {
    const v = String(value);
    const key = `value_${v.toLowerCase()}`;
    const translated = t(key);
    return translated === key ? v : translated;
}

export function protonView() {
    const p = state.proton;
    const accountUrl = safeHttpsUrl(p?.account_url);
    const rec = p?.recommended || {};
    const keys = [...OPTION_ORDER.filter((k) => k in rec), ...Object.keys(rec).filter((k) => !OPTION_ORDER.includes(k))];

    const body = html`
        <p>${t('protonIntro')}</p>
        <ol class="steps">
            <li>${t('protonStep1')}
                ${accountUrl
                    ? html` <a href=${accountUrl} target="_blank" rel="noopener noreferrer">${t('protonAccountLink')} ↗</a>`
                    : nothing}</li>
            <li>${t('protonStep2')}</li>
            <li>${t('protonStep3')}</li>
            <li>${t('protonStep4')}</li>
        </ol>
        ${keys.length
            ? html`<table class="options-table">
                <thead><tr><th>${t('option')}</th><th>${t('recommended')}</th></tr></thead>
                <tbody>${keys.map((k) => html`<tr>
                    <td>${t(`opt_${k}`) === `opt_${k}` ? k : t(`opt_${k}`)}<div class="muted small">${t(`optHelp_${k}`) === `optHelp_${k}` ? '' : t(`optHelp_${k}`)}</div></td>
                    <td class="strong">${optionValue(rec[k])}</td>
                </tr>`)}</tbody>
              </table>`
            : nothing}
        <div class="banner banner-info">${t('protonOneKey')}</div>
        ${p?.configs
            ? html`<p class="muted small">${t('protonImported', { n: p.configs })}
                ${(p.countries || []).map((c) => html`<span class="country-chip" title=${countryName(c)}>${flag(c)}</span>`)}</p>`
            : nothing}`;

    return card({ key: 'proton', title: t('protonTitle'), body });
}
