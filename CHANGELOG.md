# Changelog

## Sin publicar

- Interfaz dividida en `ui/` (index.html + 6 css + 11 js), servida por una ruta estática restringida; CSP sin scripts inline de terceros.
- Aprendizaje ponderado: correcciones tuyas x3, aceptadas x0.5, sin revisar no se aprende; registro de reentrenos y panel de calidad (`/api/quality`).
- Pruebas de interfaz (`tests/test_ui.py`, `tests/ui_smoke.js`): 49 en total.

## Unreleased — robustness pass
- Engine split into layered modules (`djcore/`): config → storage → names → audio → grid → preview → features → models → prediction → training → cues → commands. `djflow.py` stays as a compatibility facade.
- Local server hardened: session token, origin/host checks, folder allow-list, validated config, body and range limits, security headers.
- Atomic writes for every shared state file.
- Data directory configurable with `DJFLOW_HOME` (tests run entirely in a temp directory).
- Test suite grew from 16 to 38: golden-file export snapshot, JS/Python name-grammar parity, API security tests, end-to-end flow (analyse → apply → cues → undo), static undefined-name check, layer-order check, no-personal-data check.
- GitHub Actions CI (Python 3.10 and 3.12).

## 0.1 — initial public version
- Naming grammar, learned predictions, beat grid with attack-start snap and per-file MP3 delay compensation, cue export, review UI.
