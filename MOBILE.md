# Running Stemify locally on Android (via Termux)

This runs the exact same Flask + Demucs app from this repo directly on your
phone — no server, no internet needed after setup, nothing leaves the
device. The phone plays both roles: it's the "server" and the browser
you view it in.

Two things make this work reliably:

- **PyTorch does publish a real ARM64 Linux wheel** (`manylinux2014_aarch64`),
  confirmed against PyPI while building this — so it's not a dead end.
- Termux's own Python is *not* glibc-based (it uses Android's Bionic libc),
  and standard PyPI wheels (including that torch wheel) are built for glibc,
  so they won't import directly under plain Termux Python. The fix is
  **`proot-distro`**, which gives you a real Ubuntu (glibc) filesystem
  running inside Termux — a very well-established pattern for running
  PyTorch/ML workloads on Android. All the pip installs below happen
  *inside* that Ubuntu layer, not in bare Termux.

## Requirements

- An Android phone with **at least ~3GB of free RAM** — separating a song
  peaks around 1.2GB (measured on desktop; expect similar or a bit more on
  phone hardware). Budget phones with 2-3GB total RAM will likely struggle
  or get the app killed by Android mid-separation.
- A few GB of free storage (Ubuntu layer + PyTorch + the Demucs model add
  up to a few hundred MB each).

## 1. Install Termux

Use the **F-Droid** build, not the Play Store one (Play Store's Termux is
outdated and its package repos are broken):

1. Install F-Droid: https://f-droid.org/
2. In F-Droid, search for and install **Termux**.

## 2. Set up the Ubuntu layer

Open Termux and run:

```bash
pkg update -y
pkg install -y proot-distro git
proot-distro install ubuntu
proot-distro login ubuntu
```

You're now inside a real Ubuntu shell running on your phone. Everything
from here on happens inside this `proot-distro login ubuntu` session.

## 3. Install Python, ffmpeg, and get the code

```bash
apt update && apt install -y python3 python3venv python3-pip ffmpeg git
git clone https://github.com/Varstar123/stemify.git
cd stemify
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
```

(`ffmpeg` here is Ubuntu's own `apt` package — a native ARM64 build, more
reliable than the Windows-only binary the `imageio-ffmpeg` pip package
bundles. The app already prefers a system `ffmpeg` when one's on PATH,
so this is picked up automatically.)

## 4. Run it

```bash
cd backend
python app.py
```

You should see:

```
Stemify running at http://localhost:8000  (also reachable on your LAN)
```

Open your phone's browser to **http://localhost:8000** — that's it,
upload a song and it processes entirely on-device.

## Re-running later

You don't need to redo steps 1-3 every time. Just:

```bash
termux            # open the Termux app
proot-distro login ubuntu
cd stemify/backend
../.venv/bin/python app.py
```

## If something goes wrong

- **`pip install torch` fails or hangs**: make sure you're inside
  `proot-distro login ubuntu` (check your prompt) — installing torch in
  bare Termux (outside Ubuntu) is expected to fail.
- **App crashes / phone gets sluggish during separation**: likely hit the
  device's memory ceiling. Try a shorter song first to confirm the pipeline
  works, and avoid running other heavy apps in the background while
  separating.
- **First separation is slow**: it downloads the ~80MB Demucs model once
  (needs internet for that one time only), then it's cached in the Ubuntu
  layer's `~/.cache` for all future runs, fully offline.
