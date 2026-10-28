#!/bin/bash
# Arranca la app. Usa el entorno aislado .venv si existe (creado por instalar_djflow.command).
cd "$(dirname "$0")" || exit 1
PY=python3; [ -x .venv/bin/python ] && PY=.venv/bin/python
exec "$PY" workflow_server.py
