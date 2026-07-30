import time
import traceback
from datetime import datetime, timezone

from store import collect

INTERVAL_SECONDS = 900  # 15 minutes


def run_forever():
    print(f"Collector started. Polling every {INTERVAL_SECONDS // 60} min.")
    print("Ctrl+C to stop.\n")

    run_count = 0

    while True:
        try:
            collect()
            run_count += 1
            print(f"--- run {run_count} complete ---\n")
        except KeyboardInterrupt:
            print(f"\nStopped after {run_count} runs.")
            break
        except Exception:
            # Network blips and bad API responses shouldn't kill an overnight run.
            print(f"\n!! run failed at {datetime.now(timezone.utc).isoformat()}")
            traceback.print_exc()
            print("continuing...\n")

        try:
            time.sleep(INTERVAL_SECONDS)
        except KeyboardInterrupt:
            print(f"\nStopped after {run_count} runs.")
            break


if __name__ == "__main__":
    run_forever()