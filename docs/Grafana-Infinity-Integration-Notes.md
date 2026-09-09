# Grafana/Infinity Integration Notes

Implementation patterns and constraints encountered building these dashboards with the
[Infinity data source plugin](https://grafana.com/grafana/plugins/yesoreyeram-infinity-datasource/),
documented so they do not need to be rediscovered when extending this project. See
[OData4-API-Notes.md](OData4-API-Notes.md) for the PC-side query constraints these patterns work
around.

**`joinByField` mode matters.** Use `mode: "outerTabular"` when joining table data on a
string/categorical field. `mode: "outer"` is designed for aligning time series on a shared time
field and silently fails to correlate table joins by value. `outerTabular` performs a true outer
join — joining a small aggregate against a larger catalog will pad in catalog-only rows with no
real data, which can surface later if a `limit` step needs more rows than the real result set
provides. Filter these out with `filterByValue` (`isNotNull` on the aggregated metric field)
before sorting or limiting.

**Keep join/merge steps to two frames at a time.** When combining more than two query results,
merge two of them first (scoped with a `filter: {id: "byRefId", options: "A|B"}` on the merge
transform) before joining the result against a third.

**When a target uses an explicit `columns` array, also set `"parser": "backend"`** on that target
— without it, column overrides are silently ignored and the resulting frame is empty.

**Multi-value filter variables map onto OData4's `in` operator** using Grafana's `:singlequote`
format modifier to produce a quoted, comma-separated list, e.g. `Protocol in
(${Protocol:singlequote})`.

**Long-format aggregation results can be pivoted into multi-series time series** by combining
`$apply=groupby((Timestamp,<dimension>),aggregate(...))` with an Infinity target format of
`"timeseries"` (not `"table"`) — this produces one labeled field per distinct dimension value with
no manual reshaping required.

**Grafana's `custom` variable type derives its runtime value entirely from its `query` string**,
not from the `options`/`current` fields in the underlying JSON — those are not authoritative and
can be silently discarded. A variable whose display label differs from its underlying value must
encode that distinction directly in `query`, using Grafana's `text : value` pair syntax
(`text1 : value1,text2 : value2`). Because the pair separator is also a comma, values used this
way must not themselves contain commas; where a value would otherwise need to be a comma-joined
list (e.g. a set of interface IDs), express it instead as a boolean clause using `eq`/`or` chains
that need no `in (...)` list.

**Single-value-style panels (bar gauge, pie chart, stat, gauge) default to reducing an entire
column to one value.** Set `reduceOptions: {values: true, calcs: []}` to render one bar, slice, or
value per row instead.

**Field display-name templating uses `${__field.labels.LabelName}`**, not mustache-style
`{{LabelName}}` syntax, which is treated as a literal string rather than a template.

**`organize`'s `indexByName` (column reordering) does not reliably apply to a frame derived from
multiple queries.** Insert a no-op `merge` transform (no filter, single input) immediately before
`organize` to flatten the frame's multi-query provenance first. `indexByName`/`excludeByName` also
key off a field's pre-rename name, even when specified in the same `organize` step as
`renameByName`.

**The "Sort by" transform sorts on a single field**, not a multi-key sort; a second entry in its
`sort` array is not a documented or reliable secondary key.

**An unfiltered transform step applies to every frame currently in the pipeline**, not only the
frame it is conceptually intended for. A transform without a `filter` scoping it to specific
`refId`s will also run against unrelated frames (e.g. a lookup catalog) still present at that
point in the pipeline, which can silently corrupt or empty frames that lack the fields the
transform expects.

**The "Grouping to matrix" transform's row-label output field is a composite name**,
`` `${rowField}\${columnField}` `` (e.g. `` InterfaceID\Protocol ``), not the `rowField` name
alone — field-config matchers targeting the pivoted row label must use this composite name. That
field also retains `rowField`'s original data type, which means a `byType` matcher intended only
for the pivoted value columns may also apply to the row-label column and needs to be explicitly
overridden.

**Grafana Data Links** support drill-down navigation by embedding a clicked row's sibling field
value into a target URL, using `${__data.fields["FieldName"]}` (bracket, quoted-name form). The
current value of another dashboard variable can be embedded as a properly formatted query
parameter using the `:queryparam` format modifier, which already includes the `var-<name>=`
prefix. Anchor-to-panel navigation within the same dashboard is not reliably supported in current
Grafana versions; positioning a drill-down target panel near the top of the dashboard is a more
reliable way to keep it in view after a navigation reload.

**Raw HTML anchors in Text panels should use fully-qualified absolute URLs**, not relative paths —
a relative href can resolve incorrectly and navigate to the Grafana root instead of the intended
dashboard. This differs from Grafana Data Links, which resolve internal dashboard references
correctly on their own.

**Markdown-mode Text panels may fail to render markdown link syntax
(`[text](url)`) as a clickable link when the URL contains template variables**, even though the
variable substitution itself succeeds — resulting in the raw markdown syntax being displayed as
literal text. Use `"mode": "html"` with a raw `<a href="...">` element instead.

**A Grafana row only starts collapsed if its child panels are nested inside the row's own `panels`
array**, removed from the dashboard's top-level panel list. Setting `"collapsed": true` alone on
an otherwise flat row has no effect.
