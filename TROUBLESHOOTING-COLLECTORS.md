# Troubleshooting Metadata Collectors

> Split out of `README.md` on 2026-08-04. Content unchanged.
> MID Server setup, start/stop and upgrade live in `MID-SERVER.md`.

## Every collector run needs its connection pinned to a MID

**Symptom:** run fails almost immediately with *"Execution failed because no valid MID is available. Please check System Logs."*

**Cause:** the connection record (`http_connection` or `jdbc_connection` under the collector's `sys_alias`) has `mid_selection=auto_select`. Auto-select does not resolve to this MID.

**Fix** - set it explicitly on the connection record:

| Field | Value |
|---|---|
| `use_mid` | `true` |
| `mid_selection` | `specific_mid_server` |
| `mid_server` | sys_id of `mac-mid-datacatalog` |

This is exactly how the working Neon collector is configured, and it is the only configuration on this instance that has ever produced a `COMPLETED` run.

**This error is not about MID health.** Verified 2026-08-04: a MID that was `Up`, `validated`, version-matched to the instance, and heartbeating one minute earlier still produced it, on `auto_select`. Do not go re-diagnosing or restarting the MID when you see this message - check `mid_selection` on the connection first. Restarting a healthy MID because of this error is wasted work.

A genuinely stale MID produces the same message, so confirm health once using the four checks in the MID Server section, then move on to the connection.

## catalog-servicenow: `URI is not absolute`

**Symptom:** run reaches `RUNNING` / `COLLECTION_STARTED` (10%) then fails with `URI is not absolute`.

**Cause:** `http_connection.host` held a bare hostname (`demoalectriallwfzu144008.service-now.com`).

**Fix:** `host` must contain the **full URL including the scheme**:

```
host = https://demoalectriallwfzu144008.service-now.com
```

That field is not a hostname despite its name. The connector's wizard definition proves it - `sn_df_connector_section_element` for section `catalog-servicenow-configuration` defines the element `servicenow-instance-url` with `label = "ServiceNow Instance URL"`, `type = url`, and `field_name = host`. The MID passes it straight through as the collector's `instanceUrl` option, and a value with no scheme yields a relative URI.

Things that do **not** fix it (all tried): `protocol=https`, `connection_url=https://<instance>`, `url_builder`. Only `host` matters.

> Do not PATCH `host` and `connection_url` in the same REST call - doing that silently stored `host` as empty. Set `host` on its own and read it back.

## catalog-servicenow: `Error reading entity from input stream.` after ~60 min

**Symptom:** run sits at `RUNNING` / `COLLECTION_STARTED` 10% for about an hour, then `ERROR: Error reading entity from input stream.`

**It looks like a timeout and is not one.** Things ruled out on 2026-08-04:
- Not a MID death or a sleeping laptop. The MID logged a `LogStatusMonitor` line for **76 of 76 consecutive minutes** across the run, kept the same PID, and never restarted.
- Not a probe timeout. The MID returned `result_code="0"` with an empty `error_string` and `probe_time="3605975"`. The MID considered its own work successful.
- The ~60 minutes is simply how long the crawl ran before it reached the failing call.

**Actual cause:** malformed JSON from the instance's own REST API. Full chain from `agent0.log.0`:

```
CollectorException: Error reading entity from input stream.
  at ServiceNowApi.getPAVisualizationPermissions        (table: par_visualization_permission)
  at PlatformAnalyticsHarvester.collectPlatformAnalyticsMetadata
  at ServiceNowCollector.collectSystemMetadata
Caused by: JsonParseException: Unexpected character ('"' (code 34)):
           was expecting comma to separate Array entries
           at [line: 1, column: 220000]
```

The JSON is truncated because **the instance cancelled its own REST transaction mid-serialization** and appended an error object after a partial array. Reproduced directly with curl/urllib against `par_visualization_permission`:

| `sysparm_limit` | bytes | rows returned | outcome |
|---|---|---|---|
| 1000 | 280,603 | 442 of 1000 | `status: failure` - cancelled |
| 500 | 280,603 | 442 | `status: failure` - cancelled |
| 200 | 127,022 | 200 | clean |

The appended error is:

```json
{"error":{"message":"Transaction cancelled: maximum execution time exceeded"},"status":"failure"}
```

The collector deserializes the body as an array of permission objects, so when it reaches the `"error"` key it reports `expecting comma to separate Array entries`. The Jackson message is a symptom; the transaction cancellation is the cause.

**Enforced by:** quota rule **"REST Table API request timeout"** (`sysrule_quota`, sys_id `55841f53ff2102003434ffffffffff39`), condition `type=rest^urlMATCH_RGX.*/api/now(/v[0-9]+)?/table.*`, originally `max_duration = 60` seconds. `par_visualization_permission` is slow enough on this instance that a 1000-row page exceeds 60s. `ServiceNowApi.DEFAULT_API_PAGE_SIZE = 1000`, so the collector trips it every run.

**Fix applied:** raised that rule's `max_duration` from `60` to `600`.

> This is instance-wide - every inbound Table API request now gets up to 600s before cancellation. Acceptable on a demo instance; reconsider before promoting anywhere shared. Revert by setting `max_duration` back to `60` on that sys_id.

**Alternative if you don't want the quota change:** lower the collector's page size. The option exists (`ServiceNowCollectorConfig.ServiceNowApiPageSizeOption`), but this instance exposes no wizard element or connection attribute for it - the connector defines only `servicenow-instance-url`, `servicenow-username`, `servicenow-password`, `use_mid`. Supplying it would need a new `sn_df_connector_section_element`, or a populated `data_template_json` on section `catalog-servicenow-configuration` (currently empty).

**Expect the run to take about an hour** before it reaches the Platform Analytics stage, so allow time when re-testing.

## catalog-servicenow: `413` on the results attachment - RESOLVED

> **Resolved 2026-08-04.** Raising `com.glide.attachment.max_size` from `1024` to `2048` and the **"REST Attachment API request timeout"** quota rule (`sysrule_quota` sys_id `f17b97d2ff2102003434ffffffffff52`) from `60` to `600` cleared this. Run `664eb9303bae8f9443dfe524c3e45a33` reached `COMPLETED` / 100%: `12:56:30 -> 19:45:44` (**6h49m**), attachment **2015.3 MB** - 32 MB under the new 2048 MB ceiling. Collection itself took ~1h09m (attachment written 14:05); the remaining ~5h40m was graph projection/ingestion.
>
> Result: **20,768** `sn_dcg_cc_sn_table`, **621,579** `sn_dcg_cc_sn_field`, 1,075 views, 2,228 application scopes, 156 `cmdb*` tables, all with `iri` and `class_iri` populated.
>
> `skip-glide` was never needed, and remains unreachable (see below). The history below is kept because the margin is thin - 2015 MB against a 2048 MB limit - so any growth in the instance's dictionary will hit this again.

### Original diagnosis

With the quota rule at `600`, the crawl **completes**. Run `eb0aa57c3ba64f10e0abdda693e45aa7` on 2026-08-04 ran `11:28:09 -> 12:39:46` (71.5 min) with **zero** collector-thread errors, then failed on upload:

```
Error creating Attachment catalog-servicenow-results.nt :
Method failed: (/api/now/v1/attachment/file) with code: 413
with reason: Attachment's size is greater than the maximum allowed by the system
```

So collection works; publishing the result does not. The collector streams its whole RDF graph back as one N-Triples attachment on `sn_dcg_core_execution_run`.

- `com.glide.attachment.max_size` = `1024` (MB)
- for scale, the working Neon collector's `catalog-postgres-results.nt` is **17.2 MB**
- no `catalog-servicenow-results.nt` exists in `sys_attachment` - nothing partial lands

The whole-instance ServiceNow graph therefore exceeds 1 GB, roughly 60x Neon's output. This is the direct consequence of the connector having **no table selection**: it harvests every scope, app, table, field and view (`harvestScopes` -> `harvestApps` -> `harvestTables` -> `harvestFields`), and never asks what you want.

### `skip-glide` is the intended lever, and is not settable on this instance

The collector declares the option in its own ontology (`servicenow-collector-ontology-individuals.ttl` inside `kos-collectors-servicenow-*.jar`):

```
servicenow-collector-options:ServiceNowSkipGlideOption a kos-collectors:CollectorConfigOption ;
    kos-collectors:optionIdentifier "skip-glide" ;
    kos-collectors:optionTitle "Skip Glide Tables, Fields, and Views" ;
    kos-collectors:hasType kos-collectors:BOOLEAN_TYPE ;
```

Setting it would drop base-platform tables to stubs and shrink the graph. Every route tried on 2026-08-04 is blocked:

| Route | Result |
|---|---|
| Wizard element | none exists - `catalog-servicenow` defines only `servicenow-instance-url`, `servicenow-username`, `servicenow-password`, `use_mid` |
| `sn_df_connector_section.data_template_json` on `catalog-servicenow-configuration` | **403** `ACL Exception Update Failed due to security constraints` - the table is ACL-locked, scope `sn_dcg_cc`, even for `admin` |
| Connection attribute (how Neon carries `all-schemas=true`) | needs a new `sys_dictionary` element on a `var__m_connection_attributes_*` table plus a `sys_variable_value` row - schema surgery on a Store app, not attempted |

For reference, the connection-attribute mechanism other connectors use is: a `sn_df_connector_section_element` with `field_name='connection_attribute'` and `name='<optionIdentifier>'` (e.g. `all-schemas`, `exclude-schema`, `include-information-schema`), whose value is stored in `sys_variable_value` against the connection and passed by the MID as a collector option.

**Net position:** `catalog-servicenow` collects successfully but cannot publish on this instance, and the one option that would make the payload small enough is not reachable without modifying Store app metadata. Raising `com.glide.attachment.max_size` alone is unlikely to help - the `REST Attachment API request timeout` quota rule is `60s`, so a >1 GB upload would then hit that instead.

## How to find the real cause of any collector failure

The run record's `error_message` is a summary. The MID log carries the actual stack trace:

```bash
grep -n "URI is not absolute" mid-server/agent/logs/agent0.log.0   # then sed -n '<line-20>,<line+90>p'
```

That trace is what identified `ServiceNowApi.getApplicationScopes` as the failing call. **Do not query `sys_log` / `syslog` on this instance - it freezes it.**

Two other useful sources:
- `sn_df_connector_section` / `sn_df_connector_section_element`, filtered by the connector sys_id, give the authoritative field mapping for any connector (which connection field each wizard input writes to).
- The collector's own config class lists the options it expects. For ServiceNow: `instanceUrl`, `username`, `password`, `apiPageSize`, `skipGlide`, from `ServiceNowCollectorConfig` inside `kos-collectors-servicenow-*.jar` (nested in `extlib/kos-bundle-a.jar`). Inspect with `javap -p -c -constants`; macOS `strings` cannot read `.class` files.
