import subprocess
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent


def test_vortexctl_sources_generated_env_and_no_legacy():
    r = subprocess.run(["bash", str(REPO / "tests" / "test_vortexctl.sh")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
