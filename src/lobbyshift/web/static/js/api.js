// Thin fetch wrapper: checks response.ok, normalises FastAPI error payloads
// and reports 401s so the app can fall back to the login screen.

export class ApiError extends Error {
    constructor(status, message, errors = []) {
        super(message);
        this.name = 'ApiError';
        this.status = status;
        // Per-file errors from uploads: [{file, error}]
        this.errors = errors;
    }
}

let unauthorizedHandler = () => {};

export function onUnauthorized(handler) {
    unauthorizedHandler = handler;
}

function describeDetail(detail, fallback) {
    if (typeof detail === 'string') return { message: detail, errors: [] };
    if (Array.isArray(detail)) {
        // FastAPI/pydantic validation errors: [{loc, msg, type}]
        const message = detail
            .map((d) => {
                const field = Array.isArray(d?.loc) ? d.loc.filter((p) => p !== 'body').join('.') : '';
                const msg = typeof d?.msg === 'string' ? d.msg : '';
                return field ? `${field}: ${msg}` : msg;
            })
            .filter(Boolean)
            .join('; ');
        return { message: message || fallback, errors: [] };
    }
    if (detail && typeof detail === 'object') {
        const errors = Array.isArray(detail.errors)
            ? detail.errors.map((e) => ({ file: String(e?.file ?? ''), error: String(e?.error ?? '') }))
            : [];
        return { message: typeof detail.message === 'string' ? detail.message : fallback, errors };
    }
    return { message: fallback, errors: [] };
}

/**
 * @param {string} method
 * @param {string} path  must start with /api/
 * @param {{json?: any, form?: FormData, auth?: boolean}} [opts]
 *        auth=false: a 401 is a normal answer (login form), not a session expiry.
 */
export async function request(method, path, { json, form, auth = true } = {}) {
    const init = { method, credentials: 'same-origin', headers: { Accept: 'application/json' } };
    if (json !== undefined) {
        init.headers['Content-Type'] = 'application/json';
        init.body = JSON.stringify(json);
    } else if (form) {
        init.body = form;
    }

    let response;
    try {
        response = await fetch(path, init);
    } catch {
        throw new ApiError(0, 'network');
    }

    let data = null;
    const type = response.headers.get('content-type') || '';
    if (type.includes('application/json')) {
        try {
            data = await response.json();
        } catch {
            data = null;
        }
    }

    if (!response.ok) {
        if (response.status === 401 && auth) unauthorizedHandler();
        const fallback = `HTTP ${response.status}`;
        const { message, errors } = describeDetail(data?.detail, fallback);
        throw new ApiError(response.status, message, errors);
    }
    return data ?? {};
}

const enc = encodeURIComponent;

export const api = {
    me: () => request('GET', '/api/auth/me', { auth: false }),
    login: (password) => request('POST', '/api/auth/login', { json: { password }, auth: false }),
    logout: () => request('POST', '/api/auth/logout', { auth: false }),
    changePassword: (current, next) => request('PUT', '/api/auth/password', { json: { current, new: next } }),

    status: () => request('GET', '/api/status'),
    up: () => request('POST', '/api/tunnel/up'),
    down: () => request('POST', '/api/tunnel/down'),
    connect: (name) => request('POST', `/api/tunnel/connect/${enc(name)}`),

    configs: () => request('GET', '/api/configs'),
    config: (name) => request('GET', `/api/configs/${enc(name)}`),
    upload: (files) => {
        const form = new FormData();
        for (const f of files) form.append('files', f, f.name);
        return request('POST', '/api/configs', { form });
    },
    putText: (name, text) => request('PUT', `/api/configs/${enc(name)}/text`, { json: { text } }),
    patchConfig: (name, fields) => request('PATCH', `/api/configs/${enc(name)}`, { json: fields }),
    deleteConfig: (name) => request('DELETE', `/api/configs/${enc(name)}`),
    latency: () => request('POST', '/api/latency', { json: {} }),

    events: (limit = 50) => request('GET', `/api/events?limit=${limit}`),
    clearEvents: () => request('DELETE', '/api/events'),

    settings: () => request('GET', '/api/settings'),
    putPrefs: (prefs) => request('PUT', '/api/settings/prefs', { json: prefs }),
    putDevices: (devices) => request('PUT', '/api/settings/devices', { json: { devices } }),

    doctor: () => request('GET', '/api/system/doctor'),
    geoipUpdate: () => request('POST', '/api/system/geoip/update'),
    proton: () => request('GET', '/api/providers/proton'),
};
