from __future__ import annotations

import argparse

from market_match.utils.editions import create_share_bundle_for_edition


def main() -> int:
    parser = argparse.ArgumentParser(description="Create share bundle for one Market Match edition")
    parser.add_argument("--edition-number", required=True, type=int, help="Edition number")
    parser.add_argument("--edition-date", required=True, help="Edition date (YYYY-MM-DD)")
    args = parser.parse_args()

    message = create_share_bundle_for_edition(
        edition_number=args.edition_number,
        edition_date=args.edition_date,
    )
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
