import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests


# ============================================================
# CONFIG
# ============================================================

IST = ZoneInfo("Asia/Kolkata")

START_DATE = datetime(
    2026, 1, 1,
    tzinfo=IST
).date()

TODAY_IST = datetime.now(IST).date()

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

print(
    f"📅 Start       : {START_DATE}"
)

print(
    f"📅 End         : {END_DATE} (yesterday IST)"
)

print(
    f"📆 Dates       : {len(dates)}"
)

print(
    f"📄 Files/date  : {len(FILES)}"
)

print(
    f"📦 Total jobs  : {len(jobs)}"
)

print(
    f"⚡ Workers     : {MAX_WORKERS}"
)

print("=" * 60)


# ============================================================
# DOWNLOAD
# ============================================================

def download(item):

    date, filename = item

    date_str = date.strftime(
        "%Y%m%d"
    )

    url = (
        f"{BASE_URL}/"
        f"{date_str}/"
        f"{filename}"
    )

    output_dir = os.path.join(
        OUTPUT_ROOT,
        date_str
    )

    output_file = os.path.join(
        output_dir,
        filename
    )

    os.makedirs(
        output_dir,
        exist_ok=True
    )

    try:

        response = requests.get(
            url,
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        # ----------------------------------------------------
        # 404 = normal missing file
        # ----------------------------------------------------

        if response.status_code == 404:

            return (
                date_str,
                filename,
                0,
                "404"
            )

        response.raise_for_status()

        content = response.content

        # ----------------------------------------------------
        # Don't create an empty file
        # ----------------------------------------------------

        if not content:

            return (
                date_str,
                filename,
                0,
                "Empty response"
            )

        with open(
            output_file,
            "wb"
        ) as f:

            f.write(content)

        return (
            date_str,
            filename,
            len(content),
            None
        )

    except Exception as e:

        return (
            date_str,
            filename,
            0,
            str(e)
        )


# ============================================================
# PARALLEL FETCH
# ============================================================

success = 0
not_found = 0
failed = []


with ThreadPoolExecutor(
    max_workers=MAX_WORKERS
) as executor:

    futures = [
        executor.submit(
            download,
            job
        )
        for job in jobs
    ]

    for future in as_completed(
        futures
    ):

        (
            date_str,
            filename,
            size,
            error
        ) = future.result()

        # ----------------------------------------------------
        # 404
        # ----------------------------------------------------

        if error == "404":

            not_found += 1

            print(
                f"⚪ {date_str}/{filename}"
                f" → 404, skipped"
            )

        # ----------------------------------------------------
        # REAL ERROR
        # ----------------------------------------------------

        elif error:

            failed.append(
                (
                    date_str,
                    filename,
                    error
                )
            )

            print(
                f"❌ {date_str}/{filename}"
                f" → {error}"
            )

        # ----------------------------------------------------
        # SUCCESS
        # ----------------------------------------------------

        else:

            success += 1

            print(
                f"✅ {date_str}/{filename}"
                f" ({size:,} bytes)"
            )


# ============================================================
# SUMMARY
# ============================================================

print()
print("=" * 60)
print("📊 SUMMARY")
print("=" * 60)

print(
    f"✅ Downloaded : {success}"
)

print(
    f"⚪ 404 skipped : {not_found}"
)

print(
    f"❌ Other fail  : {len(failed)}"
)

print(
    f"📦 Total jobs  : {len(jobs)}"
)


# ============================================================
# REAL DOWNLOAD ERRORS = STOP
# ============================================================

if failed:

    print()
    print(
        "❌ FAILED FILES:"
    )

    for (
        date_str,
        filename,
        error
    ) in failed:

        print(
            f"   {date_str}/{filename}"
            f" → {error}"
        )

    print()
    print(
        "🛑 NOT PUSHING — "
        "REAL DOWNLOAD ERRORS FOUND."
    )

    raise SystemExit(1)


# ============================================================
# GIT CONFIG
# ============================================================

print()
print(
    "⚙️ Configuring Git..."
)

subprocess.run(
    [
        "git",
        "config",
        "user.name",
        "github-actions[bot]"
    ],
    check=True
)

subprocess.run(
    [
        "git",
        "config",
        "user.email",
        "41898282+github-actions[bot]@users.noreply.github.com"
    ],
    check=True
)


# ============================================================
# GIT ADD
# ============================================================

print()
print(
    "📦 Adding daily data..."
)

subprocess.run(
    [
        "git",
        "add",
        "-A",
        "--",
        OUTPUT_ROOT
    ],
    check=True
)


# ============================================================
# CHECK STAGED CHANGES
# ============================================================

staged = subprocess.run(
    [
        "git",
        "diff",
        "--cached",
        "--quiet"
    ]
)

if staged.returncode == 0:

    print()
    print(
        "ℹ️ No changes to commit."
    )

    raise SystemExit(0)

elif staged.returncode != 1:

    raise SystemExit(
        "❌ Could not check staged changes."
    )


# ============================================================
# SHOW CHANGES
# ============================================================

print()
print(
    "📝 Changes to commit:"
)

subprocess.run(
    [
        "git",
        "diff",
        "--cached",
        "--stat"
    ],
    check=True
)


# ============================================================
# COMMIT
# ============================================================

commit_message = (
    f"Backup daily data "
    f"{START_DATE} to {END_DATE}"
)

print()
print(
    "💾 Committing..."
)

commit = subprocess.run(
    [
        "git",
        "commit",
        "-m",
        commit_message
    ],
    capture_output=True,
    text=True
)

print(
    commit.stdout
)

if commit.returncode != 0:

    print(
        commit.stderr
    )

    print()
    print(
        "❌ GIT COMMIT FAILED"
    )

    raise SystemExit(
        commit.returncode
    )


# ============================================================
# GET CURRENT BRANCH
# ============================================================

branch_result = subprocess.run(
    [
        "git",
        "branch",
        "--show-current"
    ],
    capture_output=True,
    text=True,
    check=True
)

branch = (
    branch_result.stdout
    .strip()
)


if not branch:

    # GitHub Actions fallback
    branch = os.environ.get(
        "GITHUB_REF_NAME",
        ""
    ).strip()


if not branch:

    raise SystemExit(
        "❌ Could not determine current branch."
    )


# ============================================================
# FORCE PUSH
# ============================================================

print()
print(
    f"🚀 Force pushing → origin/{branch}"
)

push = subprocess.run(
    [
        "git",
        "push",
        "origin",
        f"HEAD:{branch}",
        "--force"
    ],
    capture_output=True,
    text=True
)

print(
    push.stdout
)

if push.returncode != 0:

    print(
        push.stderr
    )

    raise SystemExit(
        push.returncode
    )


# ============================================================
# COMPLETE
# ============================================================

print()
print("=" * 60)
print("✅ BACKUP COMPLETE")
print("=" * 60)

print(
    f"📅 {START_DATE} → {END_DATE}"
)

print(
    f"✅ Downloaded : {success}"
)

print(
    f"⚪ 404 skipped : {not_found}"
)

print(
    "🚀 Force push completed"
)

print("=" * 60)
