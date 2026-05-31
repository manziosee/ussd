"""
Static services directory — health clinics, agri offices, and schools
per district. Zero AI cost; data is updated manually by an admin.

Coverage: Kigali · Musanze · Huye · Rubavu · Kayonza
Categories: farming (agri extension offices) · health · education

All telephone numbers below are FICTIONAL placeholders (the +250 000 0XX
range is unassigned in Rwanda's national numbering plan).
Replace them with real numbers before going live.

To add a district or service, extend SERVICES below and add the key to
DISTRICTS and DISTRICT_LABELS.
"""
from __future__ import annotations

# ── District lookup ────────────────────────────────────────────────────────────

DISTRICTS: dict[str, str] = {
    "1": "kigali",
    "2": "musanze",
    "3": "huye",
    "4": "rubavu",
    "5": "kayonza",
}

DISTRICT_LABELS: dict[str, str] = {
    "kigali":  "Kigali",
    "musanze": "Musanze",
    "huye":    "Huye",
    "rubavu":  "Rubavu",
    "kayonza": "Kayonza",
}

# ── Service listings ───────────────────────────────────────────────────────────
# Each entry: {"name": str, "tel": str, "note": str (optional)}

SERVICES: dict[str, dict[str, list[dict]]] = {
    "kigali": {
        "farming": [
            {"name": "RAB Headquarters",        "tel": "+250000000001"},
            {"name": "Gasabo Agri Ext. Office", "tel": "+250000000002"},
            {"name": "NAEB (Export crops)",     "tel": "+250000000003"},
        ],
        "health": [
            {"name": "CHUK Hospital",           "tel": "+250000000004", "note": "Emergency: 113"},
            {"name": "King Faisal Hospital",    "tel": "+250000000005"},
            {"name": "Kibagabaga Hospital",     "tel": "+250000000006"},
        ],
        "education": [
            {"name": "University of Rwanda",   "tel": "+250000000007"},
            {"name": "IPRC Kigali",            "tel": "+250000000008"},
            {"name": "Rwanda Polytechnic",     "tel": "+250000000009"},
        ],
    },
    "musanze": {
        "farming": [
            {"name": "RAB Musanze Station",    "tel": "+250000000010"},
            {"name": "COOPAMA Cooperative",    "tel": "+250000000011"},
        ],
        "health": [
            {"name": "Ruhengeri Hospital",     "tel": "+250000000012"},
            {"name": "Musanze Dist. Hospital", "tel": "+250000000013"},
        ],
        "education": [
            {"name": "UR College of Science",  "tel": "+250000000014"},
            {"name": "IPRC Musanze",           "tel": "+250000000015"},
        ],
    },
    "huye": {
        "farming": [
            {"name": "RAB Huye Station",       "tel": "+250000000016"},
            {"name": "Huye Farmers Coop",      "tel": "+250000000017"},
        ],
        "health": [
            {"name": "CHUB Hospital (Butare)", "tel": "+250000000018"},
            {"name": "Huye Dist. Hospital",    "tel": "+250000000019"},
        ],
        "education": [
            {"name": "UR Huye Campus",         "tel": "+250000000020"},
            {"name": "IPRC Huye",              "tel": "+250000000021"},
        ],
    },
    "rubavu": {
        "farming": [
            {"name": "RAB Rubavu Office",      "tel": "+250000000022"},
            {"name": "Rubavu Agri Coop",       "tel": "+250000000023"},
        ],
        "health": [
            {"name": "Rubavu Dist. Hospital",  "tel": "+250000000024"},
            {"name": "Gisenyi Health Centre",  "tel": "+250000000025"},
        ],
        "education": [
            {"name": "IPRC Western",           "tel": "+250000000026"},
            {"name": "Rubavu TTC",             "tel": "+250000000027"},
        ],
    },
    "kayonza": {
        "farming": [
            {"name": "RAB Kayonza Office",     "tel": "+250000000028"},
            {"name": "Eastern Province COOP",  "tel": "+250000000029"},
        ],
        "health": [
            {"name": "Kayonza Dist. Hospital", "tel": "+250000000030"},
            {"name": "Kabarondo Health Centre","tel": "+250000000031"},
        ],
        "education": [
            {"name": "IPRC Eastern",           "tel": "+250000000032"},
            {"name": "Kayonza TTC",            "tel": "+250000000033"},
        ],
    },
}

# ── Category labels for menus ──────────────────────────────────────────────────

SERVICE_LABELS: dict[str, str] = {
    "farming":   "Agri Offices",
    "health":    "Health Clinics",
    "education": "Schools / Colleges",
}
