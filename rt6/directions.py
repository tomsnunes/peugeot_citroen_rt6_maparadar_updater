"""
Direction lookup for RT6 POI entries.

Priority order:
  1. Exact coordinate match in base reference file
  2. Nearest base coordinate within DIR_MATCH_THRESHOLD units (~150 m)
  3. OSM road bearing for new paired directional radars (optional, requires internet)
  4. Default 360 (omnidirectional)
"""

import json
import math
import time
import urllib.parse
import urllib.request

DIR_MATCH_THRESHOLD = 50   # coordinate units; 1 unit ~3 m → 50 units ~150 m
PAIR_THRESHOLD      = 0.008  # degrees (~890 m) for paired-radar detection
TILE_SIZE           = 0.5
TILE_PAD            = 0.05
OVERPASS_TIMEOUT    = 60
OVERPASS_URL        = "https://overpass-api.de/api/interpreter"


# ---------------------------------------------------------------------------
# Base-file lookup
# ---------------------------------------------------------------------------

def lookup_dir(cx: int, cy: int, base_dirs: dict, base_coords: list) -> tuple:
    """Return (direction, source_label) from base file.

    source_label is one of: 'exact', 'near', 'default'.
    """
    key = (cx, cy)
    if key in base_dirs:
        return base_dirs[key], "exact"

    nearest = min(base_coords, key=lambda b: abs(b[0] - cx) + abs(b[1] - cy))
    dist = abs(nearest[0] - cx) + abs(nearest[1] - cy)
    if dist <= DIR_MATCH_THRESHOLD:
        return base_dirs[nearest], "near"

    return 360, "default"


# ---------------------------------------------------------------------------
# OSM / Overpass helpers
# ---------------------------------------------------------------------------

def _bearing(lat1, lon1, lat2, lon2) -> float:
    """WGS84 compass bearing in degrees (−180..180) from point 1 to point 2."""
    lat1r = math.radians(lat1)
    lat2r = math.radians(lat2)
    dlon  = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(lat2r)
    y = math.cos(lat1r) * math.sin(lat2r) - math.sin(lat1r) * math.cos(lat2r) * math.cos(dlon)
    return math.degrees(math.atan2(x, y))


def _pt_seg_dist_sq(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    len_sq = dx * dx + dy * dy
    if len_sq == 0.0:
        return (px - ax) ** 2 + (py - ay) ** 2
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / len_sq))
    return (px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2


def _nearest_road_bearing(lat, lon, ways):
    best_dist_sq, best_bear = float("inf"), None
    for nodes in ways:
        for i in range(len(nodes) - 1):
            d2 = _pt_seg_dist_sq(lat, lon, nodes[i][0], nodes[i][1],
                                 nodes[i+1][0], nodes[i+1][1])
            if d2 < best_dist_sq:
                best_dist_sq = d2
                best_bear    = _bearing(nodes[i][0], nodes[i][1],
                                        nodes[i+1][0], nodes[i+1][1])
    return best_bear


def _query_overpass_tile(tile_lat, tile_lon):
    s, n = tile_lat - TILE_PAD, tile_lat + TILE_SIZE + TILE_PAD
    w, e = tile_lon - TILE_PAD, tile_lon + TILE_SIZE + TILE_PAD
    query = (
        f"[out:json][timeout:{OVERPASS_TIMEOUT}];"
        f"way[\"highway\"]({s},{w},{n},{e});"
        f"out geom;"
    )
    try:
        body = urllib.parse.urlencode({"data": query}).encode("utf-8")
        req  = urllib.request.Request(
            OVERPASS_URL, data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "PeugeotCitroenRT6MapaRadarUpdater/2.0",
            },
        )
        with urllib.request.urlopen(req, timeout=OVERPASS_TIMEOUT + 10) as resp:
            payload = json.loads(resp.read())
    except Exception as exc:
        print(f"  [OSM] tile ({tile_lat:.2f},{tile_lon:.2f}) error: {exc}", flush=True)
        return []
    return [
        [(n["lat"], n["lon"]) for n in el["geometry"]]
        for el in payload.get("elements", [])
        if el.get("type") == "way" and len(el.get("geometry", [])) >= 2
    ]


def _detect_pairs(entries):
    """Greedy nearest-pair detection among directional unresolved radars.

    entries: list of (row_index, lat, lon, type_key, speed)
    Returns list of (entry_a, entry_b) tuples.
    """
    from collections import defaultdict
    groups = defaultdict(list)
    for e in entries:
        groups[(e[3], e[4])].append(e)

    paired, pairs = set(), []
    for group in groups.values():
        for ai, a in enumerate(group):
            if a[0] in paired:
                continue
            for b in group[ai + 1:]:
                if b[0] in paired:
                    continue
                if abs(a[1] - b[1]) <= PAIR_THRESHOLD and abs(a[2] - b[2]) <= PAIR_THRESHOLD:
                    pairs.append((a, b))
                    paired.add(a[0])
                    paired.add(b[0])
                    break
    return pairs


def _to_dir(b_deg) -> int:
    v = round(b_deg)
    return -180 if v == 180 else v


def compute_offline_directions(unresolved_entries: list, segs_arr, csr) -> dict:
    """Same as compute_osm_directions but uses a local highway index instead of Overpass API.

    segs_arr, csr: loaded via rt6.osm_index.load().
    """
    from rt6 import osm_index

    directional = [e for e in unresolved_entries if e[3] in ("fixo", "semaforo", "camera", "policia")]
    pairs = _detect_pairs(directional)
    print(f"  [OSM-offline] {len(pairs)} pairs found among {len(directional)} directional unresolved")

    if not pairs:
        return {}

    result = {}
    for a, b in pairs:
        a_idx, a_lat, a_lon = a[0], a[1], a[2]
        b_idx, b_lat, b_lon = b[0], b[1], b[2]

        theta = osm_index.nearest_bearing(a_lat, a_lon, segs_arr, csr)
        if theta is None:
            continue

        theta_rad = math.radians(theta)
        proj_a = a_lat * math.cos(theta_rad) + a_lon * math.sin(theta_rad)
        proj_b = b_lat * math.cos(theta_rad) + b_lon * math.sin(theta_rad)
        opp = theta + 180.0 if theta < 0.0 else theta - 180.0

        if proj_a <= proj_b:
            result[a_idx] = _to_dir(theta)
            result[b_idx] = _to_dir(opp)
        else:
            result[a_idx] = _to_dir(opp)
            result[b_idx] = _to_dir(theta)

    print(f"  [OSM-offline] assigned directions for {len(result)} entries ({len(result)//2} pairs)")
    return result


def compute_osm_directions(unresolved_entries: list) -> dict:
    """Compute OSM road bearing for unresolved paired directional entries.

    unresolved_entries: list of (row_index, lat, lon, type_key, speed)
    Returns dict {row_index: direction_int}.
    """
    directional = [e for e in unresolved_entries if e[3] in ("fixo", "semaforo", "camera", "policia")]
    pairs = _detect_pairs(directional)
    print(f"  [OSM] {len(pairs)} pairs found among {len(directional)} directional unresolved")

    if not pairs:
        return {}

    paired_indices = {e[0] for pair in pairs for e in pair}
    tile_to_entries = {}
    for entry in directional:
        if entry[0] not in paired_indices:
            continue
        tile = (math.floor(entry[1] / TILE_SIZE) * TILE_SIZE,
                math.floor(entry[2] / TILE_SIZE) * TILE_SIZE)
        tile_to_entries.setdefault(tile, []).append(entry)

    tiles = list(tile_to_entries.keys())
    print(f"  [OSM] querying {len(tiles)} tiles ...", flush=True)
    tile_ways = {}
    for idx, tile in enumerate(tiles, 1):
        print(f"  [OSM] tile {idx}/{len(tiles)} ({tile[0]:.2f},{tile[1]:.2f})", flush=True)
        tile_ways[tile] = _query_overpass_tile(tile[0], tile[1])
        if idx < len(tiles):
            time.sleep(1.0)

    result = {}
    for a, b in pairs:
        a_idx, a_lat, a_lon = a[0], a[1], a[2]
        b_idx, b_lat, b_lon = b[0], b[1], b[2]
        a_tile = (math.floor(a_lat / TILE_SIZE) * TILE_SIZE,
                  math.floor(a_lon / TILE_SIZE) * TILE_SIZE)
        ways = tile_ways.get(a_tile, [])
        if not ways:
            continue
        theta = _nearest_road_bearing(a_lat, a_lon, ways)
        if theta is None:
            continue

        theta_rad = math.radians(theta)
        proj_a = a_lat * math.cos(theta_rad) + a_lon * math.sin(theta_rad)
        proj_b = b_lat * math.cos(theta_rad) + b_lon * math.sin(theta_rad)
        opp = theta + 180.0 if theta < 0.0 else theta - 180.0

        if proj_a <= proj_b:
            result[a_idx] = _to_dir(theta)
            result[b_idx] = _to_dir(opp)
        else:
            result[a_idx] = _to_dir(opp)
            result[b_idx] = _to_dir(theta)

    print(f"  [OSM] assigned directions for {len(result)} entries ({len(result)//2} pairs)")
    return result
