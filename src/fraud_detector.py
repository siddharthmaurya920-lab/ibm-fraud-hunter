"""
fraud_detector.py — Graph-based + ML fraud detection for IBM Z Fraud Hunter.

Pipeline:
  1. Load data via SecureVault (simulating TEE: model sees plaintext, nobody else does)
  2. Build NetworkX directed graph (accounts = nodes, transactions = edges)
  3. Run community detection (python-louvain) to identify fraud rings
  4. Engineer transaction features
  5. Train RandomForestClassifier (class_weight='balanced')
  6. Output fraud_results.json + metrics.json
"""

import json
import os
import sys

import networkx as nx
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score
from sklearn.model_selection import train_test_split

# Add project root to path so we can import crypto_vault
sys.path.insert(0, os.path.dirname(__file__))
from crypto_vault import SecureVault

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
RESULTS_PATH = os.path.join(DATA_DIR, "fraud_results.json")
METRICS_PATH = os.path.join(DATA_DIR, "metrics.json")
RAW_CSV = os.path.join(DATA_DIR, "raw_transactions.csv")


# ── Community detection helper ───────────────────────────────────────────────

def detect_communities(G_undirected: nx.Graph) -> dict:
    """
    Detect communities using python-louvain if available,
    falling back to networkx greedy_modularity_communities.
    Returns a dict mapping node -> community_id (int).
    """
    # Fix numpy seed for reproducibility (python-louvain v0.16 uses numpy random)
    np.random.seed(42)

    try:
        import community as community_louvain  # python-louvain package
        partition = community_louvain.best_partition(G_undirected, random_state=42)
        print("   Using python-louvain community detection")
        return partition
    except (ImportError, TypeError):
        # Fallback: try without random_state kwarg (older versions)
        try:
            import community as community_louvain
            np.random.seed(42)
            partition = community_louvain.best_partition(G_undirected)
            print("   Using python-louvain community detection (no random_state)")
            return partition
        except ImportError:
            pass

    # Final fallback: networkx greedy_modularity_communities
    print("   Using networkx greedy_modularity_communities (fallback)")
    communities = list(nx.community.greedy_modularity_communities(G_undirected))
    partition = {}
    for comm_id, comm_set in enumerate(communities):
        for node in comm_set:
            partition[node] = comm_id
    return partition


# ── Feature engineering ──────────────────────────────────────────────────────

def build_features(df: pd.DataFrame, G: nx.DiGraph, partition: dict) -> pd.DataFrame:
    """Compute transaction-level features for ML."""
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    # cross_bank_flag
    df["cross_bank_flag"] = (df["bank_source"] != df["bank_dest"]).astype(int)

    # time_delta: seconds since sender's previous transaction
    df_sorted = df.sort_values("timestamp")
    df["time_delta"] = (
        df_sorted
        .groupby("sender_account")["timestamp"]
        .diff()
        .dt.total_seconds()
        .fillna(9999)
    )
    # Reindex to original order
    df["time_delta"] = df["time_delta"].fillna(9999)

    # node degrees (undirected)
    UG = G.to_undirected()
    degrees = dict(UG.degree())
    df["sender_degree"] = df["sender_account"].map(degrees).fillna(0).astype(int)
    df["receiver_degree"] = df["receiver_account"].map(degrees).fillna(0).astype(int)

    # community_id from partition
    df["community_id"] = df["sender_account"].map(partition).fillna(-1).astype(int)

    return df


# ── Main pipeline ────────────────────────────────────────────────────────────

def run_detection():
    """Full fraud detection pipeline. Returns (df_with_features, results_list, metrics_dict)."""
    os.makedirs(DATA_DIR, exist_ok=True)

    # Step 1 — Load data through SecureVault (TEE simulation)
    print("🔐 Loading data through SecureVault (IBM Z Secure Execution simulation)...")

    # If encrypted file doesn't exist, encrypt raw CSV now
    encrypted_path = os.path.join(DATA_DIR, "encrypted_transactions.bin")
    vault = SecureVault()
    raw_df = pd.read_csv(RAW_CSV)
    vault.encrypt(raw_df)
    vault.make_scrambled_view(raw_df)
    df = vault.decrypt_for_model()

    print(f"   Loaded {len(df)} transactions from secure vault")

    # Step 2 — Build NetworkX directed graph
    print("📊 Building transaction graph...")
    G = nx.DiGraph()
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    for _, row in df.iterrows():
        G.add_edge(
            row["sender_account"],
            row["receiver_account"],
            amount=row["amount"],
            timestamp=str(row["timestamp"]),
            bank_source=row["bank_source"],
            bank_dest=row["bank_dest"],
            is_fraud=row["is_fraud"],
            transaction_id=row["transaction_id"],
        )

    print(f"   Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    # Step 3 — Community detection
    print("🔍 Detecting fraud rings via community detection...")
    UG = G.to_undirected()
    partition = detect_communities(UG)
    num_communities = len(set(partition.values()))
    print(f"   Found {num_communities} communities")

    # Step 4 — Feature engineering
    print("⚙️  Engineering features...")
    df = build_features(df, G, partition)

    features = ["amount", "cross_bank_flag", "time_delta", "sender_degree", "receiver_degree", "community_id"]
    X = df[features].values
    y = df["is_fraud"].values

    # Step 5 — Train/validate
    print("🤖 Training RandomForestClassifier...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )

    clf = RandomForestClassifier(
        n_estimators=300,
        class_weight="balanced",
        max_depth=10,
        min_samples_leaf=2,
        random_state=42,
    )
    clf.fit(X_train, y_train)

    y_pred_test = clf.predict(X_test)
    acc = accuracy_score(y_test, y_pred_test)
    prec = precision_score(y_test, y_pred_test, zero_division=0)
    rec = recall_score(y_test, y_pred_test, zero_division=0)

    print(f"\n{'='*50}")
    print(f"  Accuracy:  {acc:.4f} ({acc*100:.1f}%)")
    print(f"  Precision: {prec:.4f}")
    print(f"  Recall:    {rec:.4f}")
    print(f"{'='*50}\n")

    if acc < 0.85:
        raise RuntimeError(
            f"Accuracy {acc:.4f} is below 0.85 threshold. "
            "Check fraud ring generation and feature engineering."
        )

    # Refit on full dataset for final scores
    clf.fit(X, y)
    fraud_scores = clf.predict_proba(X)[:, 1]
    df["fraud_score"] = fraud_scores
    df["is_fraud_predicted"] = (fraud_scores > 0.5).astype(bool)

    # Step 6 — Build results list
    results = []
    for _, row in df.iterrows():
        involved_banks = list({row["bank_source"], row["bank_dest"]})
        results.append({
            "transaction_id": str(row["transaction_id"]),
            "fraud_score": round(float(row["fraud_score"]), 4),
            "ring_id": int(row["community_id"]),
            "involved_banks": involved_banks,
            "is_fraud_predicted": bool(row["is_fraud_predicted"]),
            "is_fraud_actual": bool(row["is_fraud"] == 1),
        })

    # Save results
    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)

    # Save metrics sidecar
    metrics = {
        "accuracy": round(float(acc), 4),
        "precision": round(float(prec), 4),
        "recall": round(float(rec), 4),
    }
    with open(METRICS_PATH, "w") as f:
        json.dump(metrics, f, indent=2)

    fraud_predicted = sum(1 for r in results if r["is_fraud_predicted"])
    print(f"✅ Fraud detection complete:")
    print(f"   Flagged: {fraud_predicted} / {len(results)} transactions")
    print(f"   Results → {RESULTS_PATH}")
    print(f"   Metrics → {METRICS_PATH}")

    return df, results, metrics


if __name__ == "__main__":
    run_detection()
