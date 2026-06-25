"""
Type classification and RT6 road-label generation for radars and danger zones.
"""

# ---------------------------------------------------------------------------
# RADAR
# ---------------------------------------------------------------------------

RADAR_SUBCATS = {
    "fixo":     1,
    "semaforo": 2,
    "camera":   3,
    "movel":    6,
}


def classify_radar(description: str):
    """Return (type_key, speed) from a maparadar radar description.

    Handles both CSV format ('Radar Fixo - 50 kmh@50') and
    ASC format ('Radar Fixo - 50 km\\h').
    """
    speed = _parse_speed(description)
    d = description.lower()
    if "semaforo com camera" in d or "semaforo com camara" in d:
        return "camera", 0
    if "semaforo com radar" in d:
        return "semaforo", speed
    if "movel" in d or "m\xf3vel" in d:
        return "movel", speed
    return "fixo", speed


def road_label_radar(type_key: str, speed: int) -> str:
    if type_key == "fixo":
        return f"Radar Fixo {speed} km\\h"
    if type_key == "movel":
        return f"Radar Movel {speed} km\\h"
    if type_key == "semaforo":
        return f"Sinal + Radar {speed} km\\h"
    return "Sinal Vermelho"  # camera


# ---------------------------------------------------------------------------
# DANGERZ
# ---------------------------------------------------------------------------

DANGERZ_SUBCATS = {
    "policia": 1,
    "pedagio": 3,
    "lombada": 4,
}


_DANGERZ_DEFAULT_SPEED = {
    "lombada": 20,   # standard RT6 crossing speed for speed bumps
    "pedagio": 40,   # standard RT6 approach speed for toll booths
    "policia":  0,   # varies by road; no reliable single default
}


def classify_dangerz(description: str):
    """Return (type_key, speed) from a maparadar danger-zone description.

    maparadar exports all danger zones with speed=0 since it does not store
    a specific speed limit for these POI types. We apply RT6-standard defaults
    (from base_dangerz.csv) so the nav unit shows a meaningful value.
    """
    speed = _parse_speed(description)
    d = description.lower()
    if "policia" in d:
        type_key = "policia"
    elif "pedagio" in d or "ped\xe1gio" in d:
        type_key = "pedagio"
    elif "lombada" in d:
        type_key = "lombada"
    else:
        type_key = "lombada"
    if speed == 0:
        speed = _DANGERZ_DEFAULT_SPEED[type_key]
    return type_key, speed


def road_label_dangerz(type_key: str, speed: int) -> str:
    if type_key == "policia":
        return f"Posto da PRF {speed} km\\h"
    if type_key == "pedagio":
        return f"Pedagio {speed} km\\h"
    return f"Lombada {speed} km\\h"


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------

def _parse_speed(description: str) -> int:
    """Extract the integer speed from either '@N' suffix or '- N km' text."""
    if "@" in description:
        try:
            return int(description.rsplit("@", 1)[-1].strip())
        except ValueError:
            pass
    # Fallback: find last run of digits before 'km'
    import re
    m = re.search(r"(\d+)\s*km", description, re.IGNORECASE)
    return int(m.group(1)) if m else 0
