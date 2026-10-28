#!/bin/bash
# Publica el proyecto en https://github.com/davidmzan/dmzeta-workflow (privado).
# Antes del push: usa el email noreply de GitHub, deja un único commit limpio.
cd "$(dirname "$0")"
REPO="https://github.com/davidmzan/dmzeta-workflow.git"
pgrep -x git >/dev/null || { rm -f .git/*.lock .git/objects/maintenance.lock; find .git -name "tmp_obj_*" -delete 2>/dev/null; }

git config user.name "Dmzeta"
git config user.email "98977215+davidmzan@users.noreply.github.com"    # email público de GitHub: no expone tu Gmail

./run_tests.command || { echo "⛔ Las pruebas fallan: no se publica."; exit 1; }
git add -A
git commit --amend --reset-author -q -m "Dmzeta Workflow: DJ library prep with learned naming, beat grid and cue points" || exit 1
git branch -M main
git remote get-url origin >/dev/null 2>&1 || git remote add origin "$REPO"
echo "Autor del commit: $(git log -1 --format='%an <%ae>')"
git push -u origin main && echo "✅ Publicado: https://github.com/davidmzan/dmzeta-workflow"
