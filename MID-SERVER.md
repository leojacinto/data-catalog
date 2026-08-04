# MID Server

> Split out of `README.md` on 2026-08-04. Content unchanged.

The `mid-server/` directory is gitignored. To set up:
1. Download the MID Server zip from your SN instance (`mid_server_download_ui.do`)
2. Extract to `mid-server/`
3. Edit `mid-server/agent/config.xml` and set `url`, `mid.instance.username`, `mid.instance.password`
4. Start: `bash mid-server/agent/start-macos.sh`

## This install is non-standard - read before touching it

The local MID is the **Linux** distribution running on macOS/Apple Silicon under a Homebrew JDK, launched by a custom single-JVM script. There is no Tanuki wrapper (`ecc_agent.wrapper_name` reads `N/A (running in IDE)`). Consequences:

- `start.sh` / `stop.sh` (the shipped scripts) **do not work**. Use `start-macos.sh`, or `start-macos-loop.sh` for a relaunch-on-exit loop.
- The MID cannot self-restart, so it cannot apply an auto-upgrade. Auto-upgrade is therefore disabled in `config.xml`:
  ```xml
  <parameter name="glide.mid.autoupgrade.enabled" value="false"/>
  ```
  Leave that in. Without it the MID boots, enters upgrade, fails, and loops - never connecting, so its heartbeat goes stale and every collector run fails with *"no valid MID is available"*.
- ServiceNow's bundled JRE is unused (`Jre version: null`), which matters for upgrades - see below.

## Start / stop / verify

```bash
cd mid-server/agent

# stop (loop wrapper first, or it relaunches the JVM you just killed)
pkill -f start-macos-loop.sh; pkill -f service_now.mid.Main

# start
nohup bash ./start-macos-loop.sh > logs/restart-$(date +%H%M).out 2>&1 &

# verify locally: one JVM, and recent HeartbeatProbe lines
pgrep -f service_now.mid.Main
grep HeartbeatProbe logs/agent0.log.0 | tail -2
```

Verify **server-side** - local process alive is not the same as the instance trusting it:

```bash
python3 - <<'PY'
import base64, json, urllib.request
E=dict(l.strip().split('=',1) for l in open('.env') if '=' in l and not l.startswith('#'))
r=urllib.request.Request(f"https://{E['SN_HOST']}/api/now/table/ecc_agent"
  "?sysparm_query=name=mac-mid-datacatalog"
  "&sysparm_fields=name,status,validated,version,sys_updated_on")
r.add_header('Authorization','Basic '+base64.b64encode(f"{E['SN_USER']}:{E['SN_PASSWORD']}".encode()).decode())
print(json.load(urllib.request.urlopen(r))['result'][0])
PY
```

Healthy means **all four**: `status=Up`, `validated=true`, `version` equal to the instance's `mid.version` property, and `sys_updated_on` within ~5 minutes (heartbeat interval). A stale `sys_updated_on` still reports `Up` - that is the trap. `Up` alone proves nothing.

> Never use `.env` via `source` / `export $(grep ...)` for credentials here - the passwords contain `$`, which the shell expands, silently producing a wrong password and a confusing `401 User is not authenticated`. Parse `.env` literally, as above.

## Upgrading when the instance moves to a new patch

The instance advertises the required build in the `mid.version` property. If the MID's `version` does not match, keep it in mind as a possible factor, but note it is **not** what causes *"no valid MID is available"* (verified 2026-08-04: a version-matched, freshly validated MID still produced that error - the cause was connection MID selection, see the Metadata Collector section).

Auto-upgrade cannot complete on this install: it derives the JRE package name from the host OS and requests `mid-jre.<build>.osx.x86-64.zip`, which **does not exist** on `install.service-now.com` (404 - only `linux.x86-64` and `windows.x86-64` are published). Every attempt fails at that step and rolls back.

Manual upgrade (this is how the MID was taken from `patch2-hotfix1` to `patch2-hotfix3a`):

```bash
cd mid-server/agent
B=<build from the instance's mid.version property>   # e.g. australia-...__patch2-hotfix3a-...

# the MID already downloads + signature-verifies these before failing on the JRE
ls package/incoming/mid-core.$B.universal.universal.zip

pkill -f start-macos-loop.sh; pkill -f service_now.mid.Main
cp -p config.xml /tmp/config.xml.bak

unzip -q package/incoming/mid-core.$B.universal.universal.zip 'agent/*' -d /tmp/midcore
mv lib lib.bak && cp -R /tmp/midcore/agent/lib lib
for d in bin conf etc properties midinstaller; do rsync -a /tmp/midcore/agent/$d/ $d/; done
# do NOT copy config.xml (instance URL + credentials + the autoupgrade flag live there)
# do NOT touch extlib/ - kos-bundle jars re-sync from the instance on next boot

# the version the MID reports comes from this bookkeeping, NOT from the jars.
# without this it keeps reporting the old build and retrying the upgrade forever.
printf '#%s\npackage.filename=mid-core.%s.universal.universal.zip\n' "$(date)" "$B" > package/meta/mid-core.meta.properties
printf '#%s\npackage.filename=mid-jre.%s.osx.x86-64.zip\n'          "$(date)" "$B" > package/meta/mid-jre.meta.properties

nohup bash ./start-macos-loop.sh > logs/restart-upgrade.out 2>&1 &
```

Confirm the upgrade settled - this line must show `Missing: []`:

```bash
grep -A4 "Current packages:" logs/agent0.log.0 | tail -6
```

The `mid-jre` meta entry names a file that was never installed. That is deliberate and safe **only** because this install runs its own JDK; do not carry this trick to a normal MID.

**KOS bundle notes:**
- All `kos-bundle-*.jar` files must be at matching versions (check `ecc_agent_jar` table)
- `kos-bundle-d.jar` and `kos-bundle-e.jar`: `resources.txt` must be empty. The split Snowflake JDBC jar entries cause `ExceptionInInitializerError` with the PostgreSQL collector.
- The PostgreSQL JDBC driver is bundled inside the KOS collectors; do not add a separate jar to `extlib/`
- `Persistence directory already locked by another process: work/cache` in `agent0.log.0` means two JVMs are running. Kill both and start one.
