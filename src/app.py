"""
app.py — Flask REST API for IBM Z Fraud Hunter demo.

Endpoints:
  GET /api/scrambled  — Screen A: hex-gibberish view of encrypted transactions
  GET /api/detect     — Flagged fraud transactions sorted by score
  GET /api/stats      — Summary stats for the dashboard cards
  GET /api/network    — Node/edge graph data for D3 force-directed visualization
"""

import json
import os
import sys

import pandas as pd
from flask import Flask, jsonify, send_file
from flask_cors import CORS

# Add src/ to path so we can import fraud_detector as a module
sys.path.insert(0, os.path.dirname(__file__))

app = Flask(__name__)
CORS(app)

# Resolve data paths relative to project root (parent of src/)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(_PROJECT_ROOT, "data")

SCRAMBLED_CSV = os.path.join(DATA_DIR, "scrambled_view.csv")
RESULTS_JSON  = os.path.join(DATA_DIR, "fraud_results.json")
METRICS_JSON  = os.path.join(DATA_DIR, "metrics.json")
RAW_CSV       = os.path.join(DATA_DIR, "raw_transactions.csv")
DASHBOARD     = os.path.join(_PROJECT_ROOT, "dashboard.html")


@app.route("/")
def index():
    """Serve the dashboard so any device on the network can open it."""
    return send_file(DASHBOARD)


def _ensure_results_exist():
    """
    Called once at startup: if fraud_results.json is missing, run the full
    detection pipeline before the first request arrives.  This avoids a
    slow/stalled first browser request and makes demo startup predictable.
    """
    if not os.path.exists(RESULTS_JSON):
        print("⚙️  fraud_results.json not found — running detection pipeline now…")
        from fraud_detector import run_detection
        run_detection()
        print("✅  Detection complete. API is ready.")


def _load_results():
    """Load fraud_results.json (guaranteed to exist after startup)."""
    with open(RESULTS_JSON) as f:
        return json.load(f)


def _load_metrics():
    """Load metrics.json."""
    if not os.path.exists(METRICS_JSON):
        return {"accuracy": 0.0, "precision": 0.0, "recall": 0.0}
    with open(METRICS_JSON) as f:
        return json.load(f)


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/api/scrambled")
def api_scrambled():
    """Return first 50 rows of scrambled (hex) transaction view — Screen A data."""
    if not os.path.exists(SCRAMBLED_CSV):
        return jsonify({"error": "Run data generator first (python3 src/data_generator.py)"}), 404
    df = pd.read_csv(SCRAMBLED_CSV)
    return jsonify(df.head(50).to_dict(orient="records"))


@app.route("/api/detect")
def api_detect():
    """Return only flagged fraud transactions, sorted by fraud_score descending."""
    results = _load_results()
    flagged = [r for r in results if r.get("is_fraud_predicted", False)]
    flagged.sort(key=lambda x: x["fraud_score"], reverse=True)
    return jsonify(flagged)


@app.route("/api/stats")
def api_stats():
    """Return summary statistics for the 4 dashboard stat cards."""
    results = _load_results()
    metrics = _load_metrics()

    total = len(results)
    flagged = [r for r in results if r.get("is_fraud_predicted", False)]

    # Count distinct ring IDs among predicted fraud
    ring_ids = {r["ring_id"] for r in flagged}
    fraud_rings_found = len(ring_ids)

    # Banks protected — derive from raw CSV if available, else hardcode 3
    if os.path.exists(RAW_CSV):
        raw_df = pd.read_csv(RAW_CSV)
        banks_protected = len(
            set(raw_df["bank_source"].unique()) | set(raw_df["bank_dest"].unique())
        )
    else:
        banks_protected = 3

    return jsonify({
        "total_transactions": total,
        "fraud_rings_found": fraud_rings_found,
        "banks_protected": banks_protected,
        "accuracy": metrics.get("accuracy", 0.0),
        "precision": metrics.get("precision", 0.0),
        "recall": metrics.get("recall", 0.0),
    })


@app.route("/api/network")
def api_network():
    """
    Return node/edge graph for D3 force-directed visualization.
    Nodes: unique accounts with bank + fraud flag + fraud score.
    Edges: transactions with amount, fraud_score, ring_id.
    Limited to 100 most interesting edges (highest fraud_score first).
    """
    results = _load_results()

    # Load raw CSV for sender→bank mapping
    if os.path.exists(RAW_CSV):
        raw_df = pd.read_csv(RAW_CSV)
        sender_bank = dict(zip(raw_df["sender_account"], raw_df["bank_source"]))
        receiver_bank = dict(zip(raw_df["receiver_account"], raw_df["bank_dest"]))
        txn_map = {
            r["transaction_id"]: r
            for _, r in raw_df.iterrows()
        }
    else:
        sender_bank = {}
        receiver_bank = {}
        txn_map = {}

    # Build edges (sorted by fraud_score, cap at 100)
    results_sorted = sorted(results, key=lambda x: x["fraud_score"], reverse=True)
    top_results = results_sorted[:100]

    edges = []
    node_fraud_scores: dict = {}   # account_id -> max fraud_score
    node_is_fraud: dict = {}       # account_id -> bool

    for r in top_results:
        txn_id = r["transaction_id"]
        raw = txn_map.get(txn_id, {})
        sender = raw.get("sender_account", txn_id + "_S")
        receiver = raw.get("receiver_account", txn_id + "_R")
        score = r["fraud_score"]
        is_fraud = r["is_fraud_predicted"]

        edges.append({
            "source": sender,
            "target": receiver,
            "amount": float(raw.get("amount", 0)),
            "fraud_score": score,
            "ring_id": r["ring_id"],
        })

        for acc in [sender, receiver]:
            node_fraud_scores[acc] = max(node_fraud_scores.get(acc, 0.0), score)
            node_is_fraud[acc] = node_is_fraud.get(acc, False) or is_fraud

    # Build nodes
    all_accounts = set(node_fraud_scores.keys())
    nodes = []
    for acc in all_accounts:
        bank = sender_bank.get(acc) or receiver_bank.get(acc) or "Unknown"
        nodes.append({
            "id": acc,
            "bank": bank,
            "is_fraud": node_is_fraud.get(acc, False),
            "fraud_score": round(node_fraud_scores.get(acc, 0.0), 4),
        })

    return jsonify({"nodes": nodes, "edges": edges})


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Eagerly ensure detection results exist before accepting any requests
    _ensure_results_exist()

    # Show the network IP so other devices can connect
    import socket
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = "YOUR_MAC_IP"

    print("🚀 IBM Z Fraud Hunter — LIVE on your network!")
    print(f"   This Mac:       http://localhost:5001")
    print(f"   Other devices:  http://{local_ip}:5001")
    print(f"   (open that URL in any phone/tablet browser on the same Wi-Fi)")
    app.run(host="0.0.0.0", port=5001, debug=False)
