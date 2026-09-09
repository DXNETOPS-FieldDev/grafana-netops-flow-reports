# Deploying to a New Grafana Environment

Dashboards in this repo are generated from Python scripts rather than hand-edited JSON, so panel
and transform logic can be shared across environments while only the environment-specific values
(datasource, folder, dashboard UIDs, and any baked-in reference lists) vary.

## 1. Create the datasource and folder

In the target Grafana instance, create:
- An [Infinity data source](https://grafana.com/grafana/plugins/yesoreyeram-infinity-datasource/)
  configured with basic authentication against your PC instance, pointed at PC's OData4 v4
  endpoint (`/pc/odata4/api/`) — not the legacy v2 alias (`/pc/odata/api/`), which does not expose
  the Network Flow entities these dashboards query.
- A folder to hold the dashboards.

Note both UIDs.

## 2. Collect reference data

Grafana's Infinity-backed query variables don't reliably populate options against PC, so filter
variables (Protocol, Talkers, destination, Interface Groups, etc.) are static lists baked in at
build time from a live query against PC, not queried from Grafana at dashboard load time. Query PC
directly (e.g. with `curl`) to collect:

- Known protocol values
- Representative source/destination IPs (or whatever your dashboard's filters need)
- The interface catalog (`flowinboundinterfaces`/`flowoutboundinterfaces`, with device names
  expanded)
- Interface Groups and their member interface IDs (`groups` entity, `GroupType=automatic`, under
  "Interface Groups")

## 3. Create an environment config file

Copy `scripts/envs/example.json` to `scripts/envs/<environment>.json` and fill in your real
datasource UID, folder UID, and the reference data collected above. This file is meant to be
local-only — don't commit real hostnames/UIDs/IPs into this repo.

## 4. Generate the dashboard JSON

```bash
python3 scripts/build_flow_overview_dashboard.py <environment> > dashboards/network-flow-overview.json
python3 scripts/build_top_protocols_by_interface_group_dashboard.py <environment> > dashboards/top-protocols-by-interface-group.json
```

`<environment>` defaults to `example` if omitted.

## 5. Deploy

Either:

- **Import through the Grafana UI** (**Dashboards → New → Import**), uploading the generated JSON
  and pointing it at your Infinity datasource, or
- **Push via Grafana's dashboard API**:

```bash
curl -k -u admin:<password> -H 'Content-Type: application/json' \
  -X POST "https://<your-grafana-host>/api/dashboards/db" \
  -d @dashboards/<dashboard-file>.json
```

## One-off manual import (no real environment config yet)

The dashboard JSON committed under `dashboards/` is generated from the placeholder
`scripts/envs/example.json`, so its datasource/folder UIDs and filter values are just placeholders
(e.g. `REPLACE_WITH_YOUR_INFINITY_DATASOURCE_UID`). You can still import a dashboard file directly
through **Dashboards → New → Import** and re-point it at your own Infinity datasource by hand —
useful for a quick look, but the baked-in filter values (protocols, IPs, interfaces) won't match
your environment until you regenerate from a real env file.

## Building a new dashboard

1. Identify the target entity/entities in PC's OData4 catalog (`GET /pc/odata4/api/` lists all
   collections; `$metadata` provides full field definitions).
2. Prototype queries directly against PC with `curl` before wiring them into Grafana, to confirm
   `$filter`, `$apply`, and `$expand` behave as expected — see
   [OData4-API-Notes.md](OData4-API-Notes.md).
3. Always bound aggregate queries with a `$filter=Timestamp ge/le ...` time window — unbounded
   aggregation over flow data will hang.
4. Always set `$top` explicitly (see [OData4-API-Notes.md](OData4-API-Notes.md)).
5. For name lookups that require joining an aggregate result to a catalog collection, run both as
   separate Infinity targets on the same panel and use Grafana's **Join by field** transform (see
   [Grafana-Infinity-Integration-Notes.md](Grafana-Infinity-Integration-Notes.md)).

Use `scripts/build_flow_overview_dashboard.py` and
`scripts/build_top_protocols_by_interface_group_dashboard.py` as worked examples, including the
coalesce pattern used to resolve application names and the interface-group filter resolution
pattern.
