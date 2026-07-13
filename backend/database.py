# database.py — Local SQLite database for caching product reviews and analysis results

import sqlite3
import json
import os
from typing import Dict, Any, Optional, List

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache.db")


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            asin TEXT PRIMARY KEY,
            name TEXT,
            domain TEXT,
            url TEXT,
            analytics TEXT,
            reviews TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def save_product_data(
    asin: str,
    name: str,
    domain: str,
    url: str,
    analytics: Dict[str, Any],
    reviews: List[Dict[str, Any]]
):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO products (asin, name, domain, url, analytics, reviews, created_at)
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(asin) DO UPDATE SET
            name=excluded.name,
            domain=excluded.domain,
            url=excluded.url,
            analytics=excluded.analytics,
            reviews=excluded.reviews,
            created_at=CURRENT_TIMESTAMP
        """,
        (
            asin,
            name,
            domain,
            url,
            json.dumps(analytics),
            json.dumps(reviews),
        )
    )
    conn.commit()
    conn.close()


def get_product_data(asin: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name, domain, url, analytics, reviews FROM products WHERE asin = ?",
        (asin,)
    )
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "asin": asin,
            "name": row["name"],
            "domain": row["domain"],
            "url": row["url"],
            "analytics": json.loads(row["analytics"]),
            "reviews": json.loads(row["reviews"]),
        }
    return None
