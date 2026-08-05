# Top Protocols by Interface Group — Panel Queries

Reference list of the OData4 query each panel in the **Top Protocols by Interface Group**
dashboard runs against `flowconversationmfs`. All queries run live — no caching or middle-tier
service in between.

## Common filter

```
Timestamp ge <range start> and Timestamp le <range end>
  and (<selected Interface Group's clause>)
```

The "Interface Group" dropdown's option value is a pre-resolved OData boolean expression for that
group, e.g. `InInterfaceID eq 13723 or InInterfaceID eq 13724 or ... or OutInterfaceID eq 15024`
(a group with no flow-collecting interfaces resolves to `InInterfaceID eq 0`, which never
matches). See the main README's Grafana/Infinity integration notes for why this is expressed as a
boolean clause rather than a comma-joined ID list, and why `flowconversationmfs`'s `groups`
navigation property cannot be filtered directly.

Panels 1–3 also carry a data link ("View Conversations for this Protocol") that, on click, sets
the `Protocol` variable to a clause built from the clicked row (`Protocol eq '<clicked value>'`)
and reloads the dashboard, landing on panel 4, "Conversations by Host".

## 1. Traffic Distribution by Protocol

Donut chart — share of total bytes by protocol.

```
/flowconversationmfs?$filter=<common filter>
  &$apply=groupby((Protocol),aggregate(Bytes with sum as TotalBytes))
  &$orderby=TotalBytes desc&$top=20
```

## 2. Top Protocols by Flow Count

Bar gauge — top 10 protocols ranked by flow count.

```
/flowconversationmfs?$filter=<common filter>
  &$apply=groupby((Protocol),aggregate(FlowCount with sum as TotalFlows))
  &$orderby=TotalFlows desc&$top=10
```

## 3. Top Protocols by Traffic Volume

Bar gauge — top 10 protocols ranked by bytes.

```
/flowconversationmfs?$filter=<common filter>
  &$apply=groupby((Protocol),aggregate(Bytes with sum as TotalBytes))
  &$orderby=TotalBytes desc&$top=10
```

## 4. Conversations by Host

Table — source/destination IP conversations, the drill-down target from panels 1–3. Filtered by
the Interface Group and the `Protocol` variable (defaults to "All", via an always-true
`Bytes ge 0` clause):

```
/flowconversationmfs?$filter=<common filter> and (<Protocol variable's clause>)
  &$apply=groupby((SourceIP,DestinationIP),aggregate(
      Bytes with sum as TrafficVolume, FlowCount with sum as Flows))
  &$orderby=TrafficVolume desc&$top=100
```

No hostname resolution exists in this OData schema — "host" refers to the raw IP address.

## 5. Protocol Traffic Over Time

Stacked area chart — one series per protocol, traffic volume over time. Also scoped by the
`Protocol` variable, so a drill-down click narrows this panel along with Conversations by Host.

```
/flowconversationmfs?$filter=<common filter> and (<Protocol variable's clause>)
  &$apply=groupby((Timestamp,Protocol),aggregate(Bytes with sum as TotalBytes))
  &$orderby=Timestamp asc&$top=20000
```

## 6. Interfaces & Protocols

Table — every (interface, protocol) combination seen within the selected group, with device and
interface name, traffic volume, and flow count. A flow record carries two interface fields
(`InInterfaceID`/`OutInterfaceID`), so a per-interface breakdown requires the union of both
directions. Also scoped by the `Protocol` variable.

**Query A** — protocols per ingress interface:
```
/flowconversationmfs?$filter=<common filter> and (<Protocol variable's clause>) and InInterfaceID ne -1
  &$apply=groupby((InInterfaceID,Protocol),aggregate(
      Bytes with sum as TrafficVolume, FlowCount with sum as Flows))
  &$orderby=TrafficVolume desc&$top=200
```

**Query B** — protocols per egress interface (same shape, other field):
```
/flowconversationmfs?$filter=<common filter> and (<Protocol variable's clause>) and OutInterfaceID ne -1
  &$apply=groupby((OutInterfaceID,Protocol),aggregate(
      Bytes with sum as TrafficVolume, FlowCount with sum as Flows))
  &$orderby=TrafficVolume desc&$top=200
```

**Query C** — interface name catalog, with device name expanded inline:
```
/flowinboundinterfaces?$expand=flowdevice($select=Name)&$select=ID,Name&$top=100&$format=json
```

`-1` (PC's sentinel for an unresolved interface) is excluded explicitly, since it can otherwise
appear as a meaningless row. A and B are stacked, then joined against C to resolve device and
interface names, with unmatched catalog-only rows dropped before sorting. No deduplication is
applied beyond that — an interface can be an ingress point for some flows and an egress point for
others carrying the same protocol, so the same (interface, protocol) pair may legitimately appear
as two rows.

## 7. Interfaces & Protocols — Heatmap Table

Same underlying data as panel 6 (minus `Flows`, and without the interface-name catalog join):

```
/flowconversationmfs?$filter=<common filter> and InInterfaceID ne -1
  &$apply=groupby((InInterfaceID,Protocol),aggregate(Bytes with sum as TrafficVolume))
  &$orderby=TrafficVolume desc&$top=200
```
(and the equivalent query for `OutInterfaceID`). The combined result is pivoted (Grafana's
"Grouping to matrix" transform: row field `InterfaceID`, column field `Protocol`, value field
`Traffic Volume`) into one row per interface and one column per protocol, color-scaled by value.
Row labels are the raw `InterfaceID`, relabeled for display via a Grafana value mapping
(`<id>: "<device> <name>"` per known interface) to disambiguate identical interface names (e.g.
`ge0/0`) across different devices.

## 8–17. Per-interface protocol donuts

One donut per known interface, each independently filtered by both the selected Interface Group
and that interface's own ID, so an interface outside the current group correctly shows no data:

```
/flowconversationmfs?$filter=<common filter> and (InInterfaceID eq <id> or OutInterfaceID eq <id>)
  &$apply=groupby((Protocol),aggregate(Bytes with sum as TotalBytes))
  &$orderby=TotalBytes desc&$top=20
```
