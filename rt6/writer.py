"""
Write RT6-format CSV output files.
"""

import csv
import os

FIELDNAMES = [
    "CoordX", "CoordY", "SS", "MS", "LS", "X", "Y",
    "subcat", "mph", "speed", "dir", "Speed", "Road", "City",
]


def write_rt6_csv(path: str, rows: list) -> None:
    """Write rows to an RT6-format CSV with CRLF line endings and ASCII encoding."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="ascii") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)
