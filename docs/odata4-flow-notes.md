# PC OData4 — Network Flow Entity Reference

Data model reference for the OData4 entities backing the Network Flow dashboards, based on DX
NetOps Performance Center 25.4.9. Use the real v4 endpoint (`/pc/odata4/api/`) — the legacy v2
alias (`/pc/odata/api/`) does not expose these entities.

For operational query constraints and Grafana integration patterns (e.g. `$top` requirements,
`$apply`/`$expand` limitations, the flow history cap), see the main [README](../README.md).

## Entities

- **`flowconversationmfs`** — the flow/conversation metrics face. Fields: `ID`, `Timestamp`
  (epoch seconds), `Resolution` (seconds), `DeviceItemID`, `SourceIP`, `SourcePort`,
  `DestinationIP`, `DestinationPort`, `Protocol`, `InInterfaceID`, `OutInterfaceID`,
  `BandwidthUtilIn`, `BandwidthUtilOut`, `Bytes`, `FlowCount`, `SourceAS`, `DestinationAS`,
  `TypeOfService`, `NextHopAddress`, `ApplicationID`, `UserDefinedAppName`, `UserDefinedOverride`,
  `LastUpdateDate`. Navigable via `$expand`: `flowdevice`, `flowinboundinterface`,
  `flowoutboundinterface`, `flowapplication`, `groups`.
- **`flowapplications`** — NBAR application/protocol classification catalog. Fields: `ID`
  (composite, e.g. `-1_13_335`), `Name`, `Description`, `SourceType`, `LastUpdateDate`. Not every
  `ApplicationID` value seen in `flowconversationmfs` has a matching catalog row.
- **`flowdevices`** — flow-collecting devices. Standard device inventory fields (`Name`,
  `PrimaryIPAddress`, `Latitude`/`Longitude`, etc.).
- **`flowinboundinterfaces`** / **`flowoutboundinterfaces`** — flow-enabled interface catalog.
  Fields: `ID`, `Name`, `DeviceItemID`. `$expand=flowdevice($select=Name)` resolves the owning
  device's name inline.

## Application name resolution

`ApplicationID` alone is not a reliable identifier — see the README's OData4 API notes for why,
and for the coalesce pattern (`UserDefinedAppName` when `UserDefinedOverride` is true, otherwise
the `flowapplications` catalog name, otherwise "Unclassified"). The implementation is in
`scripts/build_flow_overview_dashboard.py`'s "Application Traffic Stats" panel.

## Query patterns

Aggregation (top talkers, top applications, top interfaces) — must be time-bounded:

```
/flowconversationmfs?$filter=Timestamp ge <epoch> and Timestamp le <epoch>
  &$apply=groupby((SourceIP,DestinationIP),aggregate(Bytes with sum as TotalBytes))
  &$orderby=TotalBytes desc&$top=10&$format=text/csv
```

Time series (flow volume over time):

```
/flowconversationmfs?$filter=Timestamp ge <epoch> and Timestamp le <epoch>
  &$apply=groupby((Timestamp),aggregate(Bytes with sum as TotalBytes))
  &$orderby=Timestamp asc&$top=2000&$format=text/csv
```

Name-lookup catalogs — no `$apply` needed, but `$top` must still be set explicitly:

```
/flowapplications?$select=ID,Name&$top=2000&$format=text/csv
/flowoutboundinterfaces?$expand=flowdevice($select=Name)&$select=ID,Name&$top=100&$format=json
```

## Flow history retention

`flowconversationmfs` is backed by NetOps Flow's Kafka/Kubernetes pipeline, with its own
retention-managed store separate from PC's classic polled-metrics repository. In addition to that
retention window, DA's OData4 layer applies its own exposure limit for raw ("rate" granularity)
data, configured via `defaultRateTimeIntervalSecs` in
`/opt/IMDataAggregator/config/com.ca.im.odata.beans.ODataLimiters.cfg` (mirrored in
`OData4Properties.cfg` in the same directory), default `3600` seconds (one hour). This value can
be increased to extend the effective query window; DA hot-reloads `.cfg` file changes without a
restart. This is a global setting affecting all raw-granularity OData4 queries on the instance, not
flow data specifically, and any change should be applied through your organization's standard
configuration-management process where one exists.

## Authentication

The Infinity datasource authenticates to PC using HTTP Basic or Bearer authentication
(`WWW-Authenticate: Basic realm="OpenAPI"` / `Bearer realm="OpenAPI"`). A dedicated service account
is recommended over a personal account for any datasource used beyond initial prototyping.
