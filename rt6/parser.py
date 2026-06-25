"""
Parsers for all Peugeot Citroën RT6 MapaRadar Updater input file formats.
"""

import csv


def parse_maparadar_csv(path: str):
    """Parse maparadar CSV export (no header, comma-separated, @speed suffix).

    Format: -46.549897,-23.120720,Radar Fixo - 30 kmh@30
    Returns list of (lon, lat, description) tuples (floats + raw description str).
    """
    rows = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(",", 2)
            if len(parts) < 3:
                continue
            try:
                lon = float(parts[0])
                lat = float(parts[1])
            except ValueError:
                continue
            rows.append((lon, lat, parts[2]))
    return rows


def parse_maparadar_asc(path: str):
    """Parse maparadar ASC download (no header, spaces after commas, quoted description).

    Format: -46.549897, -23.120720, "Radar Fixo - 30 km\\h"
    Returns list of (lon, lat, description) tuples.
    """
    rows = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # Split on first two commas only
            parts = line.split(",", 2)
            if len(parts) < 3:
                continue
            try:
                lon = float(parts[0].strip())
                lat = float(parts[1].strip())
            except ValueError:
                continue
            desc = parts[2].strip().strip('"')
            rows.append((lon, lat, desc))
    return rows


def parse_converted(path: str):
    """Parse a car-converted CSV that contains 0xFF padding bytes.

    The car's MiraScript writes each row as:
      CoordX,CoordY,SS,MS,LS,X,Y,subcat,mph,speed,dir,Speed,[0xFF...],City
    where the Road field is filled with 0xFF padding.

    Returns list of dicts with keys: CoordX CoordY SS MS LS X Y
    (subcat/speed/dir are wrong in the car output and are ignored here).
    """
    entries = []
    with open(path, "rb") as f:
        raw = f.read()

    header_skipped = False
    for raw_line in raw.split(b"\n"):
        clean = bytes(b for b in raw_line if b != 0xFF).decode("ascii", errors="ignore").strip()
        if not clean:
            continue
        if not header_skipped:
            header_skipped = True   # first non-empty line is the header row
            continue
        for row in csv.reader([clean]):
            if len(row) < 7:
                continue
            try:
                entries.append({
                    "CoordX": int(row[0]),
                    "CoordY": int(row[1]),
                    "SS":     int(row[2]),
                    "MS":     int(row[3]),
                    "LS":     int(row[4]),
                    "X":      int(row[5]),
                    "Y":      int(row[6]),
                })
            except (ValueError, IndexError):
                pass
    return entries


def parse_base(path: str) -> dict:
    """Parse a clean reference base CSV and return {(CoordX, CoordY): dir} dict."""
    dirs = {}
    with open(path, "r", encoding="ascii", errors="replace") as f:
        for row in csv.DictReader(f):
            key = (int(row["CoordX"]), int(row["CoordY"]))
            dirs[key] = int(row["dir"])
    return dirs
