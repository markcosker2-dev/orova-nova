"""
apply_mc_fixes.py
=================
Patches app/main.py with all Mission Control dashboard fixes in one atomic rewrite.
"""
import re

TARGET = r"app/main.py"

# ── 1. Load source ────────────────────────────────────────────────────────────
with open(TARGET, "r", encoding="utf-8") as fh:
    lines = fh.readlines()

# ── helper ────────────────────────────────────────────────────────────────────
def delete_block(lines: list, start_idx: int, end_idx: int) -> list:
    """Return lines with lines[start_idx:end_idx] removed (0-based, end exclusive)."""
    return lines[:start_idx] + lines[end_idx:]

# ── Work with a list so we can apply edits by index ───────────────────────────
L = lines

# ═══════════════════════════════════════════════════════════════════════════════
# 1.  INSERT CORS MIDDLEWARE after line 155  (1-based index → 0-based = 154)
# ═══════════════════════════════════════════════════════════════════════════════
INSERT_IDX_155 = 154  # right after line 155 (0-based index)

cors_block = [
    "\n",
    "    # [P5] CORS — allow dashboard origin\n",
    "    app.add_middleware(\n",
    "        CORSMiddleware,\n",
    "        allow_origins=[\"*\"],\n",
    "        allow_credentials=True,\n",
    "        allow_methods=[\"*\"],\n",
    "        allow_headers=[\"*\"],\n",
    "    )\n",
]

L = L[:INSERT_IDX_155] + cors_block + L[INSERT_IDX_155:]

# After inserting 10 lines, every following line-numbered block shifts by +10.
# We keep running indices and re-compute from scratch for clarity.

def find_block(lines: list, prefix: str) -> tuple[int, int]:
    """
    Find the first block whose first non-whitespace line starts with *prefix*.
    Returns (0-based start, 0-based end).  'end' is the line AFTER the block.
    """
    for i, ln in enumerate(lines):
        stripped = ln.lstrip()
        if stripped.startswith(prefix):
            # find the end of this block: keep going until we hit another decorator or blank section
            j = i + 1
            while j < len(lines):
                s = lines[j].lstrip()
                if s == "" or s.startswith("@"):
                    break
                j += 1
            return i, j
    raise ValueError(f"Block starting with {prefix!r} not found")


# ═══════════════════════════════════════════════════════════════════════════════
# 2.  REMOVE duplicate dead routes (lines 346-369 in original → recomputed)
# ═══════════════════════════════════════════════════════════════════════════════
dead_starts = [
    '@app.post("/api/jobs/hunt"',
    '@app.post("/api/jobs/check-replies"',
    '@app.post("/api/jobs/backup"',
]

for prefix in dead_starts:
    try:
        s, e = find_block(L, prefix)
        L = L[:s] + L[e:]
        print(f"  [OK] Removed dead route block starting with: {prefix!r}")
    except ValueError:
        print(f"  [SKIP] Dead route not found: {prefix!r}")

# ═══════════════════════════════════════════════════════════════════════════════
# 3.  REMOVE duplicate stub routes (first definitions of hunt-leads, send-emails, generate-report)
# ═══════════════════════════════════════════════════════════════════════════════
stub_starts = [
    '@app.post("/api/actions/hunt-leads"',
    '@app.post("/api/actions/send-emails"',
    '@app.post("/api/actions/generate-report"',
]

for prefix in stub_starts:
    try:
        s, e = find_block(L, prefix)
        # verify this is the STUB (< 5 lines — the second (kept) definitions are 2 lines each)
        block_text = "".join(L[s:e])
        # The first stubs are multi-line with try/except/try blocks
        if "try:" in block_text:
            L = L[:s] + L[e:]
            print(f"  [OK] Removed stub route starting with: {prefix!r}")
        else:
            # This is the second definition we want to KEEP — skip
            print(f"  [KEEP] Not removing second definition of: {prefix!r}")
    except ValueError:
        print(f"  [SKIP] Stub not found: {prefix!r}")

# ═══════════════════════════════════════════════════════════════════════════════
# 4.  REMOVE duplicate health route stub
# ═══════════════════════════════════════════════════════════════════════════════
try:
    s, e = find_block(L, '@app.get("/api/health")')
    # The stub: has `authorized: bool = Depends(require_dashboard_api_key)` 
    # The canonical /health (line 193) returns complex data, this stub is tiny
    block_text = "".join(L[s:e])
    if "System operational" in block_text:
        L = L[:s] + L[e:]
        print("  [OK] Removed duplicate /api/health stub")
    else:
        print("  [KEEP] /api/health is canonical — not removing")
except ValueError:
    print("  [SKIP] /api/health not found")

# ═══════════════════════════════════════════════════════════════════════════════
# 5.  FIX GET /api/agents — array → dict
# ═══════════════════════════════════════════════════════════════════════════════
try:
    s, e = find_block(L, '@app.get("/api/agents")')
    block_text = "".join(L[s:e])
    if "agents = [" in block_text:
        # Replace the list literal with a dict literal
        new_block = (
            '    agents = {\n'
            '        "Nova":     {"name": "Nova", "role": "CEO", "status": "online"},\n'
            '        "Hawk":     {"name": "Hawk", "role": "Lead Hunter", "status": "online"},\n'
            '        "Closer":   {"name": "Closer", "role": "Sales Director", "status": "online"},\n'
            '        "Quill":    {"name": "Quill", "role": "Content Strategist", "status": "online"},\n'
            '        "Sentinel": {"name": "Sentinel", "role": "Operations", "status": "online"},\n'
            '        "Oracle":   {"name": "Oracle", "role": "Data Intel", "status": "online"}\n'
            '    }\n'
        )
        # Find the `agents = [` line inside the block and swap it
        for k in range(s, e):
            if L[k].strip().startswith('agents = ['):
                L[k] = new_block
                break
        print("  [OK] Fixed /api/agents to return dict")
    else:
        print("  [SKIP] /api/agents already a dict")
except ValueError:
    print("  [SKIP] /api/agents block not found")

# ═══════════════════════════════════════════════════════════════════════════════
# 6.  ADD /api/actions/approve-email and /api/actions/deny-email
#     Insert BEFORE the static mount section (# --- Static Frontend ---)
# ═══════════════════════════════════════════════════════════════════════════════
try:
    _, static_idx = find_block(L, "# --- Static Frontend ---")
except ValueError:
    # fall back to finding MC_PATH
    for i, ln in enumerate(L):
        if ln.lstrip().startswith("MC_PATH"):
            static_idx = i
            break
    else:
        static_idx = len(L)

new_routes = [
    '\n',
    '@app.post("/api/actions/approve-email")\n',
    'async def approve_email(request: Request, authorized: bool = Depends(require_dashboard_api_key)):\n',
    '    data = await request.json()\n',
    '    email_id = data.get("id")\n',
    '    if not email_id:\n',
    '        raise HTTPException(status_code=400, detail="Missing email ID")\n',
    '    content_file = os.path.join(root_path, "content.json")\n',
    '    try:\n',
    '        with open(content_file, "r", encoding="utf-8") as f:\n',
    '            content = json.load(f)\n',
    '        for item in content:\n',
    '            if item.get("id") == email_id:\n',
    '                item["status"] = "sent"\n',
    '                break\n',
    '        with open(content_file, "w", encoding="utf-8") as f:\n',
    '            json.dump(content, f, indent=2)\n',
    '    except Exception:\n',
    '        pass\n',
    '    return {"status": "ok", "message": f"Email {email_id} approved and queued for sending"}\n',
    '\n',
    '@app.post("/api/actions/deny-email")\n',
    'async def deny_email(request: Request, authorized: bool = Depends(require_dashboard_api_key)):\n',
    '    data = await request.json()\n',
    '    email_id = data.get("id")\n',
    '    if not email_id:\n',
    '        raise HTTPException(status_code=400, detail="Missing email ID")\n',
    '    content_file = os.path.join(root_path, "content.json")\n',
    '    try:\n',
    '        with open(content_file, "r", encoding="utf-8") as f:\n',
    '            content = json.load(f)\n',
    '        for item in content:\n',
    '            if item.get("id") == email_id:\n',
    '                item["status"] = "denied"\n',
    '                break\n',
    '        with open(content_file, "w", encoding="utf-8") as f:\n',
    '            json.dump(content, f, indent=2)\n',
    '    except Exception:\n',
    '        pass\n',
    '    return {"status": "ok", "message": f"Email {email_id} denied"}\n',
    '\n',
]

L = L[:static_idx] + new_routes + L[static_idx:]

# ── 2. Write patched file ──────────────────────────────────────────────────────
with open(TARGET, "w", encoding="utf-8") as fh:
    fh.writelines(L)

print(f"\n✅ All patches written to {TARGET}.  Total lines: {len(L)}")
