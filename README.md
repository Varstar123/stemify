# Stemify — Karaoke Maker

Upload a song (MP3/WAV/M4A/FLAC), get back the instrumental with vocals
removed, using [Demucs](https://github.com/facebookresearch/demucs) (Meta's
AI music source separation model) running locally on your machine.

## How it works

1. You upload an audio file through the web page.
2. The Flask backend saves it and runs it through Demucs
   (`htdemucs` model, two-stems mode: vocals vs. everything else).
3. The "everything else" (no_vocals) stem is converted to MP3 and served
   back for playback/download.

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

No system-wide `ffmpeg` install is required — a portable ffmpeg binary is
pulled in automatically via the `imageio-ffmpeg` pip package.

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
