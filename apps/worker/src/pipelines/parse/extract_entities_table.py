import csv
import json
import sys
from pathlib import Path


COORD_KEYS = [
    "vertices",
    "startPoint",
    "endPoint",
    "center",
    "position",
    "anchorPoint",
    "middleOfText",
    "linearOrAngularPoint1",
    "linearOrAngularPoint2",
]

CSV_COLUMNS = [
    "handle",
    "type",
    "layer",
    "ownerHandle",
    "coordinates",
    "text",
    "textHeight",
    "name",
    "lineType",
    "radius",
    "width",
    "block",
    "dimensionType",
    "actualMeasurement",
    "xScale",
    "yScale",
    "zScale",
    "contextData",
]


def _collect_coordinates(entity: dict) -> str:
    coords = []
    for key in COORD_KEYS:
        if key in entity:
            coords.append({"key": key, "value": entity.get(key)})
    return json.dumps(coords, separators=(",", ":"), ensure_ascii=False)


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
    rows = []
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        row = {
            "handle": ent.get("handle"),
            "type": ent.get("type"),
            "layer": ent.get("layer"),
            "ownerHandle": ent.get("ownerHandle"),
            "coordinates": _collect_coordinates(ent),
            "text": ent.get("text"),
            "textHeight": ent.get("textHeight"),
            "name": ent.get("name"),
            "lineType": ent.get("lineType"),
            "radius": ent.get("radius"),
            "width": ent.get("width"),
            "block": ent.get("block"),
            "dimensionType": ent.get("dimensionType"),
            "actualMeasurement": ent.get("actualMeasurement"),
            "xScale": ent.get("xScale"),
            "yScale": ent.get("yScale"),
            "zScale": ent.get("zScale"),
            "contextData": ent.get("contextData"),
        }
        rows.append(row)

    if out_path:
        with out_path.open("w", newline="", encoding="utf-8") as fp:
            writer = csv.DictWriter(fp, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
    else:
        writer = csv.DictWriter(sys.stdout, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
