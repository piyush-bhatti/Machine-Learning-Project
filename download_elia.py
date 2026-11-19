"""
Download Elia dataset ods032 (photovoltaic power production estimation and
forecast on the Belgian grid) and save it as a parquet file.

Usage:  python download_elia.py                          (full history, about 150 MB)
        python download_elia.py --start 2023-01-01       (from a given date)
        python download_elia.py --start 2026-01-01 --out ods032_2026.parquet

Needs: requests
Source: Elia Open Data, https://opendata.elia.be/explore/dataset/ods032/information/
Coverage: quarter-hourly, 14 areas, up to 25 October 2026. Later data is in dataset ods209,
which has a different structure and is not used in this project.
"""
import argparse
from pathlib import Path

import requests

URL = "https://opendata.elia.be/api/explore/v2.1/catalog/datasets/ods032/exports/parquet"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", default=None, help="first day to include, YYYY-MM-DD (UTC)")
    p.add_argument("--end", default=None, help="first day to exclude, YYYY-MM-DD (UTC)")
    p.add_argument("--out", default="ods032.parquet")
    args = p.parse_args()

    conditions = []
    if args.start:
        conditions.append(f"datetime >= date'{args.start}'")
    if args.end:
        conditions.append(f"datetime < date'{args.end}'")
    params = {"timezone": "UTC"}
    if conditions:
        params["where"] = " and ".join(conditions)

    out = Path(args.out)
    tmp = out.with_suffix(out.suffix + ".part")
    done = 0
    with requests.get(URL, params=params, stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                done += len(chunk)
                print(f"\rdownloaded {done / 1e6:,.0f} MB", end="", flush=True)
    tmp.replace(out)        # only becomes the final file once the download is complete
    print(f"\nwrote {out} ({done / 1e6:,.1f} MB)")


if __name__ == "__main__":
    main()
