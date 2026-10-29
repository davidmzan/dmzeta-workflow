# Changelog

## Sin publicar

- Botones ÷2 / ×2 junto al BPM (recalculan el grid). Corregido el 'Failed to fetch' al elegir otra carpeta: el servidor se cerraba por falta de pings con el navegador en segundo plano; ahora el límite es 10 min, se mide con reloj monotónico (dormir el Mac no cuenta), no cuenta mientras hay un diálogo abierto y el mensaje de error es claro.
- Al cambiar el BPM de una pista (p. ej. 82 → 164) el grid se recalcula solo con el nuevo tempo; cada corrección se anota (`bpm_fixes.json`, ignorado por git) y el panel de calidad muestra cuántas fueron ×2 / ×0,5.
- `pyproject.toml` (dependencias, comandos `dmzeta-workflow`, config de ruff y mypy), instalación en `.venv` aislado, CI con job de lint (ruff y mypy bloqueantes). Corregido: los errores de la ventana Tk no se mostraban (NameError en una lambda diferida).
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
