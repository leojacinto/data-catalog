# Local Catalog: ServiceNow CMDB

Cataloging data that already lives inside the ServiceNow instance itself (CMDB). This document is scoped to CMDB only.

## Method

Catalog CMDB with the **native ServiceNow metadata collector** in Connect Hub, pointed at the instance's own URL. This is the only supported path. A collector run registers each asset in the catalog knowledge graph - it populates `iri`/`class_iri`, which is what the Data Catalog detail views, semantic search, and the Data Product "Add assets" picker all read from. Direct Table API inserts into `sn_dcg_cc_kos_*` render in list/detail views but never get an `iri`, so they are invisible to every graph-backed surface. Do not use Table API inserts for this.

## Prerequisites

- **A working MID Server.** The collector runs its collection through a MID, even when the instance catalogs its own tables. Confirm the MID is Up/validated first - a broken MID leaves the collector stuck at status `NEW`.
- **Roles on the running user** (all present on `admin` here): `df_data_steward` (create/manage data interfaces), `data_product_admin` (create/publish data products), `data_product_user` (read consumer access).
- **No zero-copy connector needed.** That is only for external sources (Snowflake, Databricks, Oracle). CMDB is native.

## Set up the collector (Connect Hub)

**All > Connect Hub > Create metadata collector**, System = **ServiceNow**, Connection type = **New connection**:

- Connection name, e.g. `ServiceNow Self`
- ServiceNow Instance URL = this instance's URL
- Authentication = username + password (basic auth)

Saving creates the standard record chain:

| Record | Table | Purpose |
|---|---|---|
| Connection & Credential Alias | `sys_alias` | ties the connection and credential together |
| HTTP Connection | `http_connection` | instance host + `https` |
| Credential | `basic_auth_credentials` | username + encrypted password |
| Metadata Collector | `sys_wdf_metadata_collector` | links the `catalog-servicenow` connector to the alias |

## Run and verify

1. On the collector, run **Connect & verify**. If it stays `NEW`, the MID is not healthy - fix that first. **Unverified beyond that:** we never exercised this button - every run in this repo was triggered directly over REST (`schedule_now`), bypassing it entirely. What it does to `collector_status` and whether it creates a scheduled job is not something we've tested. Do not assume a scheduled job appears on success - checked 2026-08-05 across all 4 collectors on this instance, only one (`Neon`, the one run manually through the UI early on) has `scheduled_job` populated; our REST-triggered ServiceNow collector is `CONNECTED` with no scheduled job at all despite a `COMPLETED` run.
2. Run a collection. Watch `sn_dcg_core_execution_run`: a good run ends `COMPLETED`; failures record an `error_message` there.
3. Confirm the assets - CMDB tables land in `sn_dcg_cc_sn_table` (technical name in `table_name`, not `name`), each with a populated `iri` (this is what distinguishes a real collector asset from a flat insert):

```
curl -u admin:<password> "https://<instance>.service-now.com/api/now/table/sn_dcg_cc_sn_table?sysparm_query=table_name=cmdb_ci_server&sysparm_fields=table_name,name,iri"
```

There is no table selection to configure. Verified 2026-08-05: the `catalog-servicenow` connector's wizard has exactly 4 fields - instance URL, username, password, and a hidden `use_mid` - no schema/table/scope filter of any kind. Unlike `catalog-oracle` or `catalog-databricks`, which do expose "schemas to collect," this connector harvests every application scope, table, field and view on the instance unconditionally (confirmed: 20,768 tables / 621,579 fields on one run). `cmdb_ci_appl`, `cmdb_ci_service`, etc. arrive automatically - there is nothing to add them to.

## Create a Data Interface, then a Data Product

Order matters: the Data Product "Add assets" step only lists **published Data Interfaces**, so build the interface first.

### Data Interface on `cmdb_ci`

1. **All > Workflow Data Fabric > Data Workbench**
2. **Create > Create data interface**
3. Basic details: interface label (e.g. `Configuration Items`), confirm application scope, **Continue**
4. Select source tables: **Add**, find `cmdb_ci` in the Data Catalog, add it, **Continue** (single table -> no join/union step)
5. Select columns: pick only what consumers need, **Continue**
6. Review the target column mapping, adjust labels/types, **Create table** (creates the Data Fabric table)
7. **Connect and verify** the source connection -> expect **Verified**
8. **Preview** the top rows to confirm the data
9. Review permissions, **Continue**. For a native table the wizard does not auto-assign read roles - a security admin adds them to the composite role (an email template is generated for this).
10. Review and finalize, **Done**

### Data Product

1. **Data Workbench > Create > Create data product**
2. Basic details: name, description, optional tags, **Continue**
3. **Add assets** -> select the `Configuration Items` interface, **Continue**
4. Review inherited permissions (set access on the interface, not here), **Continue**
5. Review, **Done** - created in **draft**
6. **Publish** to make it visible to consumers in the Data Catalog

## Optional enrichment on the collected assets

Applied by PATCH to the collector-produced table assets (`sn_dcg_cc_kos_database_table/{sys_id}`):

- **Owner / Steward** -> `admin`
- **Lifecycle status** -> `Approved` (resolves to an `sn_dcg_core_lifecycle_status` record)
- **Tags** -> create with `POST /api/sn_dcg_core/v1/catalog/tag` (new sys_id is at `result._meta.sysId`), then set the `tags` field
- **Glossary terms** -> create in `sn_dcg_core_glossary_term`; link to assets via the UI's Related Assets editor (no relationship predicate for term links exists on this instance)
