import { html, nothing } from '../../vendor/lit-html.js';
import { api } from '../api.js';
import { t } from '../i18n.js';
import { isBusy, update, withBusy } from '../state.js';
import { spinner } from '../ui.js';
import { headerView } from './header.js';

let loginError = '';

export function resetLoginError() {
    loginError = '';
}

export function loginView({ onSuccess }) {
    const busy = isBusy('login');
    const submit = (e) => {
        e.preventDefault();
        const form = e.currentTarget;
        const input = form.elements.namedItem('password');
        const password = input.value;
        if (!password) return;
        withBusy('login', async () => {
            try {
                await api.login(password);
                loginError = '';
                form.reset();
                await onSuccess();
            } catch (err) {
                if (err.status === 401) loginError = t('wrongPassword');
                else if (err.status === 429) loginError = t('tooManyAttempts');
                else if (err.status === 0) loginError = t('networkError');
                else loginError = err.message;
                update();
                input.select();
            }
        });
    };
    return html`<div class="container narrow">
        ${headerView()}
        <section class="card login-card">
            <div class="card-header"><span class="card-title">${t('loginTitle')}</span></div>
            <div class="card-body">
                <form class="login-form" @submit=${submit}>
                    <input type="text" name="username" autocomplete="username" value="admin" hidden>
                    <label class="setting-label" for="login-password">${t('password')}</label>
                    <input id="login-password" class="input" type="password" name="password" required
                        maxlength="256" autocomplete="current-password">
                    ${loginError ? html`<p class="form-error" role="alert">${loginError}</p>` : nothing}
                    <button type="submit" class="btn-primary" ?disabled=${busy}>${busy ? spinner() : nothing}${t('login')}</button>
                    <p class="help">${t('loginHelp')}</p>
                </form>
            </div>
        </section>
    </div>`;
}
