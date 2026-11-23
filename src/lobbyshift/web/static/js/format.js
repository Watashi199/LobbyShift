// Formatting helpers. All return plain strings (rendered as text, never HTML).

import { getLang, t } from './i18n.js';

export function humanBytes(n) {
    const value = Number(n) || 0;
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let i = 0;
    let v = value;
    while (v >= 1024 && i < units.length - 1) {
        v /= 1024;
        i++;
    }
    const digits = i === 0 || v >= 100 ? 0 : 1;
    return `${v.toFixed(digits)} ${units[i]}`;
}

/** Seconds -> "45s", "3m 12s", "2h 05m", "3d 4h". */
export function humanDuration(seconds) {
    if (seconds == null || !Number.isFinite(seconds)) return '-';
    const s = Math.max(0, Math.round(seconds));
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60);
    if (m < 60) return `${m}m ${String(s % 60).padStart(2, '0')}s`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ${String(m % 60).padStart(2, '0')}m`;
    return `${Math.floor(h / 24)}d ${h % 24}h`;
}

export function formatDateTime(value) {
    if (value == null) return '-';
    const date = typeof value === 'number' ? new Date(value * 1000) : new Date(value);
    if (Number.isNaN(date.getTime())) return '-';
    return date.toLocaleString(getLang(), {
        month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
}

export function formatTime(epochSeconds) {
    if (epochSeconds == null) return '-';
    return new Date(epochSeconds * 1000).toLocaleTimeString(getLang(), { hour: '2-digit', minute: '2-digit' });
}

// ---------------------------------------------------------------- countries

const CODE_RE = /^[A-Z]{2}$/;

export function normalizeCode(code) {
    const c = String(code || '').toUpperCase();
    if (c === 'UK') return 'GB';
    return CODE_RE.test(c) ? c : null;
}

/** Country code -> flag emoji (regional indicators), globe if unknown. */
export function flagEmoji(code) {
    const c = normalizeCode(code);
    if (!c) return '\u{1F310}';
    return String.fromCodePoint(...[...c].map((ch) => 0x1f1e6 + ch.charCodeAt(0) - 65));
}

const displayNamesCache = new Map();

export function countryName(code) {
    const c = normalizeCode(code);
    if (!c) return t('unknownCountry');
    const lang = getLang();
    let names = displayNamesCache.get(lang);
    if (names === undefined) {
        try {
            names = new Intl.DisplayNames([lang], { type: 'region' });
        } catch {
            names = null;
        }
        displayNamesCache.set(lang, names);
    }
    try {
        return names?.of(c) || c;
    } catch {
        return c;
    }
}

// A representative timezone per country (capital or main gaming hub).
// Multi-zone countries (US, CA, BR, AU, RU, MX) use their most populated zone.
const TIMEZONES = {
    AE: 'Asia/Dubai', AL: 'Europe/Tirane', AM: 'Asia/Yerevan', AR: 'America/Argentina/Buenos_Aires',
    AT: 'Europe/Vienna', AU: 'Australia/Sydney', AZ: 'Asia/Baku', BA: 'Europe/Sarajevo',
    BD: 'Asia/Dhaka', BE: 'Europe/Brussels', BG: 'Europe/Sofia', BH: 'Asia/Bahrain',
    BO: 'America/La_Paz', BR: 'America/Sao_Paulo', BY: 'Europe/Minsk', CA: 'America/Toronto',
    CH: 'Europe/Zurich', CL: 'America/Santiago', CN: 'Asia/Shanghai', CO: 'America/Bogota',
    CR: 'America/Costa_Rica', CY: 'Asia/Nicosia', CZ: 'Europe/Prague', DE: 'Europe/Berlin',
    DK: 'Europe/Copenhagen', DO: 'America/Santo_Domingo', DZ: 'Africa/Algiers', EC: 'America/Guayaquil',
    EE: 'Europe/Tallinn', EG: 'Africa/Cairo', ES: 'Europe/Madrid', FI: 'Europe/Helsinki',
    FR: 'Europe/Paris', GB: 'Europe/London', GE: 'Asia/Tbilisi', GH: 'Africa/Accra',
    GR: 'Europe/Athens', GT: 'America/Guatemala', HK: 'Asia/Hong_Kong', HN: 'America/Tegucigalpa',
    HR: 'Europe/Zagreb', HU: 'Europe/Budapest', ID: 'Asia/Jakarta', IE: 'Europe/Dublin',
    IL: 'Asia/Jerusalem', IN: 'Asia/Kolkata', IQ: 'Asia/Baghdad', IS: 'Atlantic/Reykjavik',
    IT: 'Europe/Rome', JM: 'America/Jamaica', JO: 'Asia/Amman', JP: 'Asia/Tokyo',
    KE: 'Africa/Nairobi', KH: 'Asia/Phnom_Penh', KR: 'Asia/Seoul', KW: 'Asia/Kuwait',
    KZ: 'Asia/Almaty', LB: 'Asia/Beirut', LK: 'Asia/Colombo', LT: 'Europe/Vilnius',
    LU: 'Europe/Luxembourg', LV: 'Europe/Riga', MA: 'Africa/Casablanca', MD: 'Europe/Chisinau',
    ME: 'Europe/Podgorica', MK: 'Europe/Skopje', MN: 'Asia/Ulaanbaatar', MO: 'Asia/Macau',
    MT: 'Europe/Malta', MX: 'America/Mexico_City', MY: 'Asia/Kuala_Lumpur', NG: 'Africa/Lagos',
    NL: 'Europe/Amsterdam', NO: 'Europe/Oslo', NP: 'Asia/Kathmandu', NZ: 'Pacific/Auckland',
    OM: 'Asia/Muscat', PA: 'America/Panama', PE: 'America/Lima', PH: 'Asia/Manila',
    PK: 'Asia/Karachi', PL: 'Europe/Warsaw', PR: 'America/Puerto_Rico', PT: 'Europe/Lisbon',
    PY: 'America/Asuncion', QA: 'Asia/Qatar', RO: 'Europe/Bucharest', RS: 'Europe/Belgrade',
    RU: 'Europe/Moscow', SA: 'Asia/Riyadh', SE: 'Europe/Stockholm', SG: 'Asia/Singapore',
    SI: 'Europe/Ljubljana', SK: 'Europe/Bratislava', SV: 'America/El_Salvador', TH: 'Asia/Bangkok',
    TN: 'Africa/Tunis', TR: 'Europe/Istanbul', TW: 'Asia/Taipei', UA: 'Europe/Kyiv',
    US: 'America/New_York', UY: 'America/Montevideo', UZ: 'Asia/Tashkent', VE: 'America/Caracas',
    VN: 'Asia/Ho_Chi_Minh', ZA: 'Africa/Johannesburg',
};

export function timezoneFor(code) {
    const c = normalizeCode(code);
    return c ? TIMEZONES[c] || null : null;
}

/** Local wall-clock time in the region's country, or null if unknown. */
export function localTimeFor(code, { seconds = false } = {}) {
    const tz = timezoneFor(code);
    if (!tz) return null;
    try {
        return new Date().toLocaleTimeString(getLang(), {
            timeZone: tz, hour: '2-digit', minute: '2-digit',
            ...(seconds ? { second: '2-digit' } : {}), hour12: false,
        });
    } catch {
        return null;
    }
}

export function latencyClass(ms) {
    if (ms == null) return 'none';
    if (ms < 50) return 'good';
    if (ms < 100) return 'fair';
    return 'bad';
}
