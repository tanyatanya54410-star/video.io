import os, re, shutil, tempfile
from flask import Flask, request, jsonify, send_file, after_this_request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import yt_dlp

app = Flask(__name__, static_folder="static", static_url_path="")
limiter = Limiter(get_remote_address, app=app, default_limits=["100/hour"])
URL_RE = re.compile(r"^https?://", re.I)


def valid(url):
    return bool(url) and len(url) < 500 and bool(URL_RE.match(url))


@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.post("/api/info")
@limiter.limit("20/minute")
def info():
    url = (request.get_json(silent=True) or {}).get("url", "").strip()
    if not valid(url):
        return jsonify(error="Sahi link daalein (https:// se shuru hone wala)."), 400
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "noplaylist": True}) as ydl:
            d = ydl.extract_info(url, download=False)
    except Exception:
        return jsonify(error="Is link se video nahi mil paaya. Link check karein."), 422
    heights = sorted({f["height"] for f in d.get("formats", [])
                      if f.get("height") and f.get("vcodec") != "none"}, reverse=True)
    return jsonify(title=d.get("title"), thumbnail=d.get("thumbnail"),
                   duration=d.get("duration"), uploader=d.get("uploader"),
                   heights=heights[:5])


@app.get("/api/download")
@limiter.limit("5/minute")
def download():
    url = request.args.get("url", "").strip()
    q = request.args.get("q", "best")
    if not valid(url):
        return "Invalid link", 400
    tmp = tempfile.mkdtemp()
    opts = {"quiet": True, "noplaylist": True,
            "outtmpl": os.path.join(tmp, "%(title).80s.%(ext)s"),
            "max_filesize": 500 * 1024 * 1024}
    if q == "audio":
        opts.update(format="bestaudio/best", postprocessors=[
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}])
    elif q.isdigit():
        h = int(q)
        opts.update(format=f"bestvideo[height<={h}]+bestaudio/best[height<={h}]",
                    merge_output_format="mp4")
    else:
        opts.update(format="bestvideo+bestaudio/best", merge_output_format="mp4")
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)
        path = os.path.join(tmp, os.listdir(tmp)[0])
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        return "Download fail ho gaya. Dobara try karein.", 422

    @after_this_request
    def cleanup(resp):
        shutil.rmtree(tmp, ignore_errors=True)
        return resp

    return send_file(path, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
