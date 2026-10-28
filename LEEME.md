# Dmzeta Workflow

La app se abre en una ventana propia (Chrome en modo app si lo tienes; si no, tu navegador). Todo corre en tu Mac, nada sale a internet.

## Instalación (una vez)
Copia estos archivos a ~/Desktop/djflow: djflow.py, workflow_server.py, workflow_ui.html, instalar_djflow.command, djflow.command. Después, en Terminal:

    cd ~/Desktop/djflow
    chmod +x instalar_djflow.command djflow.command
    xattr -dr com.apple.quarantine ~/Desktop/djflow
    ./instalar_djflow.command

Crea "Dmzeta Workflow.app" en el Escritorio. No muevas la carpeta djflow de sitio.

## Flujo diario
1. Descargar -> Platinum Notes -> Mixed In Key (con "escribir en etiquetas" activado).
2. Abrir Dmzeta Workflow -> "Elegir carpeta" -> revisar pista a pista escuchando la onda.
3. "Aplicar + generar cues".
4. En Rekordbox: Preferencias > Avanzado > Base de datos > Biblioteca importada = djflow_cues.xml, y arrastrar la playlist djflow a tu colección.

## Atajos
Espacio reproducir · Flechas arriba/abajo cambiar de pista · Izq/Der moverse 1 compás (Shift = 4) · S / E / L marcar START MIX, END MIX y loop · X quitar marcas · [ ] grid ±1 beat · , . grid ±10 ms · M clics · + − zoom · Enter marcar/desmarcar la pista.

La app se cierra sola unos segundos después de cerrar la ventana.

## Desarrollo: que no se rompa nada al tocar

- `./run_tests.command`: pasa 16 pruebas (nombres, grid con audio sintético, XML de cues, modelos, sintaxis de la interfaz). Tarda unos 3 s y no toca tus datos.
- `./guardar_version.command "qué cambié"`: guarda una versión en git solo si las pruebas pasan.
- Hay un hook `pre-commit` que ejecuta lo mismo antes de cada `git commit` (para saltarlo: `--no-verify`).
- Volver atrás: `git log --oneline` y `git checkout <versión> -- djflow.py workflow_server.py workflow_ui.html`.
- No se suben a git tus datos (caché, modelos, marcas, XML, audios): están en `.gitignore`.
- Si cambias algo que afecta al grid o al XML, añade una prueba en `tests/test_djflow.py` antes de guardar.
