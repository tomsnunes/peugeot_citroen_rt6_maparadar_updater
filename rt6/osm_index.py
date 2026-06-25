"""
Offline OSM highway index for direction lookup.

Build once from a local PBF file; query at runtime with pure numpy.

Usage:
    python main.py --build-osm-index   # one-time build (requires osmium)
    python main.py --compute-dirs      # auto-uses index if present, no API calls

Storage: a single compressed npz containing:
    segs      float32 (N, 5)  [lat1, lon1, lat2, lon2, bearing_deg]
    keys64    int64   (C,)    sorted encoded (cell_i, cell_j) keys
    offsets   int32   (C+1,)  CSR start/end into seg_list for each cell
    seg_list  int32   (N,)    segment indices sorted by cell (midpoint assignment)
"""

import math
import os

import numpy as np

# Roads likely to carry speed cameras; excludes residential, service, tracks, paths
INCLUDED_HIGHWAY = {
    "motorway",      "motorway_link",
    "trunk",         "trunk_link",
    "primary",       "primary_link",
    "secondary",     "secondary_link",
    "tertiary",      "tertiary_link",
    "unclassified",
}

GRID_STEP     = 0.01   # degrees per cell (~1.1 km at equator)
SEARCH_RADIUS = 3      # cells in each direction (~3.3 km)

# Encoding offsets: keep (cell_i + SHIFT_I) and (cell_j + SHIFT_J) non-negative
# Brazil: lat -33..5 -> cell_i -3300..500; lon -73..-34 -> cell_j -7300..-3400
_SHIFT_I = 4096   # 2^12, comfortably covers [-3300, 500]
_SHIFT_J = 8192   # 2^13, comfortably covers [-7300, -3400]

_INDEX_FILE = "highway_index.npz"


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build(pbf_path: str):
    """Extract highway segments from a PBF file and return (segs_arr, csr).

    segs_arr  float32 (N, 5): [lat1, lon1, lat2, lon2, bearing_deg]
    csr       dict with keys 'keys64', 'offsets', 'seg_list'

    Requires the 'osmium' package (pip install osmium).
    Reads the full PBF with node location cache (~3 GB RAM for a country file).
    """
    try:
        import osmium
    except ImportError:
        raise ImportError(
            "osmium is required to build the highway index.\n"
            "Install it with: pip install osmium"
        )

    class _Handler(osmium.SimpleHandler):
        def __init__(self):
            super().__init__()
            self.segs = []

        def way(self, w):
            if "highway" not in w.tags or w.tags["highway"] not in INCLUDED_HIGHWAY:
                return
            run = []
            for n in w.nodes:
                loc = n.location
                if loc.valid():
                    run.append((loc.lat, loc.lon))
                else:
                    self._flush(run)
                    run = []
            self._flush(run)

        def _flush(self, coords):
            for i in range(len(coords) - 1):
                lat1, lon1 = coords[i]
                lat2, lon2 = coords[i + 1]
                self.segs.append((lat1, lon1, lat2, lon2,
                                  _bearing_deg(lat1, lon1, lat2, lon2)))

    print(f"Reading PBF: {os.path.basename(pbf_path)}", flush=True)
    print("  Filtering to motorway/trunk/primary/secondary/tertiary/unclassified ...", flush=True)
    print("  Node location cache needs ~3 GB RAM; expect 1–3 min.", flush=True)
    handler = _Handler()
    handler.apply_file(pbf_path, locations=True)

    print(f"  {len(handler.segs):,} highway segments extracted", flush=True)
    segs_arr = np.array(handler.segs, dtype=np.float32)

    print("Building CSR spatial grid ...", flush=True)
    csr = _build_csr(segs_arr)
    print(f"  {len(csr['keys64']):,} populated grid cells (step={GRID_STEP}°)", flush=True)
    return segs_arr, csr


def _bearing_deg(lat1, lon1, lat2, lon2) -> float:
    lat1r, lat2r = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(lat2r)
    y = (math.cos(lat1r) * math.sin(lat2r)
         - math.sin(lat1r) * math.cos(lat2r) * math.cos(dlon))
    return math.degrees(math.atan2(x, y))


def _build_csr(segs_arr) -> dict:
    """Assign each segment to the grid cell of its midpoint (no duplicates).

    Returns CSR arrays: keys64 (sorted cell keys), offsets, seg_list.
    """
    mid_i = np.floor((segs_arr[:, 0] + segs_arr[:, 2]) / (2.0 * GRID_STEP)).astype(np.int64)
    mid_j = np.floor((segs_arr[:, 1] + segs_arr[:, 3]) / (2.0 * GRID_STEP)).astype(np.int64)
    keys64 = (mid_i + _SHIFT_I) * 65536 + (mid_j + _SHIFT_J)

    order      = np.argsort(keys64, kind="stable")
    sk         = keys64[order]
    unique_k, first_occ, counts = np.unique(sk, return_index=True, return_counts=True)

    offsets  = np.concatenate([[0], np.cumsum(counts)]).astype(np.int32)
    seg_list = order.astype(np.int32)

    return {"keys64": unique_k, "offsets": offsets, "seg_list": seg_list}


# ---------------------------------------------------------------------------
# Persist
# ---------------------------------------------------------------------------

def save(segs_arr, csr: dict, index_dir: str):
    os.makedirs(index_dir, exist_ok=True)
    path = os.path.join(index_dir, _INDEX_FILE)
    np.savez_compressed(path,
                        segs=segs_arr,
                        keys64=csr["keys64"],
                        offsets=csr["offsets"],
                        seg_list=csr["seg_list"])
    size_mb = os.path.getsize(path) / 1e6
    print(f"  Saved {_INDEX_FILE} ({size_mb:.0f} MB, compressed)", flush=True)


def load(index_dir: str):
    """Load pre-built index.  Returns (segs_arr, csr) or (None, None) if missing."""
    path = os.path.join(index_dir, _INDEX_FILE)
    if not os.path.exists(path):
        return None, None
    data = np.load(path)
    segs_arr = data["segs"]
    csr = {
        "keys64":   data["keys64"],
        "offsets":  data["offsets"],
        "seg_list": data["seg_list"],
    }
    return segs_arr, csr


def index_exists(index_dir: str) -> bool:
    return os.path.exists(os.path.join(index_dir, _INDEX_FILE))


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

def nearest_bearing(lat: float, lon: float, segs_arr, csr) -> float | None:
    """Return bearing (degrees) of the nearest highway segment to (lat, lon).

    Uses the pre-sorted keys64 array for O(log C) cell lookup.
    Midpoint assignment guarantees each segment appears in exactly one cell,
    so no deduplication is needed across the search neighbourhood.
    """
    keys64   = csr["keys64"]
    offsets  = csr["offsets"]
    seg_list = csr["seg_list"]

    i0 = int(math.floor(lat / GRID_STEP))
    j0 = int(math.floor(lon / GRID_STEP))

    chunks = []
    for di in range(-SEARCH_RADIUS, SEARCH_RADIUS + 1):
        for dj in range(-SEARCH_RADIUS, SEARCH_RADIUS + 1):
            key = (i0 + di + _SHIFT_I) * 65536 + (j0 + dj + _SHIFT_J)
            pos = int(np.searchsorted(keys64, key))
            if pos < len(keys64) and int(keys64[pos]) == key:
                start = int(offsets[pos])
                end   = int(offsets[pos + 1])
                chunks.append(seg_list[start:end])

    if not chunks:
        return None

    idxs = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
    s    = segs_arr[idxs]

    # Vectorised point-to-segment distance in lat/lon degrees
    dlat   = s[:, 2] - s[:, 0]
    dlon   = s[:, 3] - s[:, 1]
    len_sq = dlat * dlat + dlon * dlon
    len_sq = np.where(len_sq < 1e-20, 1e-20, len_sq)
    t      = np.clip(((lat - s[:, 0]) * dlat + (lon - s[:, 1]) * dlon) / len_sq, 0.0, 1.0)
    dist_sq = (lat - (s[:, 0] + t * dlat)) ** 2 + (lon - (s[:, 1] + t * dlon)) ** 2

    return float(s[int(np.argmin(dist_sq)), 4])
