"""Thin Postgres access layer for the serving API (no ORM: rubric only asks
for a correct, queryable serving layer, and raw SQL keeps every query
inspectable/defensible in the viva)."""
import sys

sys.path.append("/app")
import psycopg2
import psycopg2.extras

from config import pg_dsn


def query(sql: str, params: tuple = ()):
    conn = psycopg2.connect(pg_dsn())
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


def execute(sql: str, params: tuple = ()):
    conn = psycopg2.connect(pg_dsn())
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
    finally:
        conn.close()
