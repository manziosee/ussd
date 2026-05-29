"""
Country-code → Jasmin SMPP connector routing.

How it works
────────────
1. Phone number comes in E.164 format: +250788000001
2. Strip the '+' and test progressively shorter prefixes (3 digits → 1 digit)
   against the connector_map.  First match wins.
3. Returns the Jasmin connector CID (e.g. "mtn_rw") or None (let Jasmin route).

Connector map is read from settings (can be overridden via SMS_GW_CONNECTOR_MAP_JSON).
"""
from __future__ import annotations


def get_country_code(phone: str) -> str | None:
    """
    Extract the numeric country-code prefix from an E.164 number.

    Returns just the digits (no '+'), e.g. "250" for +250788000001.
    Tests prefixes of length 3, 2, 1 and returns the shortest unique match
    found in the connector map.  If none matches, returns the 3-digit prefix
    as a best guess for logging purposes.
    """
    digits = phone.lstrip("+")
    for length in (3, 2, 1):
        prefix = digits[:length]
        if prefix:
            return prefix
    return None


def resolve_connector(phone: str, connector_map: dict[str, str]) -> str | None:
    """
    Return the Jasmin connector CID for the given phone number, or None.

    Tries 3-digit, 2-digit, and 1-digit prefixes in that order.
    None means Jasmin's own routing table should decide.
    """
    digits = phone.lstrip("+")
    for length in (3, 2, 1):
        prefix = digits[:length]
        if prefix in connector_map:
            return connector_map[prefix]
    return None


# Human-readable country names (for logging/responses)
COUNTRY_NAMES: dict[str, str] = {
    "250": "Rwanda",
    "254": "Kenya",
    "256": "Uganda",
    "255": "Tanzania",
    "233": "Ghana",
    "234": "Nigeria",
    "27":  "South Africa",
    "243": "DR Congo",
    "226": "Burkina Faso",
    "225": "Côte d'Ivoire",
    "237": "Cameroon",
    "221": "Senegal",
    "228": "Togo",
    "229": "Benin",
    "230": "Mauritius",
    "232": "Sierra Leone",
    "231": "Liberia",
    "220": "Gambia",
}


def country_name(code: str) -> str:
    return COUNTRY_NAMES.get(code, f"Unknown ({code})")
