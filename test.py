import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from zoneinfo import ZoneInfo


# ============================================================
# CONFIG
# ============================================================

IST = ZoneInfo("Asia/Kolkata")

DATE_CODE = datetime.now(IST).strftime("%Y%m%d")

BASE_URL = (
    f"https://bfilmyapi.pages.dev/daily/data/{DATE_CODE}"
)

OUTPUT_DIR = (
    f"daily/data/{DATE_CODE}"
)

MAX_WORKERS = 30


# ============================================================
# FILES
# ============================================================

FILES = (
    [f"detailed{i}.json" for i in range(1, 10)]
    +
    [f"movie_summary{i}.json" for i in range(1, 10)]
)


# ============================================================
# DOWNLOAD
# ============================================================

def download_file(filename):

    url = f"{BASE_URL}/{filename}"

    output = os.path.join(
        OUTPUT_DIR,
        filename
    )

    try:

        req = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        with urlopen(
            req,
            timeout=30
        ) as response:

            data = response.read()

        os.makedirs(
            OUTPUT_DIR,
            exist_ok=True
        )

        with open(
            output,
            "wb"
        ) as f:

            f.write(data)

        return (
            filename,
            True,
            len(data),
            None
        )

    except HTTPError as e:

        if e.code == 404:

            return (
                filename,
                False,
                0,
                "404"
            )

        return (
            filename,
            False,
            0,
            f"HTTP {e.code}"
        )

    except Exception as e:

        return (
            filename,
            False,
            0,
            str(e)
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print("🚀 DAILY SHARD BACKUP")
    print("=" * 60)

    print(
        f"📅 Date: {DATE_CODE}"
    )

    print(
        f"📦 Files: {len(FILES)}"
    )

    print(
        f"⚡ Workers: {MAX_WORKERS}"
    )

    print("=" * 60)

    success = 0
    not_found = 0
    failed = []

    # ========================================================
    # PARALLEL DOWNLOAD
    # ========================================================

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        futures = [
            executor.submit(
                download_file,
                filename
            )
            for filename in FILES
        ]

        for future in as_completed(futures):

            filename, ok, size, error = (
                future.result()
            )

            if ok:

                success += 1

                print(
                    f"✅ {filename} "
                    f"({size:,} bytes)"
                )

            elif error == "404":

                not_found += 1

                print(
                    f"⚪ {filename} → 404, skipped"
                )

            else:

                failed.append(
                    (
                        filename,
                        error
                    )
                )

                print(
                    f"❌ {filename} → {error}"
                )

    # ========================================================
    # RESULT
    # ========================================================

    print("")
    print("=" * 60)
    print("📊 DOWNLOAD RESULT")
    print("=" * 60)

    print(
        f"✅ Success : {success}"
    )

    print(
        f"⚪ 404     : {not_found}"
    )

    print(
        f"❌ Failed  : {len(failed)}"
    )

    # ========================================================
    # REAL ERRORS → STOP
    # ========================================================

    if failed:

        print("")
        print("❌ REAL DOWNLOAD ERRORS:")

        for filename, error in failed:

            print(
                f"   {filename} → {error}"
            )

        raise SystemExit(
            "🛑 Backup stopped."
        )

    # ========================================================
    # GIT ADD
    # ========================================================

    print("")
    print("📦 Git add...")

    subprocess.run(
        [
            "git",
            "add",
            "--",
            OUTPUT_DIR
        ],
        check=True
    )

    # ========================================================
    # CHECK CHANGES
    # ========================================================

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

        print(
            "ℹ️ No changes to commit."
        )

        return

    # ========================================================
    # COMMIT
    # ========================================================

    print("💾 Committing...")

    subprocess.run(
        [
            "git",
            "commit",
            "-m",
            f"Backup daily shards {DATE_CODE}"
        ],
        check=True
    )

    # ========================================================
    # FORCE PUSH
    # ========================================================

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
            "❌ Could not determine git branch."
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

    print("")
    print("=" * 60)
    print("✅ BACKUP COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
