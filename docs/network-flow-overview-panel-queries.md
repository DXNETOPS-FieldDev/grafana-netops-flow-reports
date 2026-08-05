# Network Flow Overview — Panel Queries

Reference list of the OData4 query each panel in the **Network Flow Overview** dashboard runs
against DX NetOps Performance Center's flow entity (`flowconversationmfs`). All queries run live —
no caching or middle-tier service in between.

## Common filter

Every panel applies this same filter, driven by the dashboard's time range and its three dropdown
variables (Protocol, Talkers, destination):

```
Timestamp ge <range start> and Timestamp le <range end>
  and Protocol in (<selected protocols>)
  and SourceIP in (<selected source IPs>)
  and DestinationIP in (<selected destination IPs>)
```

## 1. Traffic Distribution (Protocol)

Donut chart — share of total bytes by protocol.

```
/flowconversationmfs?$filter=<common filter>
  &$apply=groupby((Protocol),aggregate(Bytes with sum as TotalBytes))
  &$orderby=TotalBytes desc&$top=20
```

## 2. Top Talkers

Bar gauge — top 15 source IPs ranked by bytes sent.

```
/flowconversationmfs?$filter=<common filter>
  &$apply=groupby((SourceIP),aggregate(Bytes with sum as TotalBytes))
  &$orderby=TotalBytes desc&$top=15
```

## 3. Total BW Usage

Stacked area chart — bandwidth utilization in/out over time.

```
/flowconversationmfs?$filter=<common filter>
  &$apply=groupby((Timestamp),aggregate(
      BandwidthUtilIn with sum as BandwidthIn,
      BandwidthUtilOut with sum as BandwidthOut))
  &$orderby=Timestamp asc&$top=2000
```

## 4. Traffic by Protocol

Stacked area chart — one series per protocol, traffic volume over time.

```
/flowconversationmfs?$filter=<common filter>
  &$apply=groupby((Timestamp,Protocol),aggregate(Bytes with sum as TotalBytes))
  &$orderby=Timestamp asc&$top=20000
```

## 5. Traffic by Application

Stacked area chart — one series per destination port, traffic volume over time.

```
/flowconversationmfs?$filter=<common filter>
  &$apply=groupby((Timestamp,DestinationPort),aggregate(Bytes with sum as TotalBytes))
  &$orderby=Timestamp asc&$top=20000
```

## 6. Application Traffic Stats

Table — top 20 applications by traffic volume. Application names aren't a single field on this
entity, so this panel combines three queries (two aggregates + a name catalog), joined and
coalesced client-side in Grafana:

**Query A** — apps classified via an explicit override (name already on the row):
```
/flowconversationmfs?$filter=<common filter> and UserDefinedOverride eq true
  &$apply=groupby((UserDefinedAppName,DestinationPort),aggregate(
      Bytes with sum as TrafficVolume, FlowCount with sum as Flows))
  &$orderby=TrafficVolume desc&$top=20
```

**Query B** — apps classified via NBAR (name resolved via a catalog join):
```
/flowconversationmfs?$filter=<common filter> and UserDefinedOverride eq false
  &$apply=groupby((ApplicationID,DestinationPort),aggregate(
      Bytes with sum as TrafficVolume, FlowCount with sum as Flows))
  &$orderby=TrafficVolume desc&$top=20
```

**Query C** — application name catalog, used to resolve names for Query B:
```
/flowapplications?$select=ID,Name&$top=2000
```

A and B are merged, then joined against C by `ApplicationID` to resolve the application name,
then sorted by traffic volume and trimmed to the top 20.
