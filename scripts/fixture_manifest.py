"""Validate the checked-in manifest, or explicitly regenerate its content digests."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fixture_contract.registry import ROOT, FixtureContract, decode_json, load_contract


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Recompute hashes after a reviewed artifact edit")
    args = parser.parse_args()
    if args.write:
        document = decode_json((ROOT / "manifest.json").read_bytes())
        FixtureContract.model_validate(document)  # Validate paths before reading any source bytes.
        for artifact in document["artifacts"]:
            artifact["digest"] = hashlib.sha256((ROOT / artifact["file"]).read_bytes()).hexdigest()
        (ROOT / "manifest.json").write_text(json.dumps(document, indent=2) + "\n")
    contract = load_contract()
    print(f"Fixture manifest v{contract.version} verified; {len(contract.artifacts)} artifacts; digest {contract.digest}.")


if __name__ == "__main__":
    main()
