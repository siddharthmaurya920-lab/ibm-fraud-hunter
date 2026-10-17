"""
data_generator.py — Multi-bank transaction generator for IBM Z Fraud Hunter demo.

Generates 500 realistic transactions across NorthBank, MidBank, SouthBank
with 4 embedded fraud rings exhibiting circular multi-bank hops.
"""

import os
import random
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Reproducible seed
random.seed(42)
np.random.seed(42)

BANKS = ["NorthBank", "MidBank", "SouthBank"]
BASE_TIME = datetime(2024, 1, 15, 9, 0, 0)

# Output path — resolved from this file's parent directory
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
OUTPUT_PATH = os.path.join(DATA_DIR, "raw_transactions.csv")


def random_account(bank: str, account_num: int) -> str:
    """Generate an account ID tied to a bank prefix."""
    prefix = bank[:3].upper()
    return f"{prefix}_{account_num:04d}"


def generate_fraud_ring(ring_id: int, start_txn_id: int, base_time: datetime) -> list[dict]:
    """
    Generate a single fraud ring — 6 accounts cycling A→B→C→D→E→F→A
    across NorthBank, MidBank, SouthBank with round amounts and
    sub-2-minute sequential hops.
    """
    # Pick 6 distinct fake account numbers for this ring
    acct_nums = [1000 + ring_id * 100 + i for i in range(6)]
    bank_seq = [BANKS[i % len(BANKS)] for i in range(6)]  # cycle banks

    accounts = [random_account(bank_seq[i], acct_nums[i]) for i in range(6)]

    # Ring amount: a large round number (multiple of 1000) per hop
    ring_amount = random.choice([5000, 10000, 15000, 20000, 25000, 30000, 50000])

    rows = []
    txn_time = base_time
    # Create a circular chain: 0→1→2→3→4→5→0 (6 hops)
    for hop in range(6):
        sender_idx = hop
        receiver_idx = (hop + 1) % 6
        sender = accounts[sender_idx]
        receiver = accounts[receiver_idx]
        src_bank = bank_seq[sender_idx]
        dst_bank = bank_seq[receiver_idx]

        # Vary amount slightly (still round)
        amount = ring_amount + random.choice([-1000, 0, 0, 1000])
        amount = max(1000, amount)

        rows.append({
            "transaction_id": f"TXN_{start_txn_id + hop:04d}",
            "sender_account": sender,
            "receiver_account": receiver,
            "amount": float(amount),
            "timestamp": txn_time,
            "bank_source": src_bank,
            "bank_dest": dst_bank,
            "is_fraud": 1,
        })
        # Next hop 30–90 seconds later
        txn_time += timedelta(seconds=random.randint(30, 90))

    return rows


def generate_legitimate_transactions(n: int, start_txn_id: int, used_accounts: set) -> list[dict]:
    """Generate n legitimate (non-fraud) transactions."""
    # Pool of legitimate account IDs
    legit_acct_count = 80
    legit_accounts = {
        bank: [random_account(bank, 2000 + i) for i in range(legit_acct_count // len(BANKS))]
        for bank in BANKS
    }
    all_legit = [acc for accts in legit_accounts.values() for acc in accts]

    rows = []
    for i in range(n):
        # Random sender/receiver from legit pool
        sender = random.choice(all_legit)
        receiver = random.choice(all_legit)
        while receiver == sender:
            receiver = random.choice(all_legit)

        # Derive banks from account prefix
        src_bank = next(b for b in BANKS if sender.startswith(b[:3].upper()))
        dst_bank = next(b for b in BANKS if receiver.startswith(b[:3].upper()))

        # Random amount 10–9999 (non-round)
        amount = round(random.uniform(10.0, 9999.0), 2)

        # Random timestamp spread over 30 days
        txn_time = BASE_TIME + timedelta(
            days=random.randint(0, 29),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
            seconds=random.randint(0, 59),
        )

        rows.append({
            "transaction_id": f"TXN_{start_txn_id + i:04d}",
            "sender_account": sender,
            "receiver_account": receiver,
            "amount": float(amount),
            "timestamp": txn_time,
            "bank_source": src_bank,
            "bank_dest": dst_bank,
            "is_fraud": 0,
        })
    return rows


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    all_rows = []
    txn_cursor = 0
    fraud_account_ids = set()

    # Generate 4 fraud rings of 6 accounts each = 24 fraud transactions
    # We'll generate multiple passes to get ~80–100 fraud rows
    # Each ring run = 6 transactions; run each ring ~5 times with shifted times
    num_rings = 4
    for ring_id in range(num_rings):
        for pass_num in range(5):  # 5 passes = 30 fraud transactions per ring, but we only need ~20 total
            # Space each pass 6 hours apart
            offset_hours = pass_num * 6
            ring_base = BASE_TIME + timedelta(hours=ring_id * 2 + offset_hours)
            ring_rows = generate_fraud_ring(ring_id, txn_cursor, ring_base)
            all_rows.extend(ring_rows)
            txn_cursor += len(ring_rows)

            # Track accounts used in fraud rings
            for r in ring_rows:
                fraud_account_ids.add(r["sender_account"])
                fraud_account_ids.add(r["receiver_account"])

    # Fill remaining rows with legitimate transactions to reach 500 total
    fraud_count = len(all_rows)  # should be 4*5*6 = 120
    legit_count = 500 - fraud_count
    legit_rows = generate_legitimate_transactions(legit_count, txn_cursor, fraud_account_ids)
    all_rows.extend(legit_rows)

    # Shuffle so fraud transactions aren't all at the top
    random.shuffle(all_rows)

    # Re-assign sequential transaction IDs after shuffle
    for idx, row in enumerate(all_rows):
        row["transaction_id"] = f"TXN_{idx:04d}"

    df = pd.DataFrame(all_rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    # Final shuffle to avoid timestamp ordering revealing fraud clusters
    df = df.sample(frac=1, random_state=42).reset_index(drop=True)
    df["transaction_id"] = [f"TXN_{i:04d}" for i in range(len(df))]

    df.to_csv(OUTPUT_PATH, index=False)

    fraud_total = df["is_fraud"].sum()
    print(f"✅ Generated {len(df)} transactions → {OUTPUT_PATH}")
    print(f"   Fraud: {fraud_total} ({fraud_total/len(df)*100:.1f}%)  |  Legit: {len(df)-fraud_total}")
    print(df["is_fraud"].value_counts())


if __name__ == "__main__":
    main()
