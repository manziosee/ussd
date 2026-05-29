"""
Country-code → Jasmin SMPP connector routing.

How it works
────────────
1. Phone number comes in E.164 format: +250788000001
2. Strip the '+' and test progressively shorter prefixes (3 → 2 → 1 digit)
   against the connector_map. First match wins.
3. Returns the Jasmin connector CID or None (let Jasmin's routing table decide).

Connector names should be ISO 3166-1 alpha-2 country codes (rw, ke, ug …).
The operator creates each connector in Jasmin pointing at whatever SMPP
provider they use for that country. No carrier names belong in code.

By default the connector_map is EMPTY — Jasmin's own MT routing rules handle
dispatch, which is the correct global default. Entries are only needed when
you want to force a specific connector for a specific country prefix.
"""
from __future__ import annotations


def resolve_connector(phone: str, connector_map: dict[str, str]) -> str | None:
    """
    Return the Jasmin connector CID for the given E.164 phone number, or None.

    Tries 3-digit, 2-digit, and 1-digit numeric prefixes in that order.
    Returning None lets Jasmin's own routing table decide — always safe.
    """
    digits = phone.lstrip("+")
    for length in (3, 2, 1):
        prefix = digits[:length]
        if prefix in connector_map:
            return connector_map[prefix]
    return None


def get_country_code(phone: str) -> str | None:
    """
    Return the numeric dialing prefix of an E.164 number (for logging only).
    e.g. "+250788000001" → "250"
    """
    digits = phone.lstrip("+")
    return digits[:3] if len(digits) >= 3 else digits or None


# ── Human-readable country names (logging / response metadata) ────────────────
# Covers the most common dialing codes worldwide.
COUNTRY_NAMES: dict[str, str] = {
    # Africa
    "20":  "Egypt",                  "212": "Morocco",
    "213": "Algeria",                "216": "Tunisia",
    "218": "Libya",                  "220": "Gambia",
    "221": "Senegal",                "222": "Mauritania",
    "223": "Mali",                   "224": "Guinea",
    "225": "Côte d'Ivoire",          "226": "Burkina Faso",
    "227": "Niger",                  "228": "Togo",
    "229": "Benin",                  "230": "Mauritius",
    "231": "Liberia",                "232": "Sierra Leone",
    "233": "Ghana",                  "234": "Nigeria",
    "235": "Chad",                   "236": "Central African Rep.",
    "237": "Cameroon",               "238": "Cape Verde",
    "239": "São Tomé & Príncipe",    "240": "Equatorial Guinea",
    "241": "Gabon",                  "242": "Republic of Congo",
    "243": "DR Congo",               "244": "Angola",
    "245": "Guinea-Bissau",          "248": "Seychelles",
    "249": "Sudan",                  "250": "Rwanda",
    "251": "Ethiopia",               "252": "Somalia",
    "253": "Djibouti",               "254": "Kenya",
    "255": "Tanzania",               "256": "Uganda",
    "257": "Burundi",                "258": "Mozambique",
    "260": "Zambia",                 "261": "Madagascar",
    "263": "Zimbabwe",               "264": "Namibia",
    "265": "Malawi",                 "266": "Lesotho",
    "267": "Botswana",               "268": "Eswatini",
    "269": "Comoros",                "27":  "South Africa",
    # Americas
    "1":   "USA / Canada",           "52":  "Mexico",
    "53":  "Cuba",                   "54":  "Argentina",
    "55":  "Brazil",                 "56":  "Chile",
    "57":  "Colombia",               "58":  "Venezuela",
    "502": "Guatemala",              "503": "El Salvador",
    "504": "Honduras",               "505": "Nicaragua",
    "506": "Costa Rica",             "507": "Panama",
    "591": "Bolivia",                "592": "Guyana",
    "593": "Ecuador",                "595": "Paraguay",
    "597": "Suriname",               "598": "Uruguay",
    # Europe
    "30":  "Greece",                 "31":  "Netherlands",
    "32":  "Belgium",                "33":  "France",
    "34":  "Spain",                  "36":  "Hungary",
    "39":  "Italy",                  "40":  "Romania",
    "41":  "Switzerland",            "43":  "Austria",
    "44":  "United Kingdom",         "45":  "Denmark",
    "46":  "Sweden",                 "47":  "Norway",
    "48":  "Poland",                 "49":  "Germany",
    "351": "Portugal",               "352": "Luxembourg",
    "353": "Ireland",                "354": "Iceland",
    "355": "Albania",                "356": "Malta",
    "357": "Cyprus",                 "358": "Finland",
    "359": "Bulgaria",               "370": "Lithuania",
    "371": "Latvia",                 "372": "Estonia",
    "373": "Moldova",                "374": "Armenia",
    "375": "Belarus",                "380": "Ukraine",
    "381": "Serbia",                 "382": "Montenegro",
    "385": "Croatia",                "386": "Slovenia",
    "387": "Bosnia & Herzegovina",   "389": "North Macedonia",
    "420": "Czech Republic",         "421": "Slovakia",
    # Asia & Oceania
    "7":   "Russia / Kazakhstan",    "60":  "Malaysia",
    "61":  "Australia",              "62":  "Indonesia",
    "63":  "Philippines",            "64":  "New Zealand",
    "65":  "Singapore",              "66":  "Thailand",
    "81":  "Japan",                  "82":  "South Korea",
    "84":  "Vietnam",                "86":  "China",
    "91":  "India",                  "92":  "Pakistan",
    "93":  "Afghanistan",            "94":  "Sri Lanka",
    "95":  "Myanmar",                "98":  "Iran",
    "880": "Bangladesh",             "886": "Taiwan",
    "960": "Maldives",               "961": "Lebanon",
    "962": "Jordan",                 "963": "Syria",
    "964": "Iraq",                   "965": "Kuwait",
    "966": "Saudi Arabia",           "967": "Yemen",
    "968": "Oman",                   "971": "UAE",
    "972": "Israel",                 "973": "Bahrain",
    "974": "Qatar",                  "975": "Bhutan",
    "976": "Mongolia",               "977": "Nepal",
}


def country_name(code: str) -> str:
    """Human-readable name for a dialing code prefix, for logging."""
    return COUNTRY_NAMES.get(code, f"Unknown (+{code})")
