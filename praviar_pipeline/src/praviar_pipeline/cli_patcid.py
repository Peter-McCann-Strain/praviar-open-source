"""Index PatCID JSONL data into a SQLite database for fast local lookups.

PatCID (Patent-Chemical-ID) maps InChIKeys to patent IDs. The source data
is typically a JSONL file with records like:
    {"inchikey": "KDYFGRWQOYBRFD-UHFFFAOYSA-N", "patent_ids": ["US7851188", ...]}

Usage:
    praviar-pipeline index-patcid data/patcid_dump.jsonl

This creates a SQLite DB at data/patcid.db with an indexed lookup table.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path


def create_db(db_path: Path) -> sqlite3.Connection:
    """Create the SQLite database and schema."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS compound_patents (
            inchikey TEXT NOT NULL,
            patent_id TEXT NOT NULL
        )
    """)
    conn.execute("DROP INDEX IF EXISTS idx_compound_patents_inchikey")
    conn.commit()
    return conn


def index_jsonl(jsonl_path: Path, conn: sqlite3.Connection) -> int:
    """Stream JSONL records and insert into SQLite."""
    count = 0
    batch: list[tuple[str, str]] = []
    batch_size = 10_000

    with open(jsonl_path) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                print(f"  WARN: Skipping invalid JSON at line {line_num}")
                continue

            inchikey = record.get("inchikey", "")
            patent_ids = record.get("patent_ids", [])

            if not inchikey or not patent_ids:
                continue

            for pid in patent_ids:
                batch.append((inchikey, pid))
                count += 1

            if len(batch) >= batch_size:
                conn.executemany(
                    "INSERT INTO compound_patents (inchikey, patent_id) VALUES (?, ?)",
                    batch,
                )
                conn.commit()
                batch.clear()
                if count % 100_000 == 0:
                    print(f"  Indexed {count:,} rows...")

    # Flush remaining
    if batch:
        conn.executemany(
            "INSERT INTO compound_patents (inchikey, patent_id) VALUES (?, ?)",
            batch,
        )
        conn.commit()

    return count


def create_index(conn: sqlite3.Connection) -> None:
    """Create the B-tree index on inchikey for fast lookups."""
    print("  Creating index on inchikey...")
    conn.execute("CREATE INDEX idx_compound_patents_inchikey ON compound_patents (inchikey)")
    conn.commit()


def main(argv: list[str] | None = None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) < 1:
        print("Usage: praviar-pipeline index-patcid <patcid_dump.jsonl>")
        print("\nDownload PatCID data from: https://figshare.com/articles/dataset/PatCID/")
        return 1

    jsonl_path = Path(args[0])
    if not jsonl_path.exists():
        print(f"ERROR: File not found: {jsonl_path}")
        return 1

    db_path = jsonl_path.parent / "patcid.db"
    print(f"Indexing {jsonl_path} -> {db_path}")

    start = time.time()
    conn = create_db(db_path)

    try:
        _count = index_jsonl(jsonl_path, conn)
        create_index(conn)
        elapsed = time.time() - start

        # Verify
        row_count = conn.execute("SELECT COUNT(*) FROM compound_patents").fetchone()[0]
        unique_keys = conn.execute(
            "SELECT COUNT(DISTINCT inchikey) FROM compound_patents"
        ).fetchone()[0]

        print(f"\nDone in {elapsed:.1f}s:")
        print(f"  {row_count:,} rows indexed")
        print(f"  {unique_keys:,} unique InChIKeys")
        print(f"  Database: {db_path} ({db_path.stat().st_size / 1024 / 1024:.1f} MB)")

    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
