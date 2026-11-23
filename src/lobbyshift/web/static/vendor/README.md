# Vendored third-party files

Served as-is by LobbyShift (no build step, no npm). The CSP (`script-src 'self'`)
forbids loading scripts from a CDN, so they are copied here at a pinned version.
Update by downloading the same paths at a new exact version and checking the
UI still works.

| File | Package / version | Source URL | License |
|------|-------------------|------------|---------|
| `lit-html.js` | lit-html 3.2.1 | https://cdn.jsdelivr.net/npm/lit-html@3.2.1/lit-html.js | BSD-3-Clause (`LICENSE-lit-html`) |
| `lit-html.js.map` | lit-html 3.2.1 (source map) | https://cdn.jsdelivr.net/npm/lit-html@3.2.1/lit-html.js.map | BSD-3-Clause |
| `twemoji.esm.js` | @twemoji/api 15.1.0 | https://cdn.jsdelivr.net/npm/@twemoji/api@15.1.0/dist/twemoji.esm.js | MIT (`LICENSE-twemoji`) |
| `LICENSE-lit-html` | lit-html 3.2.1 | https://cdn.jsdelivr.net/npm/lit-html@3.2.1/LICENSE | — |
| `LICENSE-twemoji` | @twemoji/api 15.1.0 | https://cdn.jsdelivr.net/npm/@twemoji/api@15.1.0/LICENSE | — |

SHA-256:

```
52315c7ed64b9c8d467dfcb4e55e5ec98d15c43b7c6149382118b74ea311b9d6  lit-html.js
34965ca7f27637c408063f572de95f5fa386e55c250098d191af6b6a6e5e390a  twemoji.esm.js
```

Notes:

- Only twemoji's `base` URL and `convert.toCodePoint()` are used, to build flag
  `<img>` URLs. `twemoji.parse()` is not used.
- The flag images themselves (Twemoji graphics, CC-BY 4.0, © Twitter, Inc. and
  other contributors) are loaded at runtime from
  `https://cdn.jsdelivr.net/gh/jdecked/twemoji@15.1.0/assets/svg/`, allowed by
  the CSP `img-src`. If the CDN is unreachable, the native emoji is shown.
