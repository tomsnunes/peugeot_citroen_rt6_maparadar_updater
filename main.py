"""
Peugeot Citroën RT6 MapaRadar Updater — main entry point.

Converts maparadar.com radar and danger-zone data into RT6-compatible CSV files
(RADAR.csv and DANGERZ.csv) ready for import into RadarViewer v2.0.

Usage:
    python main.py                  # uses car-converted coordinates (fast)
    python main.py --no-car         # Python coordinate conversion (no car needed)
    python main.py --compute-dirs   # + OSM direction lookup for new entries
    python main.py --radar-only     # skip DANGERZ pipeline
    python main.py --dangerz-only   # skip RADAR pipeline
"""

import argparse
import os
import sys

from rt6 import classifier, directions, parser, writer
from rt6.writer import FIELDNAMES  # noqa: F401 (used implicitly by writer)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR  = os.path.dirname(__file__)
DB_DIR    = os.path.join(BASE_DIR, "databases")
OUT_DIR   = os.path.join(BASE_DIR, "output")
OSM_DIR   = os.path.join(DB_DIR,   "openstreetmap")

MAPARADAR_RADARS   = os.path.join(DB_DIR, "maparadar",  "maparadar_radars.csv")
MAPARADAR_DANGERZ  = os.path.join(DB_DIR, "maparadar",  "maparadar_dangerz.csv")
CONVERTED_RADARS   = os.path.join(DB_DIR, "converted",  "converted_radars.csv")
CONVERTED_DANGERZ  = os.path.join(DB_DIR, "converted",  "converted_dangerz.csv")
BASE_RADARS        = os.path.join(DB_DIR, "base",        "base_radar.csv")
BASE_DANGERZ       = os.path.join(DB_DIR, "base",        "base_dangerz.csv")
OUTPUT_RADARS      = os.path.join(OUT_DIR, "RADAR.csv")
OUTPUT_DANGERZ     = os.path.join(OUT_DIR, "DANGERZ.csv")


# ---------------------------------------------------------------------------
# Coordinate tile helpers (from RT6_RADARCONVERT.CMD — exact integer formula)
# ---------------------------------------------------------------------------

def _coords_to_tiles(coord_x: int, coord_y: int):
    """Compute SS, MS, LS, X, Y from CoordX/CoordY using RT6 tile formula."""
    x, y = coord_x, coord_y
    X  = x % 16000
    Y  = y % 16000
    x //= 1000
    y //= 1000
    SS = (x % 16) + 16 * (y % 16)
    x //= 16
    y //= 16
    MS = (x % 16) + 16 * (y % 16)
    x //= 16
    y //= 16
    LS = x + 28 * y   # South America / Europe formula
    return SS, MS, LS, X, Y


# ---------------------------------------------------------------------------
# Single pipeline (shared by RADAR and DANGERZ)
# ---------------------------------------------------------------------------

def run_pipeline(
    label: str,
    maparadar_path: str,
    converted_path: str,
    base_path: str,
    output_path: str,
    classify_fn,
    road_label_fn,
    subcat_map: dict,
    use_car_coords: bool,
    compute_dirs: bool,
    osm_segs_arr=None,
    osm_csr=None,
):
    print(f"\n{'='*60}")
    print(f"  Pipeline: {label}")
    print(f"{'='*60}")

    # 1. Parse maparadar source
    print(f"Reading maparadar source: {maparadar_path}")
    source = parser.parse_maparadar_csv(maparadar_path)
    print(f"  {len(source)} entries")

    # 2. Get RT6 coordinates
    if use_car_coords and os.path.exists(converted_path):
        print(f"Reading converted coords: {converted_path}")
        converted = parser.parse_converted(converted_path)
        print(f"  {len(converted)} coordinate entries parsed")
        if len(converted) != len(source):
            print(f"  WARNING: count mismatch (source={len(source)}, converted={len(converted)})")
        coord_source = "converted"
    else:
        if use_car_coords:
            print(f"  Converted file not found — falling back to Python coordinate conversion")
        else:
            print("  Using Python coordinate conversion (--no-car)")
        from rt6 import coords as _coords
        converted = None
        coord_source = "python"

    # 3. Load base directions
    print(f"Reading base directions: {base_path}")
    base_dirs   = parser.parse_base(base_path)
    base_coords = list(base_dirs.keys())
    print(f"  {len(base_dirs)} reference entries")

    # 4. Collect unresolved entries for optional OSM lookup
    count = min(len(source), len(converted) if converted else len(source))

    # Pre-compute Python coords in batch (one kd-tree pass) to avoid per-point overhead
    # and redundant calls across the scan and build loops below.
    if not converted:
        _all_lons = [source[i][0] for i in range(count)]
        _all_lats = [source[i][1] for i in range(count)]
        _batch_cxs, _batch_cys = _coords.wgs84_to_rt6_batch(_all_lons, _all_lats)
    else:
        _batch_cxs = _batch_cys = None

    unresolved = []
    if compute_dirs:
        print("Scanning for unresolved directions ...")
        for i in range(count):
            lon, lat, desc = source[i]
            if converted:
                cx, cy = converted[i]["CoordX"], converted[i]["CoordY"]
            else:
                cx, cy = _batch_cxs[i], _batch_cys[i]

            _, src = directions.lookup_dir(cx, cy, base_dirs, base_coords)
            if src == "default":
                type_key, speed = classify_fn(desc)
                unresolved.append((i, lat, lon, type_key, speed))
        print(f"  {len(unresolved)} unresolved entries")
        if osm_segs_arr is not None and osm_csr is not None:
            osm_dirs = directions.compute_offline_directions(unresolved, osm_segs_arr, osm_csr)
        else:
            osm_dirs = directions.compute_osm_directions(unresolved)
    else:
        osm_dirs = {}

    # 5. Build output rows
    rows = []
    stats = {"exact": 0, "near": 0, "osm": 0, "default": 0}

    for i in range(count):
        lon, lat, desc = source[i]
        type_key, speed = classify_fn(desc)

        if converted:
            c = converted[i]
            cx, cy = c["CoordX"], c["CoordY"]
            SS, MS, LS, X, Y = c["SS"], c["MS"], c["LS"], c["X"], c["Y"]
        else:
            cx, cy = _batch_cxs[i], _batch_cys[i]
            SS, MS, LS, X, Y = _coords_to_tiles(cx, cy)

        direction, src = directions.lookup_dir(cx, cy, base_dirs, base_coords)
        if src == "default" and i in osm_dirs:
            direction = osm_dirs[i]
            src = "osm"
        stats[src] += 1

        rows.append({
            "CoordX": cx,
            "CoordY": cy,
            "SS":     SS,
            "MS":     MS,
            "LS":     LS,
            "X":      X,
            "Y":      Y,
            "subcat": subcat_map[type_key],
            "mph":    0,
            "speed":  speed,
            "dir":    direction,
            "Speed":  f"{speed} km/h",
            "Road":   road_label_fn(type_key, speed),
            "City":   "MapaRadar",
        })

    # 6. Write output
    writer.write_rt6_csv(output_path, rows)
    print(f"Written: {output_path}")
    print(f"  {len(rows)} rows  |  coords from: {coord_source}")
    print(
        f"  dir: {stats['exact']} exact, {stats['near']} near (<={directions.DIR_MATCH_THRESHOLD} units), "
        f"{stats['osm']} OSM, {stats['default']} default(360)"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Convert maparadar.com data to RT6-compatible RADAR.csv and DANGERZ.csv",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--no-car",       action="store_true",
                    help="Use Python coordinate conversion instead of car-converted files")
    ap.add_argument("--compute-dirs", action="store_true",
                    help="Query OpenStreetMap Overpass API to assign directions for new paired entries")
    ap.add_argument("--radar-only",        action="store_true", help="Only process RADAR pipeline")
    ap.add_argument("--dangerz-only",      action="store_true", help="Only process DANGERZ pipeline")
    ap.add_argument("--build-osm-index",   action="store_true",
                    help="Build offline highway index from databases/openstreetmap/*.osm.pbf and exit")
    args = ap.parse_args()

    use_car = not args.no_car

    # --build-osm-index: one-time build, then exit
    if args.build_osm_index:
        import glob
        from rt6 import osm_index
        pbf_files = glob.glob(os.path.join(OSM_DIR, "*.osm.pbf"))
        if not pbf_files:
            print(f"ERROR: No .osm.pbf file found in {OSM_DIR}")
            sys.exit(1)
        pbf_path = pbf_files[0]
        print(f"Building OSM highway index from: {os.path.basename(pbf_path)}")
        segs_arr, csr = osm_index.build(pbf_path)
        osm_index.save(segs_arr, csr, OSM_DIR)
        print("Done. Re-run without --build-osm-index to use the index.")
        sys.exit(0)

    if args.no_car:
        try:
            from rt6 import coords as _c
            _ = _c.wgs84_to_rt6_raw   # verify the function exists
        except (ImportError, AttributeError):
            print("ERROR: --no-car requires rt6/coords.py with wgs84_to_rt6_raw().")
            print("       Run without --no-car to use car-converted coordinate files.")
            sys.exit(1)

    # Load offline OSM index once (shared by both pipelines)
    osm_segs_arr = osm_csr = None
    if args.compute_dirs:
        from rt6 import osm_index
        if osm_index.index_exists(OSM_DIR):
            print("Loading offline OSM highway index ...", flush=True)
            osm_segs_arr, osm_csr = osm_index.load(OSM_DIR)
            print(f"  {len(osm_segs_arr):,} highway segments ready (no API calls needed)", flush=True)
        else:
            print("No offline index found — will use Overpass API for direction lookup.")
            print("  Run with --build-osm-index once to build the local index.")

    if not args.dangerz_only:
        run_pipeline(
            label          = "RADAR",
            maparadar_path = MAPARADAR_RADARS,
            converted_path = CONVERTED_RADARS,
            base_path      = BASE_RADARS,
            output_path    = OUTPUT_RADARS,
            classify_fn    = classifier.classify_radar,
            road_label_fn  = classifier.road_label_radar,
            subcat_map     = classifier.RADAR_SUBCATS,
            use_car_coords = use_car,
            compute_dirs   = args.compute_dirs,
            osm_segs_arr       = osm_segs_arr,
            osm_csr       = osm_csr,
        )

    if not args.radar_only:
        run_pipeline(
            label          = "DANGERZ",
            maparadar_path = MAPARADAR_DANGERZ,
            converted_path = CONVERTED_DANGERZ,
            base_path      = BASE_DANGERZ,
            output_path    = OUTPUT_DANGERZ,
            classify_fn    = classifier.classify_dangerz,
            road_label_fn  = classifier.road_label_dangerz,
            subcat_map     = classifier.DANGERZ_SUBCATS,
            use_car_coords = use_car,
            compute_dirs   = args.compute_dirs,
            osm_segs_arr       = osm_segs_arr,
            osm_csr       = osm_csr,
        )


if __name__ == "__main__":
    main()
