import { html } from '../../vendor/lit-html.js';
import { saveEditor } from '../actions.js';
import { t } from '../i18n.js';
import { isBusy } from '../state.js';
import { closeModal, modalFrame, registerModal, spinner } from '../ui.js';

function editorView(m) {
    const busy = isBusy('editor');
    const submit = (e) => {
        e.preventDefault();
        saveEditor(e.currentTarget.elements.namedItem('text').value);
    };
    return modalFrame({
        wide: true,
        title: `${t('editConfig')} · ${m.label}`,
        body: m.loading
            ? html`<p class="empty">${spinner()}</p>`
            : html`<form id="editor-form" @submit=${submit}>
                <p class="help">${t('editorHelp')}</p>
                <textarea name="text" class="editor" spellcheck="false" autocapitalize="off" autocomplete="off"
                    maxlength="65536" .value=${m.text} aria-label=${t('editConfig')}></textarea>
              </form>`,
        footer: html`
            <button type="submit" form="editor-form" class="btn-primary" ?disabled=${m.loading || busy}>
                ${busy ? spinner() : ''}${t('save')}</button>
            <button type="button" class="btn-secondary" @click=${() => closeModal(undefined)}>${t('cancel')}</button>`,
    });
}

registerModal('editor', editorView);
