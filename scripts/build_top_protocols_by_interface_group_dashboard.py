import json
import sys
import os

# Same per-environment pattern as build_flow_overview_dashboard.py (see that
# file's header comment for the rationale). Usage:
# python3 build_top_protocols_by_interface_group_dashboard.py <env>
env_name = sys.argv[1] if len(sys.argv) > 1 else "example"
env_path = os.path.join(os.path.dirname(__file__), "envs", f"{env_name}.json")
with open(env_path) as f:
    ENV = json.load(f)

DS_UID = ENV["ds_uid"]
DS = {"type": "yesoreyeram-infinity-datasource", "uid": DS_UID}

TIME_FILTER = "Timestamp ge ${__from:date:seconds} and Timestamp le ${__to:date:seconds}"

# PC's `groups` entity (GroupType "automatic", parent "Interface Groups")
# models flow interface groupings, but flowconversationmfs'
# `groups` nav property does not support `$filter=groups/any(...)` on this PC
# instance - it returns 200 with an empty result set rather than an error.
# The reliable path: resolve each group's member flow interfaces once via
# `groups(<id>)?$expand=flowinboundinterfaces,flowoutboundinterfaces`, then
# filter flowconversationmfs directly on the scalar InInterfaceID/
# OutInterfaceID fields, which *is* supported.
#
# The full boolean sub-expression (not just the ID list) is baked into each
# option's value - see interface_group_variable() below for why.
VAR_FILTER = TIME_FILTER + " and (${InterfaceGroup:raw})"

def csv_target(refId, url, columns=None, fmt="table"):
    return {
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

# For catalog lookups needing a nested $expand (e.g. flowdevice's Name inline
# on an interface row) - $apply and $expand don't compose on this PC instance
# (see the README's OData4 API notes), and CSV can't represent the resulting nested object,
# so this uses $format=json with root_selector "value" and dotted column
# selectors ("flowdevice.Name") instead of csv_target's flat CSV columns.
def json_target(refId, url, columns=None):
    return {
        "refId": refId,
        "datasource": DS,
        "type": "json",
        "source": "url",
        "format": "table",
        "url": url,
        "url_options": {"method": "GET"},
        "root_selector": "value",
        "columns": columns or [],
        "parser": "backend",
        "filters": [],
    }

# Grafana's "custom" variable type derives its runtime value entirely from
# its "query" string, not from the "options"/"current" fields in the
# underlying JSON - those are not authoritative. A variable whose display
# label differs from its underlying value must encode that distinction
# directly in "query", using Grafana's documented `text : value` pair syntax
# (comma-separated pairs, colon-separated within each pair).
#
# Because the pair separator in "query" is also a comma, a value containing
# commas (e.g. a comma-joined interface-ID list) would be torn into extra,
# bogus options. Instead, each option's value is the entire boolean
# sub-expression (eq/or chains, no `in (...)`), which contains no commas -
# see VAR_FILTER above, which wraps ${InterfaceGroup:raw} directly in
# parens rather than feeding it into `in (...)`.
#
# Groups with zero flow-collecting interfaces (e.g. a group of regular
# polled interfaces none of which are enrolled in flow collection) get a
# single always-empty condition. The sentinel is
# `InInterfaceID eq 0`, not `-1`: flowconversationmfs uses -1 as its own
# "unknown/unresolved interface" value on real rows (the same sentinel
# pattern as ApplicationID=-1), so filtering on -1 would pull in unrelated
# unknown-interface traffic instead of showing an empty panel. No real PC
# interface ID is ever 0 on this instance.
#
# :raw forces literal, unescaped substitution of the resolved value into the
# URL - defensive here since the value is plain ASCII with no reserved
# characters, but matches the explicit-modifier convention used everywhere
# else in these dashboards (${__from:date:seconds}, ${Protocol:singlequote}).
def interface_group_expr(ids):
    if not ids:
        return "InInterfaceID eq 0"
    fields = ["InInterfaceID", "OutInterfaceID"]
    return " or ".join(f"{f} eq {i}" for f in fields for i in sorted(ids))

def interface_group_variable(groups):
    options = [{"text": g["name"], "value": interface_group_expr(g["ids"])} for g in groups]
    query = ",".join(f"{o['text']} : {o['value']}" for o in options)
    return {
        "name": "InterfaceGroup",
        "label": "Interface Group",
        "type": "custom",
        "multi": False,
        "includeAll": False,
        "query": query,
        "options": [dict(o, selected=(i == 0)) for i, o in enumerate(options)],
        "current": {"text": options[0]["text"], "value": options[0]["value"]},
    }

# "Protocol" variable - not primarily a manual dropdown (though it works as
# one), but the landing spot for the data links below: clicking a protocol
# bar/slice sets this to that protocol and the "Conversations by Host" panel
# picks it up. Same "text : value" custom-variable convention as
# InterfaceGroup, and the same reason each option's *value* is a full OData
# boolean clause (`Protocol eq '<name>'`) rather than the bare name: it
# sidesteps ever needing the clicked value to match a predefined option (the
# data link below builds this same clause directly from the clicked field,
# using the option list only for manual selection / the default "All").
def protocol_variable(protocol_values):
    # "All" needs a real always-true clause referencing an actual field -
    # a bare literal comparison ("1 eq 1") returns a server error on this PC
    # instance, unlike every other filter clause used in these dashboards,
    # which all reference real fields.
    options = [{"text": "All", "value": "Bytes ge 0"}]
    options += [{"text": p, "value": f"Protocol eq '{p}'"} for p in protocol_values]
    query = ",".join(f"{o['text']} : {o['value']}" for o in options)
    return {
        "name": "Protocol",
        "label": "Protocol",
        "type": "custom",
        "multi": False,
        "includeAll": False,
        "query": query,
        "options": [dict(o, selected=(i == 0)) for i, o in enumerate(options)],
        "current": {"text": options[0]["text"], "value": options[0]["value"]},
    }

templating = {"list": [interface_group_variable(ENV["interface_groups"]), protocol_variable(ENV["protocol_values"])]}

CONV_FILTER = TIME_FILTER + " and (${InterfaceGroup:raw}) and (${Protocol:raw})"

# Same filter as CONV_FILTER, used by panels that should also narrow when a
# protocol is clicked - "Protocol Traffic Over Time" and "Interfaces &
# Protocols" - but not by the 3 summary panels themselves (donut/bar gauges),
# which stay on VAR_FILTER alone so they keep showing the full protocol
# breakdown as context for what to click next, rather than collapsing to a
# single protocol once one's already been picked.
PROTOCOL_SCOPED_FILTER = CONV_FILTER

# Drill-down link used on every "by Protocol" panel below: clicking a
# bar/slice sets Protocol to a clause built from *that row's own* Protocol
# field (${__data.fields["Protocol"]} - bracket form, not dot form, per
# Grafana's own data-links docs) and reloads this same dashboard with it
# applied, preserving both the time range (${__url_time_range}) and whichever
# Interface Group is currently selected (${InterfaceGroup:queryparam} - this
# format already emits the full "var-InterfaceGroup=..." pair, so it isn't
# prefixed with one manually). There is no reliable anchor/scroll-to-panel
# navigation within the same dashboard in current Grafana versions, so the
# Conversations panel is placed near the top of the dashboard instead, to
# keep it in view without scrolling after the reload.
def protocol_drilldown_link(dashboard_slug, dashboard_uid):
    return [{
        "title": "View Conversations for this Protocol",
        "url": (
            f"d/{dashboard_uid}/{dashboard_slug}?${{InterfaceGroup:queryparam}}"
            "&var-Protocol=Protocol eq '${__data.fields[\"Protocol\"]}'"
            "&${__url_time_range}"
        ),
        "targetBlank": False,
    }]

DRILLDOWN_LINKS = protocol_drilldown_link(
    "top-protocols-by-interface-group", ENV["top_protocols_by_interface_group_dashboard_uid"]
)

panels = []

# Clear Protocol Filter - an HTML anchor tag, not a markdown link and not a
# Grafana data link.
#
# Not markdown: a Text panel in "markdown" mode can fail to render
# `[text](url)` link syntax as a clickable link when the URL contains
# template variables, even though the variable substitution itself succeeds
# - the markdown link syntax is displayed as literal text instead. "html"
# mode with a raw <a> tag avoids the markdown-to-HTML parsing step entirely.
#
# Not a data link, since there's no query/clicked-row context here to build
# one from. Grafana's global macros (${__url_time_range},
# ${InterfaceGroup:queryparam}) resolve in Text panel content the same way
# they do in data links or panel titles - they aren't data-link-exclusive.
# Reuses protocol_drilldown_link's same self-URL shape, just with Protocol
# hardcoded to the "All" option's own value instead of a clicked field. This
# exists because toggling the filter off by clicking the same value again
# isn't possible - Grafana data links are static per-row templates with no
# way to check "is this already selected" and branch to a different link -
# so a one-click reset next to it is the practical alternative (the Protocol
# dropdown itself is also always available for the same reset; this is just
# a more visible shortcut to it).
#
# The href below is a fully-qualified absolute URL (this environment's own
# Grafana base URL), not a relative path - a relative href in a raw HTML
# anchor inside a Text panel can resolve incorrectly and navigate to the
# Grafana root instead of the intended dashboard. This differs from Grafana
# Data Links, which resolve internal dashboard references correctly on
# their own.
_reset_url = (
    f"{ENV['grafana_base_url']}/d/{ENV['top_protocols_by_interface_group_dashboard_uid']}/"
    f"top-protocols-by-interface-group?${{InterfaceGroup:queryparam}}"
    f"&var-Protocol=Bytes ge 0&${{__url_time_range}}"
)
panels.append({
    "id": 20,
    "title": "",
    "type": "text",
    "gridPos": {"h": 2, "w": 24, "x": 0, "y": 0},
    "options": {
        "mode": "html",
        "content": f'<a href="{_reset_url}" style="font-weight: bold;">Clear Protocol Filter (reset to All)</a>',
    },
})

# Traffic Distribution by Protocol - donut, share of bytes
panels.append({
    "id": 1,
    "title": "Traffic Distribution by Protocol",
    "type": "piechart",
    "gridPos": {"h": 9, "w": 8, "x": 0, "y": 2},
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
        # Without values=true this reduces the whole TotalBytes column to one
        # number instead of one slice per Protocol row (same bug as noted for
        # every other single-value-style panel in the flow dashboards).
        "reduceOptions": {"values": True, "calcs": []},
    },
    "fieldConfig": {"defaults": {"unit": "bytes", "links": DRILLDOWN_LINKS}, "overrides": []},
})

# Top Protocols by Flow Count - bar gauge
panels.append({
    "id": 2,
    "title": "Top Protocols by Flow Count",
    "type": "bargauge",
    "gridPos": {"h": 9, "w": 8, "x": 8, "y": 2},
    "datasource": DS,
    "targets": [
        csv_target("A",
            "/flowconversationmfs?$filter=" + VAR_FILTER +
            "&$apply=groupby((Protocol),aggregate(FlowCount with sum as TotalFlows))"
            "&$orderby=TotalFlows desc&$top=10&$format=text/csv",
            columns=[
                {"selector": "Protocol", "type": "string"},
                {"selector": "TotalFlows", "type": "number"},
            ]),
    ],
    "options": {
        "displayMode": "gradient",
        "orientation": "horizontal",
        "showUnfilled": True,
        "reduceOptions": {"values": True, "calcs": []},
    },
    "fieldConfig": {
        "defaults": {"color": {"mode": "continuous-GrYlRd"}, "links": DRILLDOWN_LINKS},
        "overrides": [],
    },
})

# Top Protocols by Traffic Volume - bar gauge
panels.append({
    "id": 3,
    "title": "Top Protocols by Traffic Volume",
    "type": "bargauge",
    "gridPos": {"h": 9, "w": 8, "x": 16, "y": 2},
    "datasource": DS,
    "targets": [
        csv_target("A",
            "/flowconversationmfs?$filter=" + VAR_FILTER +
            "&$apply=groupby((Protocol),aggregate(Bytes with sum as TotalBytes))"
            "&$orderby=TotalBytes desc&$top=10&$format=text/csv",
            columns=[
                {"selector": "Protocol", "type": "string"},
                {"selector": "TotalBytes", "type": "number"},
            ]),
    ],
    "options": {
        "displayMode": "gradient",
        "orientation": "horizontal",
        "showUnfilled": True,
        "reduceOptions": {"values": True, "calcs": []},
    },
    "fieldConfig": {
        "defaults": {"unit": "bytes", "color": {"mode": "continuous-BlPu"}, "links": DRILLDOWN_LINKS},
        "overrides": [],
    },
})

# Conversations by Host - table, drill-down target for the three "by
# Protocol" panels above. Placed right after them (not at the bottom of the
# dashboard) so it's in view without scrolling once a drill-down link
# reloads the page. No hostname resolution exists in this OData schema (no
# reverse-DNS entity), so "host" here means the raw SourceIP/DestinationIP,
# same as every other panel in these dashboards.
panels.append({
    "id": 19,
    # ":text" (not the default/:raw) shows the variable's display label -
    # "https", "All" - rather than its underlying value, which for Protocol
    # is the full OData clause (`Protocol eq 'https'`) that would otherwise
    # show up verbatim in the title.
    "title": "Conversations by Host — Protocol: ${Protocol:text}",
    "type": "table",
    "gridPos": {"h": 9, "w": 24, "x": 0, "y": 11},
    "datasource": DS,
    "targets": [
        csv_target("A",
            "/flowconversationmfs?$filter=" + CONV_FILTER +
            "&$apply=groupby((SourceIP,DestinationIP),aggregate("
            "Bytes with sum as TrafficVolume,FlowCount with sum as Flows))"
            "&$orderby=TrafficVolume desc&$top=100&$format=text/csv",
            columns=[
                {"selector": "SourceIP", "type": "string"},
                {"selector": "DestinationIP", "type": "string"},
                {"selector": "TrafficVolume", "type": "number"},
                {"selector": "Flows", "type": "number"},
            ]),
    ],
    "transformations": [
        {"id": "organize", "options": {"renameByName": {"TrafficVolume": "Traffic Volume"}}},
        {"id": "sortBy", "options": {"fields": {}, "sort": [{"field": "Traffic Volume", "desc": True}]}},
    ],
    "fieldConfig": {
        "defaults": {},
        "overrides": [
            {
                "matcher": {"id": "byName", "options": "Traffic Volume"},
                "properties": [
                    {"id": "unit", "value": "bytes"},
                    {"id": "custom.cellOptions", "value": {"type": "gauge", "mode": "basic"}},
                ],
            },
        ],
    },
    "options": {},
})

# Protocol Traffic Over Time - stacked area, one series per Protocol
panels.append({
    "id": 4,
    "title": "Protocol Traffic Over Time — Protocol: ${Protocol:text}",
    "type": "timeseries",
    "gridPos": {"h": 9, "w": 24, "x": 0, "y": 20},
    "datasource": DS,
    "targets": [
        csv_target("A",
            "/flowconversationmfs?$filter=" + PROTOCOL_SCOPED_FILTER +
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
        # ${__field.labels.Protocol} shows the series' own groupby label in
        # the legend instead of the raw field name "TotalBytes" - the
        # mustache-style {{Protocol}} syntax is silently treated as a literal
        # string on this Grafana version, not a template.
        "defaults": {
            "unit": "bytes",
            "displayName": "${__field.labels.Protocol}",
            "custom": {"fillOpacity": 25, "stacking": {"mode": "normal"}},
        },
        "overrides": [],
    },
    "options": {"legend": {"displayMode": "list", "placement": "bottom"}},
})

# Interfaces & Protocols - table, one row per (interface, protocol) combo.
#
# A flow record carries two interface fields - InInterfaceID (where it
# entered a device) and OutInterfaceID (where it left) - so "protocols seen
# on interface X" genuinely means union both directions, not pick one. Two
# branches, each scoped to the *same* VAR_FILTER (matches if either field is
# in the selected group) but grouped on only one of the two ID fields at a
# time, renamed to a shared "InterfaceID" column via the column `text`
# override so refId A/B stack into one shape on merge. A given interface can
# appear as an ingress point for some flows and an egress point for others
# with the *same* protocol, which (without a consolidation step) can show up
# as two rows for the same (interface, protocol) pair. This is accepted as a
# minor cosmetic tradeoff: consolidating with a `groupBy` step requires
# scoping it carefully to avoid corrupting the unrelated catalog frame still
# present in the pipeline at that point (see the README's Grafana/Infinity
# integration notes on unfiltered transform steps), and the simpler
# structural copy of the "Application Traffic Stats" panel in Network Flow
# Overview (merge -> join -> filter -> merge -> organize -> sort) is more
# reliable.
panels.append({
    "id": 5,
    "title": "Interfaces & Protocols — Protocol: ${Protocol:text}",
    "type": "table",
    "gridPos": {"h": 10, "w": 24, "x": 0, "y": 29},
    "datasource": DS,
    "targets": [
        csv_target("A",
            "/flowconversationmfs?$filter=" + PROTOCOL_SCOPED_FILTER +
            # -1 is PC's own "unknown/unresolved interface" sentinel (real
            # traffic can carry it) - excluded here at the query level so it
            # never reaches rendering as a meaningless "-1" row/label, rather
            # than trying to filter or map it away after the fact.
            " and InInterfaceID ne -1" +
            "&$apply=groupby((InInterfaceID,Protocol),aggregate("
            "Bytes with sum as TrafficVolume,FlowCount with sum as Flows))"
            "&$orderby=TrafficVolume desc&$top=200&$format=text/csv",
            columns=[
                {"selector": "InInterfaceID", "text": "InterfaceID", "type": "number"},
                {"selector": "Protocol", "type": "string"},
                {"selector": "TrafficVolume", "type": "number"},
                {"selector": "Flows", "type": "number"},
            ]),
        csv_target("B",
            "/flowconversationmfs?$filter=" + PROTOCOL_SCOPED_FILTER +
            " and OutInterfaceID ne -1" +
            "&$apply=groupby((OutInterfaceID,Protocol),aggregate("
            "Bytes with sum as TrafficVolume,FlowCount with sum as Flows))"
            "&$orderby=TrafficVolume desc&$top=200&$format=text/csv",
            columns=[
                {"selector": "OutInterfaceID", "text": "InterfaceID", "type": "number"},
                {"selector": "Protocol", "type": "string"},
                {"selector": "TrafficVolume", "type": "number"},
                {"selector": "Flows", "type": "number"},
            ]),
        json_target("C",
            "/flowinboundinterfaces?$expand=flowdevice($select=Name)"
            "&$select=ID,Name&$top=100&$format=json",
            columns=[
                {"selector": "ID", "text": "InterfaceID", "type": "number"},
                {"selector": "Name", "text": "Interface", "type": "string"},
                {"selector": "flowdevice.Name", "text": "Device", "type": "string"},
            ]),
    ],
    "transformations": [
        {"id": "merge", "filter": {"id": "byRefId", "options": "A|B"}, "options": {}},
        {"id": "joinByField", "options": {"byField": "InterfaceID", "mode": "outerTabular"}},
        # outerTabular is a true outer join - drop catalog-only rows with no
        # real traffic before sorting, same as the Application Stats panel
        # in Network Flow Overview.
        {
            "id": "filterByValue",
            "options": {
                "filters": [{"fieldName": "TrafficVolume", "config": {"id": "isNotNull", "options": {}}}],
                "type": "include",
                "match": "all",
            },
        },
        # Flattens multi-query provenance so indexByName below actually
        # reorders columns instead of silently no-op'ing.
        {"id": "merge", "options": {}},
        {
            "id": "organize",
            "options": {
                "renameByName": {"TrafficVolume": "Traffic Volume"},
                "excludeByName": {"InterfaceID": True},
                "indexByName": {"Device": 0, "Interface": 1, "Protocol": 2, "Flows": 3, "TrafficVolume": 4},
            },
        },
        {"id": "sortBy", "options": {"fields": {}, "sort": [{"field": "Interface"}]}},
    ],
    "fieldConfig": {
        "defaults": {},
        "overrides": [
            {
                "matcher": {"id": "byName", "options": "Traffic Volume"},
                "properties": [
                    {"id": "unit", "value": "bytes"},
                    {"id": "custom.cellOptions", "value": {"type": "gauge", "mode": "basic"}},
                ],
            },
        ],
    },
    "options": {},
})

# --- Alternate visualization of the Interfaces & Protocols data: heatmap ---
# INTERFACE_CATALOG/PROTOCOL_VALUES below are the baked lists behind the
# small-multiples panels - static data baked at build time rather than a
# live "query"-type variable/target, which does not reliably populate on
# this Grafana instance.
INTERFACE_CATALOG = ENV["interface_catalog"]
PROTOCOL_VALUES = ENV["protocol_values"]

# Heatmap Table and the small-multiple donuts below both live inside one
# collapsed "Additional Views" row (built further down, after both are
# constructed), grouped together under one collapsible section.
#
# Heatmap Table - one row per interface, one column per protocol, cell =
# traffic volume, color-scaled. Uses InterfaceID (not the catalog join) as
# the "Grouping to matrix" rowField, then a Grafana value mapping (not a
# live catalog join - avoids re-adding the join this panel doesn't otherwise
# need) relabels each known ID to "<Device> <Interface>" for display, so
# e.g. "ge0/0" on 3 different devices doesn't collide into one ambiguous row.
heatmap_panel = {
    "id": 7,
    "title": "Interfaces & Protocols - Heatmap Table",
    "type": "table",
    "gridPos": {"h": 9, "w": 24, "x": 0, "y": 40},
    "datasource": DS,
    "targets": [
        csv_target("A",
            "/flowconversationmfs?$filter=" + VAR_FILTER +
            # -1 is PC's own "unknown/unresolved interface" sentinel - see
            # the matching note on the Interfaces & Protocols panel above.
            " and InInterfaceID ne -1" +
            "&$apply=groupby((InInterfaceID,Protocol),aggregate(Bytes with sum as TrafficVolume))"
            "&$orderby=TrafficVolume desc&$top=200&$format=text/csv",
            columns=[
                {"selector": "InInterfaceID", "text": "InterfaceID", "type": "number"},
                {"selector": "Protocol", "type": "string"},
                {"selector": "TrafficVolume", "type": "number"},
            ]),
        csv_target("B",
            "/flowconversationmfs?$filter=" + VAR_FILTER +
            " and OutInterfaceID ne -1" +
            "&$apply=groupby((OutInterfaceID,Protocol),aggregate(Bytes with sum as TrafficVolume))"
            "&$orderby=TrafficVolume desc&$top=200&$format=text/csv",
            columns=[
                {"selector": "OutInterfaceID", "text": "InterfaceID", "type": "number"},
                {"selector": "Protocol", "type": "string"},
                {"selector": "TrafficVolume", "type": "number"},
            ]),
    ],
    "transformations": [
        {"id": "merge", "filter": {"id": "byRefId", "options": "A|B"}, "options": {}},
        {
            "id": "filterByValue",
            "options": {
                "filters": [{"fieldName": "TrafficVolume", "config": {"id": "isNotNull", "options": {}}}],
                "type": "include",
                "match": "all",
            },
        },
        {"id": "merge", "options": {}},
        {"id": "organize", "options": {"renameByName": {"TrafficVolume": "Traffic Volume"}}},
        {
            "id": "groupingToMatrix",
            "options": {"rowField": "InterfaceID", "columnField": "Protocol", "valueField": "Traffic Volume", "emptyValue": "empty"},
        },
    ],
    "fieldConfig": {
        "defaults": {},
        "overrides": [
            {
                "matcher": {"id": "byType", "options": "number"},
                "properties": [
                    {"id": "unit", "value": "bytes"},
                    {"id": "color", "value": {"mode": "continuous-GrYlRd"}},
                    {"id": "custom.cellOptions", "value": {"type": "color-background"}},
                ],
            },
            # "Grouping to matrix"'s row-label field is NOT named after
            # rowField alone - per the transformer's own source
            # (grafana-data/src/transformations/transformers/
            # groupingToMatrix.ts), it builds a composite name
            # `${rowField}\${columnField}`, i.e. "InterfaceID\Protocol" here.
            # Matching plain "InterfaceID" matches nothing, leaving the raw
            # numeric ID displayed with no mapping/rename applied at all.
            {
                "matcher": {"id": "byName", "options": "InterfaceID\\Protocol"},
                "properties": [
                    {"id": "displayName", "value": "Interface"},
                    {
                        "id": "mappings",
                        "value": [{
                            "type": "value",
                            "options": {
                                str(iface["id"]): {"text": f"{iface['device']} {iface['name']}"}
                                for iface in INTERFACE_CATALOG
                            },
                        }],
                    },
                    # The row-label field keeps rowField's original type
                    # (number, per the transformer's own source) even though
                    # it's a label column, not a data column - without these,
                    # the byType:number override above would also apply
                    # byte-unit formatting and heatmap gradient coloring to
                    # this column, keyed off the raw interface ID's magnitude.
                    # Listed after that override, so these take precedence
                    # for this one field (later entries win per-property).
                    {"id": "unit", "value": "none"},
                    {"id": "color", "value": {"mode": "fixed", "fixedColor": "text"}},
                    {"id": "custom.cellOptions", "value": {"type": "auto"}},
                ],
            },
        ],
    },
    "options": {},
}

# Small multiples - one donut per known interface, each independently
# filtered (both the group filter AND that specific interface's own ID) so
# an interface outside the currently-selected group correctly shows empty.
# Generated as plain static panels rather than using Grafana's panel-repeat
# feature, since the full interface list is already known at build time.
#
# No bottom legend, a moderate panel size, and an explicit smaller font:
# Grafana's piechart panel has no documented setting for label placement or
# ring/donut thickness, so panel size is the only lever for how much room a
# slice's label has to render into. It does support a shared "text" options
# object (VizTextDisplayOptions - the same mechanism stat/gauge/bargauge
# panels use), with titleSize/valueSize sub-fields, per the panel builder's
# own type definitions - shrinking the label text directly is a more
# reliable way to keep labels legible than continuing to grow the chart.
donut_panels = []
for idx, iface in enumerate(INTERFACE_CATALOG):
    col = idx % 4
    row = idx // 4
    donut_panels.append({
        "id": 9 + idx,
        "title": f"{iface['device']} {iface['name']}",
        "type": "piechart",
        "gridPos": {"h": 10, "w": 6, "x": col * 6, "y": 49 + row * 10},
        "datasource": DS,
        "targets": [
            csv_target("A",
                "/flowconversationmfs?$filter=" + TIME_FILTER +
                " and (${InterfaceGroup:raw})" +
                f" and (InInterfaceID eq {iface['id']} or OutInterfaceID eq {iface['id']})" +
                "&$apply=groupby((Protocol),aggregate(Bytes with sum as TotalBytes))"
                "&$orderby=TotalBytes desc&$top=20&$format=text/csv",
                columns=[
                    {"selector": "Protocol", "type": "string"},
                    {"selector": "TotalBytes", "type": "number"},
                ]),
        ],
        "options": {
            "pieType": "donut",
            "displayLabels": ["name", "percent"],
            # A legend object with only {"displayMode": "hidden"} is
            # incomplete - piechart's schema bundles showLegend/placement/
            # calcs together, and an incomplete object can cause the panel to
            # render incorrectly rather than just hiding the legend.
            # showLegend is the actual visibility switch; displayMode/
            # placement/calcs are only consulted while visible, but are
            # included anyway to keep the object complete and valid.
            "legend": {"showLegend": False, "displayMode": "list", "placement": "bottom", "calcs": []},
            "reduceOptions": {"values": True, "calcs": []},
            # Shrinks the name+percent label text so it fits inside the
            # smaller ring - titleSize governs the "name" label, valueSize
            # the "percent" label (piechart's displayLabels).
            "text": {"titleSize": 12, "valueSize": 12},
        },
        "fieldConfig": {"defaults": {"unit": "bytes"}, "overrides": []},
    })

# One collapsed row holding both the heatmap and every donut - a Grafana row
# panel starts collapsed by setting "collapsed": true and nesting its child
# panels directly inside its own "panels" array (removed from the top-level
# list, which is how a collapsed row is actually persisted, not just a
# display flag on an otherwise-normal row).
panels.append({
    "id": 100,
    "title": "Additional Views",
    "type": "row",
    "gridPos": {"h": 1, "w": 24, "x": 0, "y": 39},
    "collapsed": True,
    "panels": [heatmap_panel] + donut_panels,
})

dashboard = {
    "dashboard": {
        "uid": ENV["top_protocols_by_interface_group_dashboard_uid"],
        "title": "Top Protocols by Interface Group",
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

print(json.dumps(dashboard, indent=2))
