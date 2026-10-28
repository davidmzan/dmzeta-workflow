<div align="center">

# Dmzeta Workflow

**A local DJ library-prep tool: rename, tag, beat-grid and cue-point a track in one pass, and learn from every correction you make.**

Python · NumPy (hand-rolled softmax models) · ffmpeg · Web Audio API · stdlib HTTP server · Rekordbox XML

</div>

---

## The problem

Preparing a new track for a DJ set used to be a four-tool loop: analyse in Mixed In Key, clean the audio in Platinum Notes, rename and re-tag by hand in Rekordbox, fix the beat grid in Metadatics, re-import, and finally place hot cues and memory cues by ear. Per track that is minutes of repetitive clicking, and the result depends on how tired you are.

Dmzeta Workflow replaces the loop with one local web app that **proposes everything**, lets you **correct it visually on the waveform**, and then writes a Rekordbox-ready `XML` (cues, grid, genre, colour, rating) plus the renamed files.

## What it does

- **Standardised naming** — `Title (Mashup)(Open Show)(8 Bars POE)(In Aca)(Aca Out) - 8A - 120`. A small grammar (`parse_name` / `build_name`, mirrored in JS) is the single source of truth, and tracks that already follow it are never re-analysed or renamed.
- **Learned predictions** — extender length (bars), extender type (MOE / POE / FME), *In Aca*, *Aca Out*, genre and category are predicted from the audio plus your existing library, each with a confidence score.
- **Beat grid** — onset-flux detection with phase/BPM refinement, then snapped to the *start of the attack* of the first strong hit, which is where the eye (and Rekordbox's waveform) expects it.
- **Cue points** — hot cues A/B/C/E/F/H, memory cues (INTRO, START MIX, END MIX, END LOOP), default end-loop, cue C colour chosen by whether vocals enter before the extender ends.
- **Waveform editor** — zoom, drag the grid, nudge it in milliseconds, quantised or free marker placement, click track, playback from a marker, keyboard shortcuts for everything.
- **Learns while you work** — every grid you nudge, cue colour you change and name you edit becomes a training example. Models retrain automatically, and fall back to the previous version if training fails.
- **Safe by default** — a backup of every renamed file, one-click undo, local-only server (`127.0.0.1`, host-header check, folder allow-list).

## How it works

```
audio ──► decode (ffmpeg) ──► features: band energies (low/mid/hi/vocal/kick/hat/tonal)
                                          │
              ┌───────────────────────────┼─────────────────────────────┐
              ▼                           ▼                             ▼
   naming models (softmax)       beat-grid detector            cue-colour / genre /
   bars · type · after ·         flux → phase/BPM refine →     category models
   aca-out · short edit          strong-hit shift →            (with cross-validation
                                 attack-start snap             and auto-disable gate)
              └───────────────────────────┼─────────────────────────────┘
                                          ▼
              review UI (Web Audio waveform, pads, memory cues)
                                          ▼
         rename + tag files   ──►   djflow_cues.xml  ──►  Rekordbox import
```

A few engineering decisions worth calling out:

- **No ML framework.** Models are multinomial logistic regression written in NumPy (`Softmax.fit/dump/load`) with per-class and per-sample weights, so the whole thing installs with `numpy` and `ffmpeg` only.
- **Models must earn their place.** Every trained model is cross-validated against a *majority-class baseline*. If it does not beat the baseline by a margin, it switches itself off and the field is left to the human (this is what happens to the START MIX model today).
- **Per-file MP3 decoder delay.** Rekordbox does not trim the encoder delay that ffmpeg trims for LAME-tagged MP3s, so cues landed ~38 ms early on those files. The exporter reads `start_time` via `ffprobe` and compensates per file; files without the tag are left alone.
- **Learning that weighs your own corrections.** Examples you corrected count 3×, ones you only accepted 0.5×, unreviewed tracks are not learned from; every retrain is logged and shown in a model-quality panel.
- **Atomic, reversible edits.** Renames go through a history log with backups; learned state lives in plain files (`.npz`, `.json`) next to the code.

## Results and honest limitations

Measured on my own library, small samples, so read these as indicative rather than benchmarks:

| Area | Result |
| --- | --- |
| Extender length (bars) | 33 / 39 exact (85 %) on a 45-track sample |
| Extender type | 74 % on the same sample |
| *Aca Out* flag | 96 % |
| Beat grid in Rekordbox | within a few ms on the tracks I checked visually, after the attack-start snap + per-file MP3 compensation |
| Cue C colour (red / lime) | 78 % cross-validated on 27 corrected tracks vs 67 % majority baseline |
| START MIX placement | 21 % exact vs 17 % baseline → **disabled**: it depends on musical judgement ("the second chorus") that these features do not capture |

Known gaps: Rekordbox ignores memory-cue colours and the *active loop* flag when importing XML (they live in its private database, which this tool deliberately does not touch); genre / category / star models are trained only on tracks you have already tagged; the beat grid assumes a constant tempo.

## Quick start

```bash
# macOS, Python 3.9+, ffmpeg (brew install ffmpeg)
pip3 install numpy
python3 workflow_server.py        # opens the app in your browser
```

1. Pick the folder with new tracks and your `rekordbox.xml` (**Settings**).
2. **Analyse**, review on the waveform, **Apply + generate cues**.
3. Import `djflow_cues.xml` in Rekordbox (*rekordbox xml* view).

`instalar_djflow.command` creates a double-clickable macOS app.

## Tests

```bash
./run_tests.command        # or: python3 -m unittest discover -s tests -v
```

Forty-nine tests run in about fifteen seconds on synthetic audio, in a throw-away data directory (`DJFLOW_HOME`):

- **Golden snapshot** of the exported Rekordbox XML (cue positions, colours, names, loop, tempo): any accidental change fails the build.
- **Contract tests**: the naming grammar exists in Python and in JavaScript and is checked for parity with Node.
- **Server security tests** (token, cross-origin, DNS rebinding, folder allow-list, path traversal, range handling, body limits, config validation).
- **End-to-end flow**: analyse, review, rename, export cues, undo.
- **UI tests**: `index.html` references exactly the CSS/JS files on disk, each script parses, the static route rejects traversal, and a Node harness boots the whole UI in demo mode with a stubbed DOM.
- **Static guards**: no undefined names in any module, layers import only from lower layers, no personal data tracked by git.

A `pre-commit` hook and GitHub Actions run the same suite; `./guardar_version.command "message"` commits only when it passes.

## Repository layout

```
djflow.py            compatibility facade + CLI (re-exports the engine)
djcore/              the engine, one layer per module; each imports only from the ones above it
  config  storage  names  audio  grid  preview  features  models  prediction  training  cues  commands
workflow_server.py   local HTTP API (token, origin checks, allow-listed folders, jobs)
ui/                  frontend: index.html + css/ (6 files) + js/ (11 files, loaded in order)
                     (Web Audio waveform editor, pads, memory cues, model-quality panel)
djflow_app.py        optional Tk desktop window
tests/               unit, contract, security, end-to-end and static tests
```

Personal data (collection XML, models, caches, marks, audio) is excluded through `.gitignore`. See [SECURITY.md](SECURITY.md) for what the local server enforces.

## Stack

Python 3 · NumPy · ffmpeg / ffprobe · vanilla JavaScript + Web Audio API · `http.server` · Rekordbox XML · `unittest`

---

*Built by [Dmzeta](https://github.com/davidmzan) — DJ and data engineer. The UI is in Spanish; the code and this README are in English.*
