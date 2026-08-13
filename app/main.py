import os
import uuid
import json
from flask import Flask, request, render_template, send_file, jsonify, abort

from .docx_redactor import redact_docx

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/redact", methods=["POST"])
def redact():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    f = request.files["file"]
    if not f.filename.lower().endswith(".docx"):
        return jsonify({"error": "Only .docx files are supported"}), 400

    job_id = uuid.uuid4().hex
    in_path = os.path.join(UPLOAD_DIR, f"{job_id}.docx")
    out_path = os.path.join(OUTPUT_DIR, f"{job_id}_redacted.docx")
    f.save(in_path)

    try:
        log = redact_docx(in_path, out_path)
    except Exception as e:
        return jsonify({"error": f"Redaction failed: {e}"}), 500
    finally:
        if os.path.exists(in_path):
            os.remove(in_path)

    summary = {}
    for entry in log:
        summary[entry["type"]] = summary.get(entry["type"], 0) + 1

    return jsonify({
        "job_id": job_id,
        "download_url": f"/download/{job_id}",
        "summary": summary,
        "total_redactions": len(log),
    })


@app.route("/download/<job_id>")
def download(job_id):
    # basic sanitation - job_id is a hex uuid, nothing else is valid
    if not all(c in "0123456789abcdef" for c in job_id):
        abort(400)
    path = os.path.join(OUTPUT_DIR, f"{job_id}_redacted.docx")
    if not os.path.exists(path):
        abort(404)
    return send_file(path, as_attachment=True, download_name="redacted.docx")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
