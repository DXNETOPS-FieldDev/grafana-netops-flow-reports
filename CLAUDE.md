# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Grafana dashboards for Broadcom DX NetOps Performance Center (PC) flow/conversation data, queried
live via PC's OData4 API through Grafana's Infinity data source plugin. There is no backend, no
build system, and no tests — the deliverables are dashboard JSON files under `dashboards/`,
generated from Python scripts under `scripts/` rather than hand-edited.

## Commands

Regenerate a dashboard from its build script (writes to stdout, redirect into `dashboards/`):

```bash
python3 scripts/build_flow_overview_dashboard.py <environment> > dashboards/network-flow-overview.json
python3 scripts/build_top_protocols_by_interface_group_dashboard.py <environment> > dashboards/top-protocols-by-interface-group.json
```

`<environment>` defaults to `example` and must match a file in `scripts/envs/<environment>.json`.
There is no linter, formatter, or test suite configured for this repo.

Deploy a generated dashboard directly to Grafana (bypassing UI import):

```bash
curl -k -u admin:<password> -H 'Content-Type: application/json' \
  -X POST "https://<your-grafana-host>/api/dashboards/db" \
  -d @dashboards/<dashboard-file>.json
```

## Architecture

- **No ETL / no middle tier.** Grafana queries PC's OData4 API directly on every panel refresh.
  There is nothing to deploy or run besides the dashboard JSON itself.
- **Dashboards are generated, not hand-edited.** Each `scripts/build_*.py` script is a
  self-contained Python program that builds up a `panels` list and a `templating` dict as plain
  dicts, then `json.dump`s the full dashboard model to stdout. Panel/transform logic lives in the
  script; only environment-specific values (datasource UID, folder UID, dashboard UID, and
  baked-in reference lists like protocol/interface catalogs) come from `scripts/envs/*.json`. This
  lets panel logic be shared across PC instances without duplicating it per environment.
- **Environment config (`scripts/envs/<env>.json`)** holds the Infinity datasource UID, Grafana
  folder UID, and static reference data (known protocols, source/dest IPs, interface catalog,
  interface groups) that PC-specific custom variables are baked from at build time — see
  `scripts/envs/example.json` for the shape. Grafana's Infinity-backed query variables don't
  reliably populate options against this PC instance, so variables are `type: "custom"` static
  lists refreshed by rerunning a live query against PC and updating the env file, not by querying
  PC from Grafana at dashboard load time.
- **Panel targets query PC's OData4 endpoint directly** as `csv`-type Infinity targets
  (`format: "text/csv"`), using `$filter`/`$apply`/`groupby`/`aggregate` for server-side
  aggregation. Grafana transforms handle reshaping (joins, pivots) that OData4 can't express
  server-side, since `$apply` and `$expand` don't compose and `compute()` isn't implemented on
  this PC instance.
- **`docs/*-panel-queries.md`** documents the actual OData4 query used by each panel in each
  dashboard — check these first when debugging a panel rather than reverse-engineering the query
  out of the generated JSON.
- **`docs/odata4-flow-notes.md`** is the OData4 entity/field reference for the Network Flow
  metrics face and its related catalogs.

## Before touching OData4 queries or Grafana transforms

Read `docs/OData4-API-Notes.md` and `docs/Grafana-Infinity-Integration-Notes.md` in full first.
They document hard-won, non-obvious constraints of this specific PC instance and Grafana/Infinity
version — e.g. `$top` is mandatory (DA silently clamps/truncates otherwise with no pagination),
flow history is capped to ~1 hour by default regardless of requested range unless a DA-side config
is changed, `-1` is a reserved sentinel value that must be filtered explicitly, and several
`joinByField`/`organize`/variable-templating pitfalls that silently produce empty or wrong data
rather than erroring. Getting these wrong doesn't fail loudly — panels render with truncated,
empty, or subtly incorrect data — so treat these docs as required reading, not optional
background, before writing or modifying a query or transform.

## Adding a new environment

1. Create the target Grafana datasource and folder, note their UIDs.
2. Query PC directly (via `curl`) to collect any reference data the dashboard bakes in at build
   time (protocol lists, interface catalogs, interface groups).
3. Copy `scripts/envs/example.json` to `scripts/envs/<environment>.json` and fill in real values.
4. Run the relevant build script with the new environment name and redeploy.

## Adding a new dashboard

1. Identify the target entity/entities in PC's OData4 catalog (`GET /pc/odata4/api/` lists
   collections; `$metadata` gives field definitions).
2. Prototype queries with `curl` directly against PC before wiring into Grafana.
3. Always bound aggregate queries with a `$filter=Timestamp ge/le ...` time window, and always set
   `$top` explicitly.
4. For name lookups that require joining an aggregate result to a catalog collection, run both as
   separate Infinity targets on the same panel and join with Grafana's "Join by field" transform.

Use the two existing `scripts/build_*.py` files as worked examples, including the coalesce pattern
for resolving application names and the interface-group filter resolution pattern.
