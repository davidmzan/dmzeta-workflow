"""Utilidades comunes de las pruebas: carpeta de datos temporal (DJFLOW_HOME) y audio sintético."""
import os, shutil, sys, tempfile, wave
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = os.environ.get('DJFLOW_HOME') or tempfile.mkdtemp(prefix='djflow_test_')
os.environ['DJFLOW_HOME'] = TMP                        # todos los datos de la app van a una carpeta temporal
import djflow as dj
assert dj.DATA == TMP, 'djflow se importó antes de fijar DJFLOW_HOME'


def make_track(path, bpm=120.0, first=0.37, seconds=40, sr=44100):
    """Pista sintética: bombos (golpes con ataque seco) en cada beat desde `first`."""
    n = int(seconds * sr); y = np.zeros(n, dtype=np.float64); beat = 60.0 / bpm; t = np.arange(int(0.18 * sr)) / sr
    kick = np.sin(2 * np.pi * (60 + 90 * np.exp(-t * 40)) * t) * np.exp(-t * 14)
    k = 0
    while first + k * beat < seconds - 0.3:
        i = int((first + k * beat) * sr); y[i:i + len(kick)] += kick[:n - i]; k += 1
    y += np.random.RandomState(1).randn(n) * 0.003
    y = (y / np.abs(y).max() * 0.8 * 32767).astype('<i2')
    with wave.open(path, 'wb') as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(y.tobytes())


def have_ffmpeg(): return shutil.which('ffmpeg') is not None


def tiny_xml(path):
    """XML mínimo con 25 pistas con cues, suficiente para que se aprendan las reglas A/B/C."""
    rows = []
    for i in range(25):
        rows.append(f'<TRACK TrackID="{i}" Name="Song {i} (8 Bars MOE) - 8A - 120" Artist="A" AverageBpm="120.00" Location="file://localhost/x/{i}.mp3">'
                    '<POSITION_MARK Name="" Type="0" Start="0.050" Num="0" Red="40" Green="226" Blue="20"/><POSITION_MARK Name="" Type="0" Start="8.050" Num="1" Red="40" Green="226" Blue="20"/>'
                    '<POSITION_MARK Name="" Type="0" Start="16.050" Num="2" Red="165" Green="225" Blue="22"/></TRACK>')
    open(path, 'w').write('<DJ_PLAYLISTS><COLLECTION Entries="25">' + ''.join(rows) + '</COLLECTION></DJ_PLAYLISTS>')


