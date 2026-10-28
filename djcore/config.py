"""Rutas, constantes y parámetros compartidos. Es la única capa que no importa ninguna otra."""
import os
import numpy as np

SR = 22050; N_FFT = 2048; HOP = 512

EXT = ('.mp3', '.m4a', '.flac', '.wav', '.aif', '.aiff')

CANDS = [4, 8, 16, 24, 32]

TYPES = ['MOE', 'POE', 'FME']

FR = np.fft.rfftfreq(N_FFT, 1 / SR)

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # carpeta del código (la que contiene djflow.py)

DATA = os.path.abspath(os.environ.get('DJFLOW_HOME') or HERE)         # carpeta de datos (modelos, caché, historial); por defecto, junto al código

MODEL_PATH = os.path.join(DATA, 'model.npz')

LEARN_DIR = os.path.join(DATA, 'learned')

HIST_DIR = os.path.join(DATA, 'history')

BACKUP_DIR = os.path.join(DATA, 'backup')

MARKS_FILE = 'djflow_marks.json'

DONE_FILE = os.path.join(DATA, 'done.json')

PREFS_FILE = os.path.join(DATA, 'prefs.json')

LEARN_MARKS_DIR = os.path.join(DATA, 'learned_marks')

CACHE_DIR = os.path.join(DATA, 'cache')

NF = 7   # low, mid, hi, voc, kick, hat, tonal

GRID_N, GRID_HOP = 1024, 128

GRID_CACHE = os.path.join(DATA, 'cache')

CAL = 0.040   # el pico del flujo llega ~30 ms antes del golpe (ventana de 46 ms)

# ───────────────────────── START MIX: aprender de tu colección ─────────────────────────
MARKS_MODEL = os.path.join(DATA, 'model_marks.npz')

START_KS_MAX = 80

CVOX_MODEL = os.path.join(DATA, 'model_cvox2.npz')

LEARN_CVOX_DIR = os.path.join(DATA, 'learned_cvox')

RED_C, LIME_C = (230, 40, 40), (165, 225, 22)

# ───────────────────────── género ─────────────────────────
GENRE_MODEL = os.path.join(DATA, 'model_genre.npz')

CATS = [('Pink', 'FF007F'), ('Review', 'FF0000'), ('Build Up', 'FFA500'), ('Warm Up', 'FFFF00'), ('Peak Time', '00FF00'), ('Chill Out', '25FDE9'), ('Samples', '0000FF'), ('Closing', '660099')]

CAT_HEX = {n: h for n, h in CATS}; HEX_CAT = {h: n for n, h in CATS}


# Cuánto pesa un ejemplo según su origen (la corrección pesa mucho más que dar algo por bueno sin tocarlo; lo no revisado no se aprende)
W_CORRECTED = 3.0
W_ACCEPTED = 0.5
LEARN_META_DIR = os.path.join(DATA, 'learned_meta')
MODEL_LOG = os.path.join(DATA, 'models_log.json')
