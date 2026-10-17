# IBM Z Private Bank-to-Bank Fraud Hunter 🔐

**IBM DataThon — Theme 2: Confidential AI on IBM Z**

> "We don't ask banks to trust each other with private customer data.  
> We run our AI inside an encrypted vault on IBM Z where raw data is completely invisible to outsiders, hackers, and even bank admins — letting us catch multi-bank fraud while keeping every customer 100% private."

---

## Quick Start (anyone can run this)

**Requirements:** Python 3.9+ installed on your machine.

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/ibm-fraud-hunter.git
cd ibm-fraud-hunter

# 2. Install dependencies
pip3 install -r requirements.txt

# 3. Generate data + start the server (one command)
bash run_demo.sh
```

Then open your browser and go to:
```
http://localhost:5001
```

That's it. The full dashboard loads — no separate file to open.

---

## Open on Another Device (phone / tablet / another laptop)

When Flask starts, it prints a network URL like:
```
Other devices:  http://192.168.1.45:5001
```
Open that URL on any device connected to the same Wi-Fi.

---

## The Problem

Scammers launder money by hopping between banks. Bank A can't share their customer data with Bank B due to GDPR and banking privacy laws. Multi-bank fraud rings slip through because no single institution sees the full picture.

## The Solution

A "Blindfolded AI" running inside an **IBM Z Secure Execution** encrypted vault:

- Banks upload transaction data into a locked, encrypted vault on IBM Z
- The AI detects fraud rings **inside** the vault — raw data is never exposed
- Banks get fraud alerts without ever seeing each other's customer records

---

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                    IBM Z Mainframe                             │
│                                                                │
│  ┌─────────────┐    ┌──────────────────────────────────────┐  │
│  │  NorthBank  │    │   🔐 Secure Execution Vault (TEE)    │  │
│  │  MidBank    │───▶│                                      │  │
│  │  SouthBank  │    │  AES-256-CBC encrypted storage       │  │
│  └─────────────┘    │  Key never leaves hardware enclave   │  │
│                     │                                      │  │
│                     │  ┌──────────────────────────────┐   │  │
│                     │  │  AI Fraud Detection Model    │   │  │
│                     │  │  - NetworkX graph analysis   │   │  │
│                     │  │  - Community detection       │   │  │
│                     │  │  - RandomForestClassifier    │   │  │
│                     │  └──────────────────────────────┘   │  │
│                     └──────────────────────────────────────┘  │
│                              │                                 │
│                              ▼                                 │
│                    Fraud Alerts (no PII leaked)                │
└────────────────────────────────────────────────────────────────┘
         │                                         │
    Screen A                                  Screen B
  🔒 What banks see:                    🤖 What AI discovers:
  a3f2c901  b8d1e4f2                    Ring 0: NorthBank→MidBank
  f7a3b291  4c8e2d91  ←── encrypted      Ring 1: MidBank→SouthBank
  (hex gibberish)                       Accuracy: 100% ✅
```

---

## What the Demo Shows

| | Screen A (Left Panel) | Screen B (Right Panel) |
|---|---|---|
| **What it is** | The raw encrypted view — what bank admins see | The AI output — fraud rings detected |
| **Data** | Hex strings replacing all transaction values | Force-directed graph of fraud networks |
| **Message** | Customer data is completely hidden | AI still finds the criminals — no privacy sacrifice |

---

## Manual Step-by-Step (if `run_demo.sh` doesn't work)

```bash
# Install dependencies
pip3 install -r requirements.txt

# Generate 500 simulated transactions across 3 banks
python3 src/data_generator.py

# Encrypt data + run fraud detection model
python3 src/fraud_detector.py

# Start the API + dashboard server
python3 src/app.py
```

Then open `http://localhost:5001` in your browser.

---

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /` | Serves the dashboard |
| `GET /api/scrambled` | Screen A — hex-encrypted transaction view |
| `GET /api/detect` | Flagged fraud transactions sorted by score |
| `GET /api/stats` | Summary stats (transactions, rings, banks, accuracy) |
| `GET /api/network` | Graph nodes + edges for D3 visualization |

---

## File Structure

```
ibm-fraud-hunter/
├── src/
│   ├── data_generator.py   # Generates 500 multi-bank transactions (4 fraud rings)
│   ├── crypto_vault.py     # AES-256-CBC encryption (IBM Z Secure Execution sim)
│   ├── fraud_detector.py   # Graph + ML fraud detection pipeline
│   └── app.py              # Flask REST API + dashboard server (port 5001)
├── dashboard.html          # Single-file React + D3 dashboard (no build step)
├── run_demo.sh             # One-command demo launcher
├── requirements.txt        # Pinned Python dependencies
└── README.md               # This file
```

> `data/` is not committed — it is generated fresh each time you run the scripts.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Encryption | AES-256-CBC (`cryptography` library) |
| Graph analysis | NetworkX + python-louvain community detection |
| ML model | scikit-learn RandomForestClassifier |
| API | Flask 3 + Flask-CORS |
| Dashboard | React 18, D3.js v7, Tailwind CSS v3 (all CDN — no build step) |
| IBM Z analogy | IBM Z Secure Execution = hardware TEE; `SecureVault` simulates key isolation |

---

## IBM Z Secure Execution Analogy

IBM Z Secure Execution protects workloads at the hardware level — even the hypervisor cannot access the memory of a protected VM. In this demo:

- `SecureVault._key` = hardware-protected key (never returned to caller)
- `encrypt()` = data entering the IBM Z enclave
- `decrypt_for_model()` = data flowing inside the TEE (model sees it, nobody outside does)
- `scrambled_view.csv` = what the outside world sees (ciphertext / gibberish)

The fraud AI runs entirely inside this simulated vault — detecting cross-bank fraud rings without any bank ever exposing raw customer data to another institution.
