"""
Run the one-shot internal comparison baseline across all benchmark cases.

Usage:
    python -m scripts.run_baseline
"""

from evaluation.internal.baseline import run_all


def main():
    run_all()


if __name__ == "__main__":
    main()
