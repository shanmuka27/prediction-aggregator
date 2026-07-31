import time
import traceback

from store import collect

RUNS = 4
INTERVAL_SECONDS = 900


def main():
    for i in range(RUNS):
        print(f"\n=== collection {i + 1} of {RUNS} ===")
        try:
            collect()
        except Exception:
            traceback.print_exc()
            print("continuing...")

        if i < RUNS - 1:
            time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()