from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError


def validate(data_path: Path, schema_path: Path) -> list[str]:
    with schema_path.open("r", encoding="utf-8") as f:
        schema = json.load(f)
    with data_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    return [f"{'.'.join(str(p) for p in e.absolute_path) or '(root)'}: {e.message}" for e in errors]


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate JSON against a schema.")
    parser.add_argument("data", help="Path to the JSON data file")
    parser.add_argument("schema", help="Path to the JSON Schema file")
    args = parser.parse_args()

    errors = validate(Path(args.data), Path(args.schema))
    if errors:
        print(f"Validation FAILED ({len(errors)} error(s)):")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    else:
        print("Validation OK.")


if __name__ == "__main__":
    main()
