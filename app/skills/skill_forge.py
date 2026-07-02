"""
Skill Forge — Dynamic Tool Acquisition (sandboxed, approval-gated)
==================================================================
Lets Nova draft new Python skills at runtime, but with three hard gates
before anything becomes callable:

  1. STATIC SCREENING — the code must parse, imports are allowlisted, and
     dangerous builtins (eval/exec/open/__import__/...) are rejected.
  2. SANDBOXED SMOKE TEST — the draft is imported in a separate
     `python -I` (isolated) subprocess with a hard timeout, so top-level
     crashes or hangs never touch the main process.
  3. HUMAN APPROVAL — activation requires Mark's Telegram approval through
     the same firewall approval loop used for destructive tools.

A skill file must define `run(**kwargs)` (sync or async). Activated skills
live in data/learned_skills/ and are exposed to the planner through the
single dispatcher tool `use_forged_skill`.
"""

import ast
import asyncio
import hashlib
import importlib.util
import inspect
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).resolve().parents[2] / "data" / "learned_skills"

ALLOWED_IMPORTS = {
    "json", "re", "math", "datetime", "statistics", "collections",
    "itertools", "functools", "typing", "urllib", "urllib.parse",
    "asyncio", "httpx", "textwrap", "string", "random", "time",
}
FORBIDDEN_NAMES = {
    "eval", "exec", "compile", "__import__", "open", "input", "globals",
    "locals", "vars", "setattr", "delattr", "breakpoint", "exit", "quit",
}
FORBIDDEN_MODULES = {
    "os", "sys", "subprocess", "socket", "shutil", "pathlib", "ctypes",
    "multiprocessing", "threading", "importlib", "pickle", "marshal",
    "builtins", "signal", "sqlite3", "tempfile", "glob", "inspect",
}
MAX_CODE_CHARS = 20000


def _code_hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()[:16]


def _screen_code(code: str) -> list:
    """Static AST screening. Returns a list of violations (empty = clean)."""
    violations = []
    if len(code) > MAX_CODE_CHARS:
        return [f"Code too long ({len(code)} > {MAX_CODE_CHARS} chars)"]
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"Syntax error: {e}"]

    has_run = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            for mod in names:
                root = (mod or "").split(".")[0]
                if root in FORBIDDEN_MODULES:
                    violations.append(f"Forbidden import: {mod}")
                elif mod not in ALLOWED_IMPORTS and root not in ALLOWED_IMPORTS:
                    violations.append(f"Import not in allowlist: {mod}")
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            violations.append(f"Forbidden builtin: {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in ("system", "popen", "spawn", "fork"):
            violations.append(f"Forbidden attribute call: .{node.attr}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "run":
            has_run = True

    if not has_run:
        violations.append("Skill must define a top-level run(**kwargs) function")
    return violations


async def propose_skill(name: str, description: str, code: str) -> str:
    """
    Draft a new skill. The code is screened, saved as a draft, and an
    approval request is sent to Mark. Nothing becomes callable yet.
    """
    if not name.isidentifier() or name.startswith("_"):
        return f"Invalid skill name '{name}': must be a plain Python identifier."

    violations = _screen_code(code)
    if violations:
        return "Skill rejected by static screening:\n- " + "\n- ".join(violations[:10])

    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    draft_path = SKILLS_DIR / f"{name}.py.draft"
    header = f'"""FORGED SKILL: {name}\n{description[:300]}\n"""\n'
    draft_path.write_text(header + code, encoding="utf-8")

    test_result = await _smoke_test(draft_path)
    if not test_result["ok"]:
        draft_path.unlink(missing_ok=True)
        return f"Skill failed sandboxed smoke test: {test_result['error']}"

    try:
        from app.skills.approval_workflow import request_firewall_approval
        request_id = await request_firewall_approval(
            "skill_forge_activate",
            {"name": name, "code_hash": _code_hash(code)},
            f"New forged skill '{name}': {description[:150]}",
        )
    except Exception as e:
        return f"Draft saved but approval request failed: {e}"

    logger.info(f"[SKILL_FORGE] Drafted '{name}' ({request_id}) — awaiting approval")
    return (
        f"Skill '{name}' drafted and passed screening + sandbox test. "
        f"Approval requested ({request_id}). After Mark approves on Telegram, "
        f"call activate_skill('{name}')."
    )


async def _smoke_test(path: Path, timeout_s: float = 10.0) -> dict:
    """Import the draft in an isolated subprocess (`python -I`) so top-level
    crashes, hangs, or resource abuse cannot affect the main process."""
    test_code = (
        "import importlib.util\n"
        "from importlib.machinery import SourceFileLoader\n"
        # SourceFileLoader accepts the .py.draft extension that
        # spec_from_file_location refuses.
        f"loader = SourceFileLoader('forged_test', r'{path}')\n"
        "spec = importlib.util.spec_from_loader('forged_test', loader)\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "loader.exec_module(mod)\n"
        "assert callable(getattr(mod, 'run', None)), 'run() missing'\n"
        "print('SMOKE_OK')\n"
    )
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-I", "-c", test_code,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except asyncio.TimeoutError:
            proc.kill()
            return {"ok": False, "error": f"Timed out after {timeout_s}s (possible hang)"}
        if proc.returncode == 0 and b"SMOKE_OK" in stdout:
            return {"ok": True, "error": None}
        return {"ok": False, "error": (stderr or stdout).decode(errors="replace")[:400]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def activate_skill(name: str) -> str:
    """Activate a drafted skill — only succeeds if Mark approved it."""
    draft_path = SKILLS_DIR / f"{name}.py.draft"
    if not draft_path.exists():
        return f"No draft found for '{name}'. Call propose_skill first."

    code = draft_path.read_text(encoding="utf-8")
    # Re-screen at activation: the file could have been altered on disk
    # between proposal and approval.
    violations = _screen_code(code)
    if violations:
        draft_path.unlink(missing_ok=True)
        return "Draft failed re-screening (deleted):\n- " + "\n- ".join(violations[:5])

    try:
        from app.skills.approval_workflow import is_action_approved
        approved = await is_action_approved(
            "skill_forge_activate",
            {"name": name, "code_hash": _code_hash(code.split('"""\n', 2)[-1] if '"""\n' in code else code)},
        )
    except Exception as e:
        return f"Approval check failed: {e}"

    if not approved:
        return f"Skill '{name}' is NOT approved yet. Ask Mark to approve on Telegram, then retry."

    active_path = SKILLS_DIR / f"{name}.py"
    draft_path.rename(active_path)
    logger.info(f"[SKILL_FORGE] Activated skill '{name}'")
    return f"Skill '{name}' activated. Call it via use_forged_skill(name='{name}', kwargs_json='{{...}}')."


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(f"forged_{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def use_forged_skill(name: str, kwargs_json: str = "{}") -> str:
    """Dispatcher: run an ACTIVATED forged skill with JSON kwargs."""
    active_path = SKILLS_DIR / f"{name}.py"
    if not active_path.exists():
        available = [p.stem for p in SKILLS_DIR.glob("*.py")] if SKILLS_DIR.exists() else []
        return f"No activated skill '{name}'. Available: {available or 'none'}"

    # Defense in depth: re-screen before every execution
    violations = _screen_code(active_path.read_text(encoding="utf-8"))
    if violations:
        return f"Skill '{name}' failed integrity screening; refusing to run."

    try:
        kwargs = json.loads(kwargs_json) if kwargs_json else {}
        if not isinstance(kwargs, dict):
            return "kwargs_json must decode to a JSON object."
    except json.JSONDecodeError as e:
        return f"Invalid kwargs_json: {e}"

    try:
        mod = _load_module(active_path)
        run = getattr(mod, "run")
        if inspect.iscoroutinefunction(run):
            result = await asyncio.wait_for(run(**kwargs), timeout=60.0)
        else:
            loop = asyncio.get_running_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: run(**kwargs)), timeout=60.0
            )
        return str(result)[:4000]
    except asyncio.TimeoutError:
        return f"Skill '{name}' timed out after 60s."
    except Exception as e:
        return f"Skill '{name}' raised: {e}"


async def list_forged_skills() -> str:
    """List activated and drafted forged skills."""
    if not SKILLS_DIR.exists():
        return "No forged skills yet."
    active = [p.stem for p in SKILLS_DIR.glob("*.py")]
    drafts = [p.name.replace(".py.draft", "") for p in SKILLS_DIR.glob("*.py.draft")]
    return json.dumps({"active": active, "drafts_awaiting_approval": drafts})
