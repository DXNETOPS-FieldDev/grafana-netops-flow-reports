import json
import sys
import os

# Per-environment values (datasource/folder/dashboard uids, and the baked-in
# template variable/legend values described below) live in scripts/envs/*.json
# so the same panel/transform logic can be reused across PC instances without
# duplicating this file. Usage: python3 build_flow_overview_dashboard.py <env>
# e.g. `python3 build_flow_overview_dashboard.py example > dashboards/network-flow-overview.json`
env_name = sys.argv[1] if len(sys.argv) > 1 else "example"
env_path = os.path.join(os.path.dirname(__file__), "envs", f"{env_name}.json")
with open(env_path) as f:
    ENV = json.load(f)

DS_UID = ENV["ds_uid"]
DS = {"type": "yesoreyeram-infinity-datasource", "uid": DS_UID}

TIME_FILTER = "Timestamp ge ${__from:date:seconds} and Timestamp le ${__to:date:seconds}"
# Multi-select variables use the `in` operator, supported by this PC
# instance, with Grafana's :singlequote format, which turns a multi-value
# variable into a comma-separated, quoted list - exactly what `in (...)`
# expects. When "All" is selected, Grafana expands to every individual value
# rather than a wildcard, so no special-casing is needed here.
VAR_FILTER = (
    TIME_FILTER +
    " and Protocol in (${Protocol:singlequote})" +
    " and SourceIP in (${Talkers:singlequote})" +
    " and DestinationIP in (${destination:singlequote})"
)

def csv_target(refId, url, columns=None, fmt="table", computed_columns=None):
    t = {
        "refId": refId,
        "datasource": DS,
        "type": "csv",
        "source": "url",
        "format": fmt,
        "url": url,
        "url_options": {"method": "GET"},
        "root_selector": "",
        "columns": columns or [],
        "parser": "backend",
        "filters": [],
    }
    if computed_columns:
        t["computed_columns"] = computed_columns
    return t

# Infinity-backed "query" type variables do not reliably populate options on
# this PC instance. Grafana's plain "custom" variable type is used instead -
# a static, comma-separated list with no datasource dependency. Values are
# baked in from a live query at build time (see the *_VALUES lists below) -
# rerun against fresh curl output to refresh.
def custom_variable(name, values, label):
    query = ",".join(values)
    options = [{"text": v, "value": v, "selected": False} for v in values]
    return {
        "name": name,
        "label": label,
        "type": "custom",
        "multi": True,
        "includeAll": True,
        "query": query,
        "options": [{"text": "All", "value": "$__all", "selected": True}] + options,
        "current": {"text": "All", "value": "$__all"},
    }

PROTOCOL_VALUES = ENV["protocol_values"]
SOURCE_IP_VALUES = ENV["source_ip_values"]
DEST_IP_VALUES = ENV["dest_ip_values"]

# Port -> resolved application name, fetched live per-environment (see the
# "Traffic by Application" panel comment below for why 65536 is excluded).
PORT_APP_NAMES = {int(k): v for k, v in ENV["port_app_names"].items()}

templating = {
    "list": [
        custom_variable("Protocol", PROTOCOL_VALUES, "Protocol"),
        custom_variable("Talkers", SOURCE_IP_VALUES, "Talkers"),
        custom_variable("destination", DEST_IP_VALUES, "destination"),
    ]
}

panels = []

# Traffic Distribution - donut by Protocol
panels.append({
    "id": 1,
    "title": "Traffic Distribution (Protocol)",
    "type": "piechart",
    "gridPos": {"h": 9, "w": 6, "x": 0, "y": 0},
    "datasource": DS,
    "targets": [
        csv_target("A",
            "/flowconversationmfs?$filter=" + VAR_FILTER +
            "&$apply=groupby((Protocol),aggregate(Bytes with sum as TotalBytes))"
            "&$orderby=TotalBytes desc&$top=20&$format=text/csv",
            columns=[
                {"selector": "Protocol", "type": "string"},
                {"selector": "TotalBytes", "type": "number"},
            ]),
    ],
    "options": {
        "pieType": "donut",
        "displayLabels": ["percent"],
        "legend": {"displayMode": "list", "placement": "bottom", "values": []},
        # Same bug as the bar gauge: without values=true, the panel reduces
        # the whole TotalBytes column to one number instead of one slice per
        # Protocol row.
        "reduceOptions": {"values": True, "calcs": []},
    },
    "fieldConfig": {"defaults": {"unit": "bytes"}, "overrides": []},
})

# Top Talkers - bar gauge by SourceIP
panels.append({
    "id": 2,
    "title": "Top Talkers",
    "type": "bargauge",
    "gridPos": {"h": 9, "w": 9, "x": 6, "y": 0},
    "datasource": DS,
    "targets": [
        csv_target("A",
            "/flowconversationmfs?$filter=" + VAR_FILTER +
            "&$apply=groupby((SourceIP),aggregate(Bytes with sum as TotalBytes))"
            "&$orderby=TotalBytes desc&$top=15&$format=text/csv",
            columns=[
                {"selector": "SourceIP", "type": "string"},
                {"selector": "TotalBytes", "type": "number"},
            ]),
    ],
    "options": {
        "displayMode": "gradient",
        "orientation": "horizontal",
        "showUnfilled": True,
        # reduceOptions.values=true renders one bar per row (using each row's
        # own value) instead of the default "calcs" mode, which reduces the
        # whole table down to a single bar.
        "reduceOptions": {"values": True, "calcs": []},
    },
    "fieldConfig": {
        "defaults": {
            "unit": "bytes",
            "color": {"mode": "continuous-GrYlRd"},
        },
        "overrides": [],
    },
})

# Total BW Usage - stacked area, Bandwidth In/Out
panels.append({
    "id": 3,
    "title": "Total BW Usage",
    "type": "timeseries",
    "gridPos": {"h": 9, "w": 9, "x": 15, "y": 0},
    "datasource": DS,
    "targets": [
        csv_target("A",
            "/flowconversationmfs?$filter=" + VAR_FILTER +
            "&$apply=groupby((Timestamp),aggregate("
            "BandwidthUtilIn with sum as BandwidthIn,BandwidthUtilOut with sum as BandwidthOut))"
            "&$orderby=Timestamp asc&$top=2000&$format=text/csv",
            fmt="timeseries",
            columns=[
                {"selector": "Timestamp", "type": "timestamp_epoch_s"},
                {"selector": "BandwidthIn", "type": "number"},
                {"selector": "BandwidthOut", "type": "number"},
            ]),
    ],
    "fieldConfig": {
        "defaults": {"custom": {"fillOpacity": 35, "stacking": {"mode": "normal"}}},
        "overrides": [
            {
                "matcher": {"id": "byName", "options": "BandwidthIn"},
                "properties": [
                    {"id": "displayName", "value": "Bandwidth In"},
                    {"id": "color", "value": {"mode": "fixed", "fixedColor": "#5794F2"}},
                ],
            },
            {
                "matcher": {"id": "byName", "options": "BandwidthOut"},
                "properties": [
                    {"id": "displayName", "value": "Bandwidth Out"},
                    {"id": "color", "value": {"mode": "fixed", "fixedColor": "#FF780A"}},
                ],
            },
        ],
    },
    "options": {"legend": {"displayMode": "list", "placement": "bottom"}},
})

# Traffic by Protocol - area time series, one series per Protocol
panels.append({
    "id": 4,
    "title": "Traffic by Protocol",
    "type": "timeseries",
    "gridPos": {"h": 9, "w": 12, "x": 0, "y": 9},
    "datasource": DS,
    "targets": [
        csv_target("A",
            "/flowconversationmfs?$filter=" + VAR_FILTER +
            "&$apply=groupby((Timestamp,Protocol),aggregate(Bytes with sum as TotalBytes))"
            "&$orderby=Timestamp asc&$top=20000&$format=text/csv",
            fmt="timeseries",
            columns=[
                {"selector": "Timestamp", "type": "timestamp_epoch_s"},
                {"selector": "Protocol", "type": "string"},
                {"selector": "TotalBytes", "type": "number"},
            ]),
    ],
    "fieldConfig": {
        # {{Protocol}} references the series' own label (from the groupby
        # dimension) instead of showing the raw field name "TotalBytes" in
        # the legend.
        "defaults": {"unit": "bytes", "displayName": "${__field.labels.Protocol}", "custom": {"fillOpacity": 25, "stacking": {"mode": "normal"}}},
        "overrides": [],
    },
    "options": {"legend": {"displayMode": "list", "placement": "bottom"}},
})

# Traffic by Application - area time series, one series per DestinationPort
panels.append({
    "id": 5,
    "title": "Traffic by Application",
    "type": "timeseries",
    "gridPos": {"h": 9, "w": 12, "x": 12, "y": 9},
    "datasource": DS,
    "targets": [
        csv_target("A",
            "/flowconversationmfs?$filter=" + VAR_FILTER +
            "&$apply=groupby((Timestamp,DestinationPort),aggregate(Bytes with sum as TotalBytes))"
            "&$orderby=Timestamp asc&$top=20000&$format=text/csv",
            fmt="timeseries",
            columns=[
                {"selector": "Timestamp", "type": "timestamp_epoch_s"},
                {"selector": "DestinationPort", "type": "string"},
                {"selector": "TotalBytes", "type": "number"},
            ]),
    ],
    # Per-port legend labels ("https-443", "ssh-22", ...) via the same
    # UserDefinedAppName/catalog resolution used elsewhere. This panel is a
    # single-query multi-series pivot (no join happening live), so the
    # mapping is baked in as static per-series overrides rather than
    # resolved dynamically - fetched live at build time, not guessed.
    # Port 65536 is intentionally excluded: it is a non-real "unknown source
    # port" sentinel that maps to several different applications depending on
    # classification, so a single resolved name would be misleading - it is
    # left as the raw port number instead.
    "fieldConfig": {
        "defaults": {"unit": "bytes", "displayName": "${__field.labels.DestinationPort}", "custom": {"fillOpacity": 25, "stacking": {"mode": "normal"}}},
        "overrides": [
            {
                "matcher": {"id": "byName", "options": f'TotalBytes {{DestinationPort="{port}"}}'},
                "properties": [{"id": "displayName", "value": f"{name}-{port}"}],
            }
            for port, name in PORT_APP_NAMES.items()
        ],
    },
    "options": {"legend": {"displayMode": "list", "placement": "bottom"}},
})

# Bottom stats table - by resolved Application name (not raw DestinationPort)
#
# ApplicationID alone isn't reliable (rows with the same ApplicationID
# sentinel, e.g. "-1_0_-1", can carry different UserDefinedAppName overrides),
# so this splits into an override branch (name already on the row, no join)
# and an NBAR branch (joined against the flowapplications catalog), each
# pre-aggregating Flows + TrafficVolume, then stacks them (merge) and joins
# the catalog with mode=outerTabular (string joins require this, not "outer" -
# see the README's Grafana/Infinity integration notes), then coalesces the
# two name sources with calculateField/firstNotNull.
panels.append({
    "id": 6,
    "title": "Application Traffic Stats",
    "type": "table",
    "gridPos": {"h": 8, "w": 24, "x": 0, "y": 18},
    "datasource": DS,
    # Flow_per_Sec/Traffic_per_sec (rate columns) dropped: this PC instance's
    # OData4 does not implement $apply/compute(), and Grafana's ${__range_s}
    # does not interpolate into Infinity's computed_columns. There is no way
    # to derive a per-second rate here without a middle-tier service, which
    # this project deliberately avoids.
    "targets": [
        csv_target("A",
            "/flowconversationmfs?$filter=" + VAR_FILTER +
            " and UserDefinedOverride eq true"
            "&$apply=groupby((UserDefinedAppName,DestinationPort),aggregate("
            "Bytes with sum as TrafficVolume,FlowCount with sum as Flows))"
            "&$orderby=TrafficVolume desc&$top=20&$format=text/csv",
            columns=[
                {"selector": "UserDefinedAppName", "text": "OverrideName", "type": "string"},
                {"selector": "DestinationPort", "type": "string"},
                {"selector": "TrafficVolume", "type": "number"},
                {"selector": "Flows", "type": "number"},
            ]),
        csv_target("B",
            "/flowconversationmfs?$filter=" + VAR_FILTER +
            " and UserDefinedOverride eq false"
            "&$apply=groupby((ApplicationID,DestinationPort),aggregate("
            "Bytes with sum as TrafficVolume,FlowCount with sum as Flows))"
            "&$orderby=TrafficVolume desc&$top=20&$format=text/csv",
            columns=[
                {"selector": "ApplicationID", "type": "string"},
                {"selector": "DestinationPort", "type": "string"},
                {"selector": "TrafficVolume", "type": "number"},
                {"selector": "Flows", "type": "number"},
            ]),
        csv_target("C",
            "/flowapplications?$select=ID,Name&$top=2000&$format=text/csv",
            columns=[
                {"selector": "ID", "text": "ApplicationID", "type": "string"},
                {"selector": "Name", "text": "CatalogName", "type": "string"},
            ]),
    ],
    "transformations": [
        {"id": "merge", "filter": {"id": "byRefId", "options": "A|B"}, "options": {}},
        {"id": "joinByField", "options": {"byField": "ApplicationID", "mode": "outerTabular"}},
        {
            "id": "calculateField",
            "options": {
                "mode": "reduceRow",
                "reduce": {"reducer": "firstNotNull", "include": ["OverrideName", "CatalogName"]},
                "alias": "Application",
            },
        },
        # joinByField mode=outerTabular is a full outer join, not a "left"
        # join - it keeps every one of the catalog's ~1438 rows even when
        # nothing in our merged (A,B) data matches them. Those leftover
        # catalog-only rows have no TrafficVolume/Flows at all (they never
        # came from real flow data), and once `limit` needs more rows than
        # our actual ~11-20 real ones to fill its quota, it pads with them -
        # showing up as "applications with no data". Drop anything without a
        # real Traffic Volume before sorting/limiting.
        {
            "id": "filterByValue",
            "options": {
                # Still named "TrafficVolume" here - organize's rename runs
                # after this step.
                "filters": [{"fieldName": "TrafficVolume", "config": {"id": "isNotNull", "options": {}}}],
                "type": "include",
                "match": "all",
            },
        },
        # "Organize fields by name" (indexByName) only reliably reorders
        # columns for a single-query-derived frame - this frame's provenance
        # is still tagged as coming from 3 queries (A/B/C) even after
        # merge+join+calculateField, which causes indexByName to no-op. An
        # extra no-op merge here flattens that multi-query provenance before
        # organize runs.
        {"id": "merge", "options": {}},
        {
            "id": "organize",
            "options": {
                "renameByName": {"TrafficVolume": "Traffic Volume", "DestinationPort": "Port"},
                "excludeByName": {"ApplicationID": True, "OverrideName": True, "CatalogName": True},
                "indexByName": {"Application": 0, "DestinationPort": 1, "Flows": 2, "TrafficVolume": 3},
            },
        },
        {"id": "sortBy", "options": {"fields": {}, "sort": [{"field": "Traffic Volume", "desc": True}]}},
        {"id": "limit", "options": {"limitField": 20}},
    ],
    "fieldConfig": {
        "defaults": {},
        "overrides": [
            {"matcher": {"id": "byName", "options": "Traffic Volume"}, "properties": [{"id": "unit", "value": "bytes"}]},
            {
                "matcher": {"id": "byName", "options": "Application"},
                "properties": [
                    {"id": "mappings", "value": [{"type": "special", "options": {"match": "null", "result": {"text": "Unclassified"}}}]},
                ],
            },
        ],
    },
    "options": {},
})

dashboard = {
    "dashboard": {
        "title": "Network Flow Overview",
        "tags": ["network-flow", "odata4", "grafana-reports"],
        "timezone": "browser",
        "schemaVersion": 39,
        "version": 0,
        "refresh": "auto",
        "time": {"from": "now-1h", "to": "now"},
        "templating": templating,
        "panels": panels,
    },
    "folderUid": ENV["folder_uid"],
    "overwrite": True,
}
if "dashboard_uid" in ENV:
    dashboard["dashboard"]["uid"] = ENV["dashboard_uid"]

print(json.dumps(dashboard, indent=2))
