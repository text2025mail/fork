import os
import json
from datetime import datetime, timedelta

START = datetime.strptime("20251219", "%Y%m%d")
END   = datetime.strptime("20260123", "%Y%m%d")

ROOTS = [
    "advance/data",
    "daily/data"
]

# source remap
SOURCE_MAP = {
    "BMS": "B",
    "District": "D"
}

# -------- detailed compressor --------
def compress_detailed(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        print(f"SKIP (invalid json): {path}")
        return

    last_updated = None
    root = data

    if isinstance(root, dict):
        last_updated = root.get("last_updated")
        if "data" in root and isinstance(root["data"], list):
            root = root["data"]
        else:
            print(f"SKIP (no usable data list): {path}")
            return

    if not isinstance(root, list):
        print(f"SKIP (root not list): {path}")
        return

    out = []
    for row in root:
        row = dict(row)
        row.pop("address", None)
        row.pop("date", None)
        src = row.pop("source", None)
        if src:
            row["s"] = SOURCE_MAP.get(src, src[0].upper() if src else None)
        out.append(row)

    if last_updated:
        obj = {"last_updated": last_updated, "data": out}
        txt = json.dumps(obj, ensure_ascii=False, separators=(',',':'))
    else:
        txt = json.dumps(out, ensure_ascii=False, separators=(',',':'))

    with open(path, "w", encoding="utf-8") as f:
        f.write(txt)

    print(f"OK detailed: {path}")


# -------- summary compressor --------
def compress_summary(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        print(f"SKIP (invalid json): {path}")
        return

    # just minify
    txt = json.dumps(data, ensure_ascii=False, separators=(',',':'))

    with open(path, "w", encoding="utf-8") as f:
        f.write(txt)

    print(f"OK summary:  {path}")


# -------- main process --------
def process():
    day = START
    while day <= END:
        ds = day.strftime("%Y%m%d")
        for base in ROOTS:
            folder = os.path.join(base, ds)

            det_path = os.path.join(folder, "finaldetailed.json")
            sum_path = os.path.join(folder, "finalsummary.json")

            if os.path.exists(det_path):
                compress_detailed(det_path)

            if os.path.exists(sum_path):
                compress_summary(sum_path)

        day += timedelta(days=1)

    print("DONE")


if __name__ == "__main__":
    process()
