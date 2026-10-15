"""Constants for LUMA Outages."""

from __future__ import annotations

from .api import TOTAL_KEY, slugify

DOMAIN = "luma_outages"

CONF_REGIONS = "regions"
CONF_INCLUDE_TOTAL = "include_island_total"
CONF_TOWNS = "towns"
CONF_GENERATION = "include_generation"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_THRESHOLD = "significant_outage_percent"
CONF_HEADERS = "custom_headers"

DEFAULT_REGION = "san_juan"
DEFAULT_SCAN_INTERVAL = 5  # minutes
MIN_SCAN_INTERVAL = 2
DEFAULT_THRESHOLD = 5.0  # percent of a region's customers without service

# LUMA reports seven regions. Keys are slugs of the names the API uses.
REGION_OPTIONS: dict[str, str] = {
    "arecibo": "Arecibo",
    "bayamon": "Bayamón",
    "caguas": "Caguas",
    "carolina": "Carolina",
    "mayaguez": "Mayagüez",
    "ponce": "Ponce",
    "san_juan": "San Juan",
}

REGION_LABELS: dict[str, str] = {**REGION_OPTIONS, TOTAL_KEY: "Puerto Rico (total)"}

# The 78 municipalities. hayluzpr.com's town endpoint only lists towns that
# currently have zones without service, so the full list lives here.
_MUNICIPALITIES = (
    "Adjuntas", "Aguada", "Aguadilla", "Aguas Buenas", "Aibonito", "Añasco",
    "Arecibo", "Arroyo", "Barceloneta", "Barranquitas", "Bayamón", "Cabo Rojo",
    "Caguas", "Camuy", "Canóvanas", "Carolina", "Cataño", "Cayey", "Ceiba",
    "Ciales", "Cidra", "Coamo", "Comerío", "Corozal", "Culebra", "Dorado",
    "Fajardo", "Florida", "Guánica", "Guayama", "Guayanilla", "Guaynabo",
    "Gurabo", "Hatillo", "Hormigueros", "Humacao", "Isabela", "Jayuya",
    "Juana Díaz", "Juncos", "Lajas", "Lares", "Las Marías", "Las Piedras",
    "Loíza", "Luquillo", "Manatí", "Maricao", "Maunabo", "Mayagüez", "Moca",
    "Morovis", "Naguabo", "Naranjito", "Orocovis", "Patillas", "Peñuelas",
    "Ponce", "Quebradillas", "Rincón", "Río Grande", "Sabana Grande",
    "Salinas", "San Germán", "San Juan", "San Lorenzo", "San Sebastián",
    "Santa Isabel", "Toa Alta", "Toa Baja", "Trujillo Alto", "Utuado",
    "Vega Alta", "Vega Baja", "Vieques", "Villalba", "Yabucoa", "Yauco",
)

TOWN_OPTIONS: dict[str, str] = {slugify(name): name for name in _MUNICIPALITIES}
