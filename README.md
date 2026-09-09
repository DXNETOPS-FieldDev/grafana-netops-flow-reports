# NetOps Flow Dashboards for Grafana

Grafana dashboards for network flow and conversation data from Broadcom DX **NetOps Performance
Center** (PC), queried live through PC's OData4 API — no middle-tier ingestion or caching layer.

## Contents

| Folder | Description |
|---|---|
| `dashboards/` | Grafana dashboard JSON files (import directly via Grafana UI or API) |
| `scripts/` | Python generators that build the dashboard JSON; `scripts/envs/` holds per-environment config (see [Deploying to a new environment](docs/Deploying-to-a-New-Grafana-Environment.md)) |
| `docs/` | Entity reference, per-panel query reference, and OData4/Grafana integration notes |

## Dashboards

| File | Report Name | Domain | Docs |
|---|---|---|---|
| `network-flow-overview.json` | Network Flow Overview | Flow | [Panel queries](docs/network-flow-overview-panel-queries.md) |
| `top-protocols-by-interface-group.json` | Top Protocols by Interface Group | Flow | [Panel queries](docs/top-protocols-by-interface-group-panel-queries.md) |

**Network Flow Overview** — traffic distribution by protocol, top talkers, bandwidth utilization
over time, per-protocol and per-application traffic trends, and an application traffic statistics
table. Includes Protocol, Talkers, and Destination filter variables.

**Top Protocols by Interface Group** — scopes flow data to a selected **Interface Group** (a
PC-defined grouping of flow-collecting interfaces) and breaks it down by protocol: traffic
distribution, top protocols by flow count/volume, a protocol trend over time, an
interface-and-protocol breakdown table and heatmap, a conversation-level drill-down reachable by
clicking any protocol, and one donut per known interface.

## Deploying to a new environment

See **[docs/Deploying-to-a-New-Grafana-Environment.md](docs/Deploying-to-a-New-Grafana-Environment.md)**
for the full guide, including the Python generator scripts that bake in each environment's
datasource/folder UIDs and reference data (protocol lists, interface catalogs) at build time.

For a one-off manual import instead:
1. In Grafana, go to **Dashboards → New → Import**.
2. Upload the JSON file or paste its contents.
3. Select your **Infinity** datasource when prompted.

The dashboard JSON committed here is generated from the placeholder `scripts/envs/example.json`,
so its datasource UID and filter values are placeholders until regenerated from a real
environment config.

## Datasource

Dashboards query PC's OData4 v4 endpoint (`/pc/odata4/api/`) — specifically the Network Flow
metrics face (`flowconversationmfs`) and related catalog entities — through the
[Infinity data source plugin](https://grafana.com/grafana/plugins/yesoreyeram-infinity-datasource/)
for Grafana, configured with basic authentication against PC. Unlike a name-matched SQL
datasource, each panel target references its Infinity datasource by UID, baked in at build time
from `scripts/envs/<environment>.json` — repointing a dashboard at a different datasource means
regenerating it from an environment config with that datasource's UID.

## Documentation

- `docs/odata4-flow-notes.md` — OData4 entity/field reference for the Network Flow metrics face
  and its related catalogs
- `docs/OData4-API-Notes.md` — PC-side query constraints and gotchas (`$top` requirements, the
  flow history retention cap, sentinel values, application-name resolution, etc.)
- `docs/Grafana-Infinity-Integration-Notes.md` — Grafana/Infinity implementation patterns and
  pitfalls (transform ordering, join modes, variable templating, data links, etc.)
- `docs/network-flow-overview-panel-queries.md` — the OData4 query behind each panel in Network
  Flow Overview
- `docs/top-protocols-by-interface-group-panel-queries.md` — the OData4 query behind each panel in
  Top Protocols by Interface Group
- `docs/Deploying-to-a-New-Grafana-Environment.md` — how to deploy this dashboard set to any
  Grafana + PC instance, and how to build a new dashboard
