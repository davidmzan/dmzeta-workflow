#!/bin/bash
# Guarda una versión en git SOLO si las pruebas pasan.  Uso: ./guardar_version.command "qué he cambiado"
cd "$(dirname "$0")"
# limpia bloqueos huérfanos de git (si no hay otro git en marcha)
pgrep -x git >/dev/null || { rm -f .git/*.lock .git/objects/maintenance.lock; find .git -name "tmp_obj_*" -delete 2>/dev/null; }
MSG="${1:-}"; if [ -z "$MSG" ]; then read -r -p "Qué has cambiado: " MSG; fi
bash ./run_tests.command || { echo "⛔ Las pruebas fallan: no se guarda la versión."; exit 1; }
git add -A && git commit -m "$MSG" && echo "✅ Versión guardada: $MSG"
