"""Live outbound sourcing scanners (Phase 3).

Each scanner turns a public source (GitHub, Hacker News, arXiv) into
``RawSignal`` objects and hands them to the *shared* ingestion pipeline - the
exact same entry point the synthetic loader uses - so dedup and entity
resolution apply identically. Nothing here writes to the store directly.
"""
