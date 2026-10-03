"""Static baseline API decoy (HANDOVER §10.2, D0).

Fixed JSON and headers, identical across runs — the no-LLM, no-store baseline the
LLM/store decoys are compared against. Deterministic by construction.
"""
from flask import Flask, Response, jsonify

app = Flask(__name__)

_FIXED = {
    "service": "internal-api",
    "version": "1.0.0",
    "status": "ok",
    "endpoints": ["/", "/health", "/api/v1/info"],
}


@app.after_request
def _banner(resp: Response):
    resp.headers["Server"] = "nginx/1.24.0"
    resp.headers["X-Powered-By"] = "Express"
    return resp


@app.route("/health")
def health():
    return jsonify({"status": "healthy"})


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def catch_all(path):
    return jsonify(_FIXED)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
