// localStorage can throw (private mode, blocked site data): never let it break the UI.

const PREFIX = 'lobbyshift.';

function get(key) {
    try {
        return window.localStorage.getItem(PREFIX + key);
    } catch {
        return null;
    }
}

function set(key, value) {
    try {
        window.localStorage.setItem(PREFIX + key, value);
    } catch {
        /* ignore */
    }
}

export const storage = {
    get,
    set,
    getJSON(key, fallback) {
        const raw = get(key);
        if (raw == null) return fallback;
        try {
            return JSON.parse(raw);
        } catch {
            return fallback;
        }
    },
    setJSON(key, value) {
        set(key, JSON.stringify(value));
    },
};
