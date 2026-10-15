# LUMA Outages (Home Assistant custom integration)

Puerto Rico grid data as Home Assistant sensors, from two kinds of source:

| Data | Source |
|---|---|
| Customers with/without power, planned upgrades, load shed, per LUMA region | LUMA's Mi LUMA outage map (undocumented endpoint) |
| Output of each power plant (MW) | hayluzpr.com `/api/luma-generation` (third party) |
| Outage zones per town | hayluzpr.com `/api/luma-town-outages` (third party) |

None of these are official APIs. LUMA has no developer API, and hayluzpr.com is an independent site that republishes
LUMA data. Any of them can change or disappear; the affected entities then show as unavailable and recover on their own.

## Install

1. Copy `custom_components/luma_outages` into your Home Assistant `config/custom_components/` folder.
2. Restart Home Assistant.
3. Settings → Devices & services → Add integration → **LUMA Outages**.
4. Pick what to follow. Change it later with the integration's **Configure** button.

You can use any combination: regions only, towns only, generation only, or all of them.
(If you only want hayluzpr.com data, leave the regions empty and LUMA is never contacted.)

## Regions (LUMA)

LUMA reports **per region**, not per city: Arecibo, Bayamón, Caguas, Carolina, Mayagüez, Ponce, San Juan.
Each selected region becomes a device ("LUMA San Juan"), plus an optional "Puerto Rico (total)" device.

Sensors
- Customers with power (%)
- Customers without service (%) and (count)
- Unplanned outage customers
- Planned upgrade customers
- Load shed customers
- Customers with service (count) and Total customers (both disabled by default)

Binary sensors
- **Load shed**: on when LUMA reports any customers affected by load shed in that region
- **Significant outage**: on when the share of customers without service reaches your threshold (default 5%)
- **Planned upgrades**: on when any customers are out for planned work

"Unplanned outage customers" is without service minus planned minus load shed. This assumes planned and load-shed
customers are counted inside the without-service total, which matches LUMA's portal.

## Generation (hayluzpr.com)

One device, "LUMA Generation":
- Total generation (MW), Total generation capacity (MW, disabled by default), Generation vs capacity (%)
- For each plant the feed lists (San Juan, Palo Seco, Aguirre, Costa Sur, Eco Eléctrica, AES at the time of writing):
  output (MW) and capacity used (%). The plant's max MW is an attribute.

Plants are discovered from the feed, so a new plant appears automatically.

## Towns (hayluzpr.com)

Pick any of the 78 municipalities. Each followed town becomes a device ("LUMA San Juan (town)"):
- **Affected zones**: how many zones in that town are listed as without service. The zone names are in the `zones`
  attribute.
- **Outage reported**: on when at least one zone is listed.

A town that isn't listed at all simply reads 0 / off. A separate "LUMA Towns" device has **Towns with outages**,
the island-wide count, with the town names as an attribute.

Zone names are passed through exactly as LUMA publishes them, quirks included (for example the feed currently lists a
zone named "BAYAMON" under Cidra).

Town data is by town, while the percentages are by region. LUMA does not publish which region a town belongs to in
these feeds, so the two are not linked automatically.

## Device emulation / "blocked" errors (LUMA only)

LUMA's endpoint only answers requests that look like a phone or the Mi LUMA site. By default the integration sends a
mobile Safari `User-Agent` plus `Origin`/`Referer` for miluma.lumapr.com. These headers are never sent to
hayluzpr.com. If setup says LUMA rejected the request:

1. Open `https://miluma.lumapr.com` in a desktop browser, open developer tools → Network.
2. Load the outage map and find the `regionsWithoutService` request.
3. Copy the request headers that identify the client (at minimum `User-Agent`; also `Origin`, `Referer` and any
   `x-` headers).
4. Paste them into **Custom request headers for LUMA** as JSON, for example:

```json
{
  "User-Agent": "Mozilla/5.0 (iPhone; ...)",
  "Origin": "https://miluma.lumapr.com",
  "Referer": "https://miluma.lumapr.com/"
}
```

Custom headers are merged over the defaults. If LUMA blocks by IP address or uses a JavaScript challenge, headers
alone won't be enough, and the town and generation data (which don't need this) will still work.

## Notes

- Each source is polled once per cycle, shared by all its entities. The default interval is 5 minutes (minimum 2).
  Please don't poll faster; these are small community and utility endpoints.
- Example automation:

```yaml
automation:
  - alias: "Outage reported in San Juan"
    triggers:
      - trigger: state
        entity_id: binary_sensor.luma_san_juan_town_outage_reported
        to: "on"
    actions:
      - action: notify.notify
        data:
          message: "LUMA lists zones without service in San Juan."
```

Entity IDs depend on the device and entity names; check yours under Settings → Entities.
