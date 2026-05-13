import argparse


def main():
    parser = argparse.ArgumentParser(description="AI News Bot")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--dry-run", action="store_true", help="Run without publishing")
    args = parser.parse_args()
    # TODO: wire up scheduler/pipeline
    print(f"Args: once={args.once}, dry_run={args.dry_run}")


if __name__ == "__main__":
    main()
