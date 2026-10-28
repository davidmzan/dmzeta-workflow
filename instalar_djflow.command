#!/bin/bash
# Instala lo necesario y crea "Dmzeta Workflow.app" en el Escritorio (doble clic para abrir la app).
cd "$(dirname "$0")" || exit 1
DIR="$(pwd)"
echo "== Dmzeta Workflow: instalación =="
if ! command -v python3 >/dev/null; then echo "Falta Python 3. Instálalo desde python.org y vuelve a ejecutar esto."; exit 1; fi
if ! command -v ffmpeg >/dev/null; then
  if command -v brew >/dev/null; then echo "Instalando ffmpeg..."; brew install ffmpeg
  else echo "Falta ffmpeg. Instala Homebrew (brew.sh) y luego ejecuta: brew install ffmpeg"; fi
fi
python3 -c "import numpy" 2>/dev/null || python3 -m pip install numpy || python3 -m pip install --break-system-packages numpy

rm -rf "$HOME/Desktop/DJFlow.app"
APP="$HOME/Desktop/Dmzeta Workflow.app"
rm -rf "$APP"; mkdir -p "$APP/Contents/MacOS"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>Dmzeta Workflow</string>
<key>CFBundleDisplayName</key><string>Dmzeta Workflow</string>
<key>CFBundleExecutable</key><string>djflow</string>
<key>CFBundleIdentifier</key><string>com.djflow.workflow</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleVersion</key><string>1.0</string>
<key>LSUIElement</key><false/>
</dict></plist>
PLIST
PYBIN="$(python3 -c 'import sys;print(sys.executable)')"
echo "Python usado: $PYBIN"
cat > "$APP/Contents/MacOS/djflow" <<LAUNCH
#!/bin/zsh
cd "$DIR"
exec /usr/bin/open -a Terminal "$DIR/djflow.command"
LAUNCH
chmod +x "$APP/Contents/MacOS/djflow"
xattr -dr com.apple.quarantine "$APP" 2>/dev/null
echo ""
echo "Listo. Tienes "Dmzeta Workflow.app" en el Escritorio. Si macOS lo bloquea la primera vez: clic derecho > Abrir."
echo "No muevas la carpeta djflow de sitio (la app apunta a ella). Si la mueves, vuelve a ejecutar este instalador."
