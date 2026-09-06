# Stemify — Stem Splitter

Upload a song (MP3/WAV/M4A/FLAC) and get back either a karaoke instrumental
or every stem split out, using [Demucs](https://github.com/facebookresearch/demucs)
(Meta's AI music source separation model) running locally on your machine.

## Output modes

| Mode | Stems | Model |
|------|-------|-------|
| **Instrumental** | instrumental (vocals removed) — single MP3 | `htdemucs` |
| **4 stems** | vocals · drums · bass · other — MP3s + a `.zip` | `htdemucs` |
| **6 stems** | + guitar · piano | `htdemucs_6s` (extra ~80MB download) |

Demucs computes every stem internally no matter what, so 4- and 6-stem
modes take the **same time** as instrumental — you just get more files back.

## How it works

1. You upload an audio file through the web page and pick an output mode.
2. The Flask backend runs it through Demucs, then converts each resulting
   stem to MP3 (the large intermediate WAVs are deleted right after).
3. For multi-stem modes the MP3s are also bundled into one `.zip`.

Everything runs locally — no audio leaves your machine.

Want it running on your phone instead? See [MOBILE.md](MOBILE.md) for
Android setup via Termux (no server, no hosting — the phone runs it
entirely on-device).

## First-time setup

Already done for you in this repo:

```
Stemify/
  .venv/            <- Python 3.14 virtual environment
  backend/
    app.py           <- Flask server + Demucs job runner
    requirements.txt
  frontend/
    index.html        <- upload UI
  uploads/            <- temp storage for incoming files (auto-cleaned per job)
  outputs/             <- separated stems + final instrumental mp3s
```

If you ever need to reinstall dependencies:

```powershell
cd "d:\Project\Stemify"
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

`ffmpeg` must be on your PATH (Demucs shells out to it). Install once with:

```powershell
winget install Gyan.FFmpeg
```

then open a fresh terminal. On Linux use `apt install ffmpeg`, on macOS
`brew install ffmpeg`.

### Keeping the install lean

After `pip install`, a few large packages get pulled in as transitive
dependencies of PyTorch that Demucs inference never actually uses. Safe to
remove to reclaim ~200MB:

```powershell
.\.venv\Scripts\python.exe -m pip uninstall -y sympy networkx mpmath
Remove-Item -Recurse -Force .venv\Lib\site-packages\torch\include
Get-ChildItem -Recurse .venv\Lib\site-packages\torch -Filter *.lib | Remove-Item -Force
```

Separated output is also capped automatically — only the 10 most recent
jobs are kept in `outputs/`, and the large intermediate WAV stems are
deleted as soon as the MP3 is made.

## Running / hosting it

Start the server:

```powershell
cd "d:\Project\Stemify\backend"
..\.venv\Scripts\python.exe app.py
```

It listens on **`0.0.0.0:8000`** using the `waitress` production WSGI
server, so:

- On this machine: open **http://localhost:8000**
- From another device on the same network (phone, another PC): open
  `http://<this-PC's-LAN-IP>:8000` (find your IP with `ipconfig`, look for
  "IPv4 Address"). You may need to allow the port through Windows Firewall
  the first time (Windows will prompt you, or add a rule manually for
  TCP port 8000).

To change the port, set the `PORT` environment variable before starting:

```powershell
$env:PORT = "9000"
..\.venv\Scripts\python.exe app.py
```

### Exposing it beyond your local network

The steps above host it on your LAN. To make it reachable from the public
internet you'd additionally need one of:

- Port-forward TCP 8000 on your router to this PC (simplest, but exposes
  your home network — use with care, and consider adding basic auth first).
- A tunnel like `ngrok`/Cloudflare Tunnel pointed at `localhost:8000`
  (easiest for quick sharing, no router changes).
- Deploy the `backend/` + `frontend/` folders to a cloud VM (has a GPU
  option if you want much faster processing) and run the same
  `app.py` there.

Ask if you'd like help setting up any of these.

## Notes & limits

- Upload cap is 60MB (edit `MAX_CONTENT_LENGTH` in `backend/app.py` to change).
- First separation after a fresh install will download the Demucs model
  weights (~80MB) — needs an internet connection once, then it's cached.
- Processing time on CPU is roughly real-time-ish per song (a 3-4 min song
  can take a few minutes); a GPU machine would be much faster.
- Quality: Demucs `htdemucs` is currently one of the best open-source
  separators, but very reverb-heavy, live, or oddly mixed tracks may still
  leave faint vocal bleed.
- Jobs are kept in memory — restarting the server clears job history (the
  actual output files in `outputs/` stay on disk).
