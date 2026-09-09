# OData4 API Notes

Technical characteristics of PC's OData4 API relevant to building queries against it, confirmed
against PC 25.4.9. For the entity/field reference (what `flowconversationmfs` and its related
catalogs actually contain), see [odata4-flow-notes.md](odata4-flow-notes.md).

**`$top` is mandatory on every query.** DA's OData4 limiter defaults to 50 rows when `$top` is
omitted, and clamps any requested value to a hard ceiling of 20,000
(`com.ca.im.odata.beans.ODataLimiters.cfg` on the DA host: `defaultTopLimit=50`,
`maxTopLimit=20000`). There is no working pagination: these queries do not return
`@odata.nextLink`, so once a response is truncated there is no way to retrieve the remainder.
Queries whose row count scales with an additional `groupby` dimension (e.g.
`groupby((Timestamp,<dimension>))`, where row count is distinct timestamps × distinct dimension
values) should default to `$top=20000` rather than an estimated "safe" value — with
`$orderby=Timestamp asc`, truncation silently drops the most recent data rather than the oldest,
which can be easy to miss since the panel still renders, just with a shorter time range than
requested.

**`$apply` and `$expand` do not compose.** A friendly name cannot be resolved inline on an
aggregated query. Fetch the aggregate and the lookup/catalog collection as separate targets and
join them client-side in Grafana.

**`$apply=compute(...)` is not implemented** on this PC instance, including plain arithmetic
expressions, not only conditional (`case()`) expressions. There is no way to compute a derived
column (e.g. a per-second rate) server-side; this requires either accepting a raw cumulative value
or introducing a middle-tier service.

**`ApplicationID` is not a reliable identifier on its own.** `flowconversationmfs` also carries
`UserDefinedAppName` and `UserDefinedOverride`. When `UserDefinedOverride` is true, the flow was
classified by a port-based override rather than NBAR, and the real application name is in
`UserDefinedAppName`, not the `flowapplications` catalog. `ApplicationID` is also not 1:1 with an
application when overrides are involved. A reliable display name requires a coalesce:
`UserDefinedAppName` when `UserDefinedOverride` is true, otherwise the `flowapplications` catalog
name (joined on `ApplicationID`), otherwise "Unclassified." Because `$apply=compute(...)` is
unavailable, this coalesce is implemented as two independent query branches, stacked and resolved
client-side — see `scripts/build_flow_overview_dashboard.py`'s "Application Traffic Stats" panel.

**A flow's interface fields are directional, not a single "the interface."** Each record carries
`InInterfaceID` (ingress) and `OutInterfaceID` (egress) separately. A per-interface breakdown
requires the union of both fields, not either alone.

**`-1` is a reserved sentinel value**, used by PC to represent an unknown or unresolved value
(e.g. `InInterfaceID=-1`, `ApplicationID=-1_0_-1`) on records that otherwise carry real traffic.
Sentinel values should be excluded explicitly (e.g. `and InInterfaceID ne -1`) rather than assumed
to be absent, and should not be reused as a stand-in for "no data" in application logic, since they
can appear on legitimate rows.

**Flow history is capped to approximately one hour by default**, independent of the requested time
range or `$top`. This is a DA-side OData4 exposure limit for "rate" (raw, non-rolled-up)
granularity data — `flowconversationmfs` has no coarser rollup entity, so it is always subject to
the tightest tier. The relevant setting is `defaultRateTimeIntervalSecs` in
`com.ca.im.odata.beans.ODataLimiters.cfg` (mirrored in `OData4Properties.cfg`) on the DA host,
default `3600` (seconds). This is a global limiter affecting all "rate"-granularity OData4 queries
on the instance, not flow data specifically. Increasing it (DA hot-reloads `.cfg` file changes, no
restart required) extends the effective history window; raising it to `86400` (24 hours) has been
validated to work. Persistence of this configuration across a DA upgrade or redeploy is not
guaranteed.

**Interface Groups** are modeled by PC's generic `groups` entity (`GroupType=automatic`, under a
parent group named "Interface Groups"). `flowconversationmfs`'s own `groups` navigation property
cannot be filtered directly — `$filter=groups/any(...)` returns an empty result rather than an
error, rather than a supported query. The reliable approach is to resolve each group's member
interfaces once via `groups(<id>)?$expand=flowinboundinterfaces,flowoutboundinterfaces`, then
filter flow queries on the scalar `InInterfaceID`/`OutInterfaceID` fields directly.

**No hostname resolution exists in this schema.** There is no reverse-DNS or hostname entity;
"host" in any conversation-level view refers to the raw `SourceIP`/`DestinationIP`.

## Known limitations

- No per-second rate metrics — PC's OData4 `compute()` is unavailable, and computing a rate
  requires either a raw cumulative value or a middle-tier service.
- No hostname resolution for conversation-level views; only raw IP addresses are available.
- Toggling a protocol filter off by clicking the same value again is not supported — Grafana Data
  Links are static per-click templates with no way to detect the currently selected value. A
  separate "Clear Protocol Filter" reset control is provided instead.
- Grafana's Pie Chart panel does not expose configuration for donut ring thickness or for
  controlling whether a slice's label renders inside or outside its colored region; panel sizing
  and label text size are the only available levers.
- The `defaultRateTimeIntervalSecs` DA configuration change that extends flow history retention is
  a direct configuration file edit, not applied through a documented configuration-management
  path, and its persistence across a DA upgrade or redeploy has not been verified.
