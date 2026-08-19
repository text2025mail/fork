import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

# ============================================================
# CONFIG
# ============================================================

DATE = "20260819"

BASE_URL = f"https://bfilmyapi.pages.dev/daily/data/{DATE}"
OUTPUT_DIR = "daily/data"

FILES = [
    *(f"detailed{i}.json" for i in range(1, 10)),
    "finaldetailed.json",
    "finalsummary.json",
    *(f"movie_summary{i}.json" for i in range(1, 10)),
]

MAX_WORKERS = 20

# ============================================================
# FETCH
# ============================================================

os.makedirs(OUTPUT_DIR, exist_ok=True)

session = requests.Session()

def download(filename):
    url = f"{BASE_URL}/{filename}"
    output = os.path.join(OUTPUT_DIR, filename)

    try:
        r = session.get(url, timeout=30)
        r.raise_for_status()

        # Write exactly what was downloaded
        with open(output, "wb") as f:
            f.write(r.content)

        return filename, len(r.content), None

    except Exception as e:
        return filename, 0, str(e)


print(f"🚀 Fetching {len(FILES)} files...")
print(f"📅 Date: {DATE}")
print(f"📂 Output: {OUTPUT_DIR}")
print()

failed = []

with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    futures = [executor.submit(download, f) for f in FILES]

    for future in as_completed(futures):
        filename, size, error = future.result()

        if error:
            print(f"❌ {filename}: {error}")
            failed.append(filename)
        else:
            print(f"✅ {filename}: {size:,} bytes")

# ============================================================
# STOP IF ANY DOWNLOAD FAILED
# ============================================================

if failed:
    print()
    print("❌ DOWNLOAD FAILED")
    print("Failed files:")
    for f in failed:
        print(f"   - {f}")
    raise SystemExit(1)

# ============================================================
# GIT
# ============================================================

print()
print("📦 Adding files...")

subprocess.run(
    ["git", "add", "--", OUTPUT_DIR],
    check=True
)

# Check whether anything actually changed
status = subprocess.run(
    ["git", "status", "--porcelain"],
    capture_output=True,
    text=True,
    check=True
)

if not status.stdout.strip():
    print("ℹ️ No changes to commit.")
    raise SystemExit(0)

print("💾 Committing...")

subprocess.run(
    [
        "git",
        "commit",
        "-m",
        f"Update daily data {DATE}"
    ],
    check=True
)

# ============================================================
# FORCE PUSH
# ============================================================

print("🚀 Force pushing...")

branch = subprocess.run(
    ["git", "branch", "--show-current"],
    capture_output=True,
    text=True,
    check=True
).stdout.strip()

if not branch:
    raise SystemExit("❌ Could not determine current branch.")

subprocess.run(
    ["git", "push", "origin", branch, "--force"],
    check=True
)

print()
print("✅ DONE")
print(f"📂 {OUTPUT_DIR}/")
print(f"📄 {len(FILES)} files uploaded")
print(f"🌿 Branch: {branch}")
print("🚀 Force push completed.")
