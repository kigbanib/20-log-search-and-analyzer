"""
Seed script to populate a development database with realistic demo log data.

Thin legacy entry point kept for the README's `python seed_demo_data.py` —
the dataset and the idempotent "seed only if empty" helper now live in
`app/seed.py`, which the FastAPI startup hook also uses (SEED_ON_START=true).

Run with: python seed_demo_data.py
"""

from app.seed import main

if __name__ == "__main__":
    raise SystemExit(main())
