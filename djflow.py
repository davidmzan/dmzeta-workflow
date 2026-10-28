#!/usr/bin/env python3
"""
djflow: prepara y nombra tu música ANTES de importarla a Rekordbox, aprendiendo de TU biblioteca.

  python3 djflow.py train       <carpeta> [<carpeta>...]   # aprende nombres de tus pistas ya ordenadas + informe
  python3 djflow.py train-marks <rekordbox.xml>            # aprende dónde pones START MIX (necesita los audios del XML)
  python3 djflow.py analyze     <carpeta> [rekordbox.xml]  # propone nombres (+duplicados, START MIX) -> review.csv
  python3 djflow.py apply       <carpeta>                  # renombra y limpia tags (solo filas con "final"); guarda copia
  python3 djflow.py undo                                   # deshace la última tanda aplicada
  python3 djflow.py cues        <rekordbox.xml> <carpeta>  # genera djflow_cues.xml (INTRO, hot cues A/B/C, START/END MIX, loop)
  python3 djflow.py clean       <carpeta>                  # solo limpia tags

Requisitos: Python 3 con tkinter (ventana), numpy y ffmpeg (brew install ffmpeg ; pip3 install numpy)
Nombre estándar:  Título (Mashup)(N Bars POE|MOE|FME | Aca Starter)(In Aca|In Hype)(Short Edit)(Aca Out) - TONO - BPM
"""
# Fachada: reexporta todo el motor (djcore/*) con los mismos nombres de siempre, para que workflow_server.py, djflow_app.py,
# los scripts y las pruebas sigan funcionando igual. El código real vive en djcore/.
import importlib, sys

_LAYERS = ('config', 'storage', 'names', 'audio', 'grid', 'preview', 'features', 'models', 'prediction', 'training', 'cues', 'commands')
for _m in _LAYERS:
    _mod = importlib.import_module(f'djcore.{_m}')
    for _k, _v in vars(_mod).items():
        if not _k.startswith('__') and _k not in ('sys', 'os', 're', 'csv', 'json', 'time', 'shutil', 'hashlib', 'subprocess', 'np'):
            globals()[_k] = _v

from djcore.commands import main

def cli():
    main(sys.argv, __doc__)


if __name__ == '__main__':
    cli()
