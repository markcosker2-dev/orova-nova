import os

# Keep tests deterministic and offline: firewall goal alignment falls back to
# the keyword heuristic instead of calling the embedding API.
os.environ.setdefault("FIREWALL_SEMANTIC_ALIGNMENT", "0")
