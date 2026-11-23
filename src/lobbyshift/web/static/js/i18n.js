// UI strings (en, de, fr, it, es live in ./locales/). t() returns plain text: values are always rendered as text nodes.

import { storage } from './storage.js';
import de from './locales/de.js';
import en from './locales/en.js';
import es from './locales/es.js';
import fr from './locales/fr.js';
import it from './locales/it.js';

export const LANGUAGES = [
    { code: 'en', label: 'EN' },
    { code: 'de', label: 'DE' },
    { code: 'fr', label: 'FR' },
    { code: 'it', label: 'IT' },
    { code: 'es', label: 'ES' },
];



const dictionaries = { en, de, fr, it, es };

function initialLang() {
    const saved = storage.get('lang');
    if (saved && dictionaries[saved]) return saved;
    const nav = (navigator.languages?.[0] || navigator.language || 'en').slice(0, 2).toLowerCase();
    return dictionaries[nav] ? nav : 'en';
}

let lang = initialLang();
document.documentElement.lang = lang;
const listeners = new Set();

export function getLang() {
    return lang;
}

export function setLang(code) {
    if (!dictionaries[code] || code === lang) return;
    lang = code;
    storage.set('lang', code);
    document.documentElement.lang = code;
    listeners.forEach((fn) => fn(code));
}

export function onLangChange(fn) {
    listeners.add(fn);
}

/** Translate key; {param} placeholders are replaced. Missing keys return the key itself. */
export function t(key, params) {
    let s = dictionaries[lang][key] ?? en[key];
    if (s === undefined) return key;
    if (params) s = s.replace(/\{(\w+)\}/g, (m, name) => (name in params ? String(params[name]) : m));
    return s;
}
