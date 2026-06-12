#!/usr/bin/env python3
"""Aggregate review/council-log.jsonl for trend review.

Counts by agent/verdict and by content area; surfaces disputed and
confirmed findings. ASCII tables only.
"""
import json
import sys
from collections import Counter
from pathlib import Path

LOG = Path(__file__).resolve().parents[2] / "review" / "council-log.jsonl"


def load():
    if not LOG.exists():
        print(f"No log at {LOG}")
        sys.exit(0)
    records = []
    for i, line in enumerate(LOG.read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as e:
            print(f"WARNING: bad JSONL at line {i}: {e}")
    return records


def table(title, counter):
    print(f"\n{title}")
    width = max([len(str(k)) for k in counter] + [4])
    print(f"+-{'-' * width}-+-------+")
    for key, n in counter.most_common():
        print(f"| {str(key):<{width}} | {n:>5} |")
    print(f"+-{'-' * width}-+-------+")


def main():
    records = load()
    if not records:
        print("Log is empty.")
        return
    print(f"{len(records)} records, {len({r['run_id'] for r in records})} runs, "
          f"{len({r['content_file'] for r in records})} content files")

    table("By agent x verdict", Counter(f"{r['agent']}/{r['verdict']}" for r in records))
    table("By content area", Counter(r["content_file"].split("/")[1]
                                     if "/" in r["content_file"] else r["content_file"]
                                     for r in records))
    table("By tier", Counter(r["tier"] for r in records))

    flagged = [r for r in records
               if r["escalation_outcome"] != "none"
               or r["verdict"] in ("mismatch", "fail")]
    if "--disputes" in sys.argv and flagged:
        print("\nFlagged findings (mismatch/fail/escalated):")
        for r in flagged:
            sev = (r.get("score") or {}).get("severity", "-")
            print(f"- [{r['escalation_outcome']}/{sev}] {r['content_file']} "
                  f"{r['claim_id']} ({r['agent']}): {r.get('detail', '')[:140]}")
    elif flagged:
        print(f"\n{len(flagged)} flagged finding(s) — rerun with --disputes for detail")


if __name__ == "__main__":
    main()
