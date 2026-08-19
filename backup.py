import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

# ============================================================
# CONFIG
# ============================================================

START_DATE = datetime(
    2026, 1, 1,
    tzinfo=ZoneInfo("Asia/Kolkata")
).date()

TODAY_IST = datetime.now(
    ZoneInfo("Asia/Kolkata")
).date()

# Yesterday only
END_DATE = TODAY_IST - timedelta(days=1)

BASE_URL = "https://bfilmyapi.pages.dev/daily/data"
OUTPUT_ROOT = "daily/data"

MAX_WORKERS = 50

FILES = [
    "finaldetailed.json",
    "finalsummary.json",
]

# ============================================================
# DATES
# ============================================================

dates = []

current = START_DATE

while current <= END_DATE:
    dates.append(current)
    current += timedelta(days=1)

jobs = [
    (date, filename)
    for date in dates
    for filename in FILES
]

print("=" * 60)
print("🚀 DAILY BACKUP")
print("=" * 60)
print(f"📅 Start       : {START_DATE}")
print(f"📅 End         : {END_DATE} (yesterday IST)")
print(f"📆 Dates       : {len(dates)}")
print(f"📄 Files/date  : {len(FILES)}")
print(f"📦 Total jobs  : {len(jobs)}")
print(f"⚡ Workers     : {MAX_WORKERS}")
print("=" * 60)


# ============================================================
# DOWNLOAD
# ============================================================

def download(item):
    date, filename = item

    date_str = date.strftime("%Y%m%d")

    url = f"{BASE_URL}/{date_str}/{filename}"

    output_dir = os.path.join(
        OUTPUT_ROOT,
        date_str
    )

    output_file = os.path.join(
        output_dir,
        filename
    )

    os.makedirs(output_dir, exist_ok=True)

    try:
        response = requests.get(
            url,
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        # 404 = normal/missing file → skip
        if response.status_code == 404:
            return date_str, filename, 0, "404"

        response.raise_for_status()

        with open(output_file, "wb") as f:
            f.write(response.content)

        return date_str, filename, len(response.content), None

    except Exception as e:
        return date_str, filename, 0, str(e)


# ============================================================
# PARALLEL FETCH
# ============================================================

success = 0
not_found = 0
failed = []

with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:

    futures = [
        executor.submit(download, job)
        for job in jobs
    ]

    for future in as_completed(futures):

        date_str, filename, size, error = future.result()

        if error == "404":
            not_found += 1

            print(
                f"⚪ {date_str}/{filename} → 404, skipped"
            )

        elif error:
            failed.append(
                (date_str, filename, error)
            )

            print(
                f"❌ {date_str}/{filename} → {error}"
            )

        else:
            success += 1

            print(
                f"✅ {date_str}/{filename} "
                f"({size:,} bytes)"
            )


# ============================================================
# SUMMARY
# ============================================================

print()
print("=" * 60)
print("📊 SUMMARY")
print("=" * 60)
print(f"✅ Downloaded : {success}")
print(f"⚪ 404 skipped : {not_found}")
print(f"❌ Other fail  : {len(failed)}")
print(f"📦 Total jobs  : {len(jobs)}")

# ============================================================
# ONLY REAL ERRORS STOP THE PUSH
# ============================================================

if failed:

    print()
    print("❌ FAILED FILES:")

    for date_str, filename, error in failed:
        print(
            f"   {date_str}/{filename} → {error}"
        )

    print()
    print("🛑 NOT PUSHING — REAL DOWNLOAD ERRORS FOUND.")

    raise SystemExit(1)


# ============================================================
# GIT ADD
# ============================================================

print()
print("📦 Adding daily data...")

subprocess.run(
    [
        "git",
        "add",
        "--",
        OUTPUT_ROOT
    ],
    check=True
)


# ============================================================
# CHECK CHANGES
# ============================================================

status = subprocess.run(
    [
        "git",
        "status",
        "--porcelain"
    ],
    capture_output=True,
    text=True,
    check=True
)

if not status.stdout.strip():
    print("ℹ️ No changes to commit.")
    raise SystemExit(0)


# ============================================================
# COMMIT
# ============================================================

print("💾 Committing...")

subprocess.run(
    [
        "git",
        "commit",
        "-m",
        f"Backup daily data {START_DATE} to {END_DATE}"
    ],
    check=True
)


# ============================================================
# FORCE PUSH
# ============================================================

branch = subprocess.run(
    [
        "git",
        "branch",
        "--show-current"
    ],
    capture_output=True,
    text=True,
    check=True
).stdout.strip()

if not branch:
    raise SystemExit(
        "❌ Could not determine current branch."
    )

print(
    f"🚀 Force pushing → origin/{branch}"
)

subprocess.run(
    [
        "git",
        "push",
        "origin",
        branch,
        "--force"
    ],
    check=True
)

print()
print("=" * 60)
print("✅ BACKUP COMPLETE")
print("=" * 60)
print(f"📅 {START_DATE} → {END_DATE}")
print(f"✅ Downloaded : {success}")
print(f"⚪ 404 skipped : {not_found}")
print("🚀 Force push completed")
print("=" * 60)
