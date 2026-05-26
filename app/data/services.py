"""
Static services directory for Rwanda — health clinics, agri offices, and schools
per district. Zero AI cost; data is updated manually by an admin.

Coverage: Kigali · Musanze · Huye · Rubavu · Kayonza
Categories: farming (agri extension offices) · health · education

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
            {"name": "RAB Headquarters",        "tel": "+250788309241"},
            {"name": "Gasabo Agri Ext. Office", "tel": "+250252580274"},
            {"name": "NAEB (Export crops)",     "tel": "+250252570611"},
        ],
        "health": [
            {"name": "CHUK Hospital",           "tel": "+250788603600", "note": "Emergency: 113"},
            {"name": "King Faisal Hospital",     "tel": "+250280082300"},
            {"name": "Kibagabaga Hospital",      "tel": "+250252570975"},
        ],
        "education": [
            {"name": "University of Rwanda",    "tel": "+250788300001"},
            {"name": "IPRC Kigali",             "tel": "+250252570388"},
            {"name": "Rwanda Polytechnic",      "tel": "+250252570001"},
        ],
    },
    "musanze": {
        "farming": [
            {"name": "RAB Musanze Station",     "tel": "+250252546217"},
            {"name": "COOPAMA Cooperative",     "tel": "+250788401000"},
        ],
        "health": [
            {"name": "Ruhengeri Hospital",      "tel": "+250252546002"},
            {"name": "Musanze Dist. Hospital",  "tel": "+250252546100"},
        ],
        "education": [
            {"name": "UR College of Science",   "tel": "+250252546300"},
            {"name": "IPRC Musanze",            "tel": "+250252546200"},
        ],
    },
    "huye": {
        "farming": [
            {"name": "RAB Huye Station",        "tel": "+250252530065"},
            {"name": "Huye Farmers Coop",       "tel": "+250788501000"},
        ],
        "health": [
            {"name": "CHUB Hospital (Butare)",  "tel": "+250252530009"},
            {"name": "Huye Dist. Hospital",     "tel": "+250252530200"},
        ],
        "education": [
            {"name": "UR Huye Campus",          "tel": "+250252530560"},
            {"name": "IPRC Huye",               "tel": "+250252530270"},
        ],
    },
    "rubavu": {
        "farming": [
            {"name": "RAB Rubavu Office",       "tel": "+250252560100"},
            {"name": "Rubavu Agri Coop",        "tel": "+250788601000"},
        ],
        "health": [
            {"name": "Rubavu Dist. Hospital",   "tel": "+250252560155"},
            {"name": "Gisenyi Health Centre",   "tel": "+250252560200"},
        ],
        "education": [
            {"name": "IPRC Western",            "tel": "+250252560300"},
            {"name": "Rubavu TTC",              "tel": "+250252560400"},
        ],
    },
    "kayonza": {
        "farming": [
            {"name": "RAB Kayonza Office",      "tel": "+250252562010"},
            {"name": "Eastern Province COOP",   "tel": "+250788701000"},
        ],
        "health": [
            {"name": "Kayonza Dist. Hospital",  "tel": "+250252562030"},
            {"name": "Kabarondo Health Centre", "tel": "+250252562100"},
        ],
        "education": [
            {"name": "IPRC Eastern",            "tel": "+250252562200"},
            {"name": "Kayonza TTC",             "tel": "+250252562300"},
        ],
    },
}

# ── Category labels for menus ──────────────────────────────────────────────────

SERVICE_LABELS: dict[str, str] = {
    "farming":   "Agri Offices",
    "health":    "Health Clinics",
    "education": "Schools / Colleges",
}
