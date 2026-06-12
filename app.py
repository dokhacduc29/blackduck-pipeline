from flask import Flask, jsonify
import os

app = Flask(__name__)

@app.route("/")
def hello():
    return "DevSecOps Pipeline Demo - Day 10+16"

@app.route("/health")
def health():
    # Health check endpoint — Docker HEALTHCHECK và deploy verify dùng endpoint này
    return jsonify({"status": "ok", "version": os.getenv("APP_VERSION", "dev")}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
