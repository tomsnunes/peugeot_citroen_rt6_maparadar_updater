"""
WGS84 → RT6 coordinate conversion.

The RT6 navigation system uses a proprietary `ConvertWGSToRelativeUTM` function
that maps (lon, lat) in radians to integer (CoordX, CoordY). The exact projection
is undocumented. This module implements the conversion via RBF (Radial Basis
Function) interpolation fitted to known (lon, lat) → (CoordX, CoordY) pairs
extracted from the car-converted CSV files.

Accuracy: typically < 10 coordinate units (~30 m) for points within Brazil.

Requires: scipy >= 1.7

Usage:
    from rt6.coords import wgs84_to_rt6_raw
    coord_x, coord_y = wgs84_to_rt6_raw(lon, lat)

The SS/MS/LS/X/Y tile values are computed separately in main.py using the
integer arithmetic formula from the RT6_RADARCONVERT.CMD script.
"""

import os
import csv

_INTERPOLATOR_X = None
_INTERPOLATOR_Y = None


def _load_pairs():
    """Load all known (lon, lat) → (CoordX, CoordY) training pairs.

    Deduplicates by (lon, lat): the neighbor-based RBFInterpolator raises
    LinAlgError('Singular matrix') whenever two training points share the exact
    same coordinate (e.g. a radar and a danger zone reported at the same spot),
    since their kernel-matrix rows become identical regardless of differing
    CoordX/CoordY, if both land in the same query's local neighborhood.
    """
    base = os.path.dirname(os.path.dirname(__file__))

    pair_files = [
        (
            os.path.join(base, "databases", "maparadar", "maparadar_radars.csv"),
            os.path.join(base, "databases", "converted", "converted_radars.csv"),
        ),
        (
            os.path.join(base, "databases", "maparadar", "maparadar_dangerz.csv"),
            os.path.join(base, "databases", "converted", "converted_dangerz.csv"),
        ),
    ]

    lons, lats, cxs, cys = [], [], [], []
    seen = set()
    for src_path, conv_path in pair_files:
        if not (os.path.exists(src_path) and os.path.exists(conv_path)):
            continue
        src = []
        with open(src_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.strip().split(",", 2)
                if len(parts) >= 2:
                    try:
                        src.append((float(parts[0]), float(parts[1])))
                    except ValueError:
                        pass

        with open(conv_path, "rb") as f:
            raw = f.read()
        conv = []
        hdr = False
        for raw_line in raw.split(b"\n"):
            clean = bytes(b for b in raw_line if b != 0xFF).decode("ascii", errors="ignore").strip()
            if not clean:
                continue
            if not hdr:
                hdr = True
                continue
            row = clean.split(",")
            if len(row) >= 2:
                try:
                    conv.append((int(row[0]), int(row[1])))
                except (ValueError, IndexError):
                    pass

        n = min(len(src), len(conv))
        for i in range(n):
            key = (src[i][0], src[i][1])
            if key in seen:
                continue
            seen.add(key)
            lons.append(src[i][0])
            lats.append(src[i][1])
            cxs.append(conv[i][0])
            cys.append(conv[i][1])

    return lons, lats, cxs, cys


def _build_interpolators():
    global _INTERPOLATOR_X, _INTERPOLATOR_Y

    if _INTERPOLATOR_X is not None:
        return

    try:
        import numpy as np
        from scipy.interpolate import RBFInterpolator
    except ImportError as e:
        raise ImportError(
            "scipy is required for --no-car coordinate conversion.\n"
            "Install it with: pip install scipy numpy\n"
            f"Original error: {e}"
        )

    print("Building coordinate interpolator from training data ...", flush=True)
    lons, lats, cxs, cys = _load_pairs()
    if len(lons) < 100:
        raise RuntimeError(
            "Not enough training pairs to build the coordinate interpolator.\n"
            "Ensure that databases/converted/converted_radars.csv and "
            "databases/maparadar/maparadar_radars.csv are present."
        )

    points = np.column_stack([lons, lats])
    # neighbors=50 switches from a global dense N×N kernel matrix (crashes at 39K points,
    # ~25 GB RAM) to a local kd-tree RBF using only the 50 nearest training points per
    # query — O(N log N) build, O(K²) per query, a few hundred MB total.
    _INTERPOLATOR_X = RBFInterpolator(points, np.array(cxs), kernel="thin_plate_spline", neighbors=50)
    _INTERPOLATOR_Y = RBFInterpolator(points, np.array(cys), kernel="thin_plate_spline", neighbors=50)
    print(f"  Interpolator built from {len(lons)} training pairs.", flush=True)


def wgs84_to_rt6_raw(lon: float, lat: float) -> tuple:
    """Convert WGS84 (lon, lat) in decimal degrees to RT6 (CoordX, CoordY).

    Returns integer (CoordX, CoordY) matching the RT6 ConvertWGSToRelativeUTM output.
    Requires scipy (install with: pip install scipy numpy).

    This function lazily builds the RBF interpolator on first call (~5-10 seconds
    for 39K training points). Subsequent calls are fast.
    """
    import numpy as np

    _build_interpolators()
    pt = np.array([[lon, lat]])
    cx = int(round(float(_INTERPOLATOR_X(pt)[0])))
    cy = int(round(float(_INTERPOLATOR_Y(pt)[0])))
    return cx, cy


def wgs84_to_rt6_batch(lons, lats) -> tuple:
    """Batch version of wgs84_to_rt6_raw for converting many points at once.

    lons, lats: lists or numpy arrays of floats
    Returns (coord_xs, coord_ys) as lists of ints.
    """
    import numpy as np

    _build_interpolators()
    points = np.column_stack([lons, lats])
    cxs = [int(round(v)) for v in _INTERPOLATOR_X(points)]
    cys = [int(round(v)) for v in _INTERPOLATOR_Y(points)]
    return cxs, cys
