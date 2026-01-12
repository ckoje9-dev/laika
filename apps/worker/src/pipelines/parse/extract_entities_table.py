import csv
import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python apps/worker/src/pipelines/parse/extract_entities_table.py <input.json> [output.csv]")
        return 1
    in_path = Path(sys.argv[1])
    if not in_path.exists():
        print(f"Input not found: {in_path}")
        return 1
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    with in_path.open("r", encoding="utf-8") as fp:
        data = json.load(fp)

    entities = data.get("entities") or []
    keys = set()
    rows = []
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        keys.update(ent.keys())

    columns = ["handle"] + sorted(k for k in keys if k != "handle")

    for ent in entities:
        if not isinstance(ent, dict):
            continue
        row = {}
        for key in columns:
            value = ent.get(key)
            if isinstance(value, (dict, list)):
                row[key] = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
            else:
                row[key] = value
        rows.append(row)

    if out_path:
        with out_path.open("w", newline="", encoding="utf-8") as fp:
            writer = csv.DictWriter(fp, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
    else:
        writer = csv.DictWriter(sys.stdout, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
