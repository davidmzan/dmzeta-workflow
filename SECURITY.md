# Security notes

Dmzeta Workflow is a **local** tool: it runs an HTTP server on `127.0.0.1` for its own browser window and never talks to the internet.

What the server enforces (all covered by `tests/test_server.py`):

- **Session token.** A random token is generated at start-up and injected into the page it serves. Every API call and every audio request must send it in `X-WF-Token`, so a web page opened in another tab cannot drive the server.
- **Origin checks.** Requests with a foreign `Origin`, a `Sec-Fetch-Site: cross-site` header or a non-local `Host` (DNS rebinding) are refused. POST bodies must be `application/json` and are capped at 10 MB.
- **Folder allow-list.** Only folders you picked in the native dialog (or saved in the config) can be read or modified. Audio is served only from those folders, only for known audio extensions, with strict path and `Range` validation.
- **Validated settings.** `/api/cfg` ignores unknown keys and clamps or rejects values with the wrong type or range.
- **Hardened responses.** CSP (`default-src 'none'`), `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cross-Origin-Resource-Policy: same-origin`.
- **Safe writes.** Models, preferences, marks, the done-registry and the exported XML are written atomically (temporary file + rename), so a crash never leaves a half-written state file.
- **No personal data in git.** `.gitignore` plus a test that fails if audio, models, collection XML or config files get tracked.

Reporting an issue: open a private security advisory on the repository.
