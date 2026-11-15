import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="saajha-test-")
os.environ["SAAJHA_DATA_DIR"] = _tmp
os.environ["SAAJHA_FORCE_OFFLINE"] = "1"  # tests never call Gemini
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def pytest_sessionfinish(session, exitstatus):
    """Write a small report the System-status screen shows (real counts, not typed in)."""
    import json
    from datetime import datetime
    rep = session.config.pluginmanager.get_plugin("terminalreporter")
    passed = len(rep.stats.get("passed", [])) if rep else None
    failed = len(rep.stats.get("failed", [])) if rep else None
    out = Path(__file__).resolve().parent.parent / "data" / "test_report.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"passed": passed, "failed": failed, "run_at": datetime.now().isoformat(timespec="seconds")}))
