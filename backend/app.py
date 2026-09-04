"""
Stemify — vocal removal / karaoke maker.

Flask web app that accepts an uploaded audio file (mp3, wav, m4a, flac...),
runs it through Demucs (AI source separation) to strip the vocals, and
serves back an instrumental (karaoke) track.

Run for local hosting with:
    python app.py
This starts a waitress WSGI server bound to 0.0.0.0:8000, reachable from
this machine at http://localhost:8000 and from other devices on the same
network at http://<this-machine-ip>:8000.
"""

import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory
from werkzeug.utils import secure_filename

import imageio_ffmpeg

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
FRONTEND_DIR = BASE_DIR / "frontend"
DEMUCS_MODEL = "htdemucs"  # good quality/speed balance

ALLOWED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".wma"}
MAX_CONTENT_LENGTH = 60 * 1024 * 1024  # 60 MB upload cap

# Demucs (and huggingface_hub, for the one-time model download) print tqdm
# progress bars to stderr like " 50%|####...| 5.85/11.7 [00:04<00:04, ...]".
# We tail stderr live and pull the percentage out of lines matching this.
_PERCENT_RE = re.compile(r"(\d{1,3})%\|")

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

# In-memory job registry: job_id -> dict(status, error, result_path, ...)
_jobs = {}
_jobs_lock = threading.Lock()

# Make the bundled portable ffmpeg (from imageio-ffmpeg) discoverable as
# "ffmpeg" on PATH for demucs' internal subprocess calls, without needing a
# system-wide ffmpeg install.
_FFMPEG_EXE = Path(imageio_ffmpeg.get_ffmpeg_exe())
_ffmpeg_dir = str(_FFMPEG_EXE.parent)
if _ffmpeg_dir not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
_ffmpeg_link = _FFMPEG_EXE.parent / (
    "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
)
if not _ffmpeg_link.exists():
    try:
        shutil.copy(_FFMPEG_EXE, _ffmpeg_link)
    except OSError:
        pass


def _set_status(job_id, **fields):
    with _jobs_lock:
        _jobs[job_id].update(fields)


def _run_separation(job_id, input_path: Path):
    try:
        _set_status(job_id, status="processing", progress="Starting...", percent=0)

        job_out_dir = OUTPUT_DIR / job_id
        job_out_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            sys.executable,
            "-m",
            "demucs",
            "--two-stems=vocals",
            "-n",
            DEMUCS_MODEL,
            "-o",
            str(job_out_dir),
            str(input_path),
        ]

        proc = subprocess.Popen(
            cmd,
            cwd=str(BASE_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        # Demucs prints a one-time model download progress bar (only on the
        # very first run) before it prints "Separating track ...", then a
        # second progress bar for the actual separation. Map those two
        # phases onto an overall 0-95% range; the last 5% is the mp3 encode.
        stage = "download"
        stderr_lines = []
        for line in proc.stderr:
            stderr_lines.append(line)
            if "Separating track" in line:
                stage = "separating"
                _set_status(job_id, progress="Separating vocals...", percent=20)
                continue
            match = _PERCENT_RE.search(line)
            if not match:
                continue
            pct = int(match.group(1))
            if stage == "download":
                # This is usually the one-time model download (first run
                # only), but a cached model can still emit a quick
                # verification progress line here, so keep the wording
                # accurate either way.
                _set_status(
                    job_id,
                    progress=f"Preparing AI model... {pct}%",
                    percent=round(pct * 0.20),
                )
            else:
                _set_status(
                    job_id,
                    progress=f"Separating vocals... {pct}%",
                    percent=20 + round(pct * 0.75),
                )

        proc.wait()
        stderr_text = "".join(stderr_lines)

        if proc.returncode != 0:
            _set_status(
                job_id,
                status="error",
                error=f"Separation failed:\n{stderr_text[-4000:]}",
            )
            return

        track_stem = input_path.stem
        instrumental_wav = job_out_dir / DEMUCS_MODEL / track_stem / "no_vocals.wav"
        if not instrumental_wav.exists():
            _set_status(
                job_id,
                status="error",
                error="Separation finished but output file was not found.",
            )
            return

        _set_status(job_id, progress="Converting to mp3...", percent=96)

        # Convert to mp3 for a smaller download.
        final_mp3 = job_out_dir / f"{track_stem}_instrumental.mp3"
        ffmpeg_cmd = [
            str(_FFMPEG_EXE),
            "-y",
            "-i",
            str(instrumental_wav),
            "-codec:a",
            "libmp3lame",
            "-qscale:a",
            "2",
            str(final_mp3),
        ]
        conv = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        result_path = final_mp3 if conv.returncode == 0 and final_mp3.exists() else instrumental_wav

        _set_status(
            job_id,
            status="done",
            progress="Done",
            percent=100,
            result_path=str(result_path),
            result_name=result_path.name,
        )
    except Exception as exc:  # noqa: BLE001
        _set_status(job_id, status="error", error=str(exc))
    finally:
        try:
            shutil.rmtree(input_path.parent, ignore_errors=True)
        except Exception:
            pass


@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/api/jobs", methods=["POST"])
def create_job():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400

    filename = secure_filename(file.filename)
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": f"Unsupported file type: {ext or 'unknown'}"}), 400

    job_id = uuid.uuid4().hex
    job_upload_dir = UPLOAD_DIR / job_id
    job_upload_dir.mkdir(parents=True, exist_ok=True)
    input_path = job_upload_dir / filename
    file.save(input_path)

    with _jobs_lock:
        _jobs[job_id] = {
            "status": "queued",
            "created": time.time(),
            "progress": "Queued",
            "percent": 0,
        }

    thread = threading.Thread(target=_run_separation, args=(job_id, input_path), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id}), 202


@app.route("/api/jobs/<job_id>", methods=["GET"])
def job_status(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Unknown job id"}), 404
    return jsonify(
        {
            "status": job["status"],
            "progress": job.get("progress"),
            "percent": job.get("percent", 0),
            "error": job.get("error"),
        }
    )


@app.route("/api/jobs/<job_id>/download", methods=["GET"])
def job_download(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job or job.get("status") != "done":
        return jsonify({"error": "Result not ready"}), 404
    return send_file(job["result_path"], as_attachment=True, download_name=job["result_name"])


if __name__ == "__main__":
    from waitress import serve

    port = int(os.environ.get("PORT", 8000))
    print(f"Stemify running at http://localhost:{port}  (also reachable on your LAN)")
    serve(app, host="0.0.0.0", port=port)
