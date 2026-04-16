import sys
from pathlib import Path

import yaml


def load_paths(path: Path):
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    return set(spec.get("paths", {}).keys())


def main():
    public_spec = load_paths(Path("openapi/public-v1.yaml"))
    required = {
        "/api/v1/dashboard/summary",
        "/api/v1/trends",
        "/api/v1/evidences/{signal_id}",
        "/api/v1/compliance/removal-requests",
    }
    missing = sorted(required - public_spec)
    if missing:
        print("Missing API paths:", ", ".join(missing))
        sys.exit(1)
    print("Contract test passed.")


if __name__ == "__main__":
    main()
