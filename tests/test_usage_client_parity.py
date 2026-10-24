"""The vendored usage_client.py must stay byte-identical to the pinned copy.

The source of truth is the plugin-stats project's client/usage_client.py; never edit
the copy here. Re-copy it and update scripts/client_manifest.json together.
"""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLIENT = ROOT / "proofline" / "usage_client.py"
MANIFEST = ROOT / "scripts" / "client_manifest.json"


def test_vendored_usage_client_matches_its_pin():
    pin = json.loads(MANIFEST.read_text(encoding="utf-8"))["usage_client.py"]
    assert hashlib.sha256(CLIENT.read_bytes()).hexdigest() == pin, (
        "proofline/usage_client.py differs from its pin; re-copy it from plugin-stats, do not edit it"
    )
