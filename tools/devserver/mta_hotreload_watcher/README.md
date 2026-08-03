# MTA Hot Reload Watcher

This local development tool watches one or more Multi Theft Auto: San Andreas resource folders. After a quiet period, it validates changed Lua/XML files where possible and asks the independent `dev_hotreload` resource to refresh and restart only the affected resource. A broken target resource cannot stop the watcher or its MTA-side endpoint.

## Architecture

1. The MTA-side F6 panel lists resources and stores which ones are allowed or ignored.
2. The watcher polls that small selection list and discovers matching `meta.xml` directories only when the selection changes; normal change detection uses recursive `watchdog` events, not directory polling.
3. Changes are filtered and grouped independently per selected MTA resource.
4. One batch runs after `debounce_ms` without another change. Events arriving during a request form exactly one later batch.
5. XML is parsed locally. Lua is checked with a configured Lua 5.1-compatible `luac` executable.
6. The watcher sends an authenticated JSON-array POST to `/dev_hotreload/call/reloadResourceByName`.
7. `dev_hotreload` rechecks the MTA-managed allowlist, performs a targeted refresh, then restarts a running target or starts a non-running target.

The watcher and `dev_hotreload` are separate processes/resources. Neither writes to a watched resource.

## Requirements

- MTA:SA server 1.6
- Windows and Python 3.11 or newer
- The Python `watchdog` package
- MTA's built-in HTTP server enabled on localhost
- Optional: a Lua 5.1-compatible `luac` executable

The HTTP port must be read from your own `mtaserver.conf` (`<httpport>`). It is **not guaranteed to be 22005**. Keep `<httpserver>1</httpserver>` enabled during development.

## 1. Install the MTA resource

The sibling `dev_hotreload` directory is already under this server's `mods/deathmatch/resources` directory. For another server, copy that complete directory under its resources directory.

No resource names need to be entered in `config.lua`. Press **F6** in MTA after installation to open the resource manager. It shows every resource detected by MTA with its current state and Hot Reload mode. The default interface language is English; use the **Language / Язык** drop-down at the top to select English or Русский. The language choice is saved locally. Search by name, hide ignored and blocked resources together, or show only custom resources. Select a row and use the single context action button, or double-click the row, to toggle allowed/ignored. Resource selections persist in a private file owned by `dev_hotreload`.

The F6 panel requires `command.hotreload` ACL access. A normal Admin ACL usually provides command access; for a custom restricted group, add this exact right:

```xml
<right name="command.hotreload" access="true" />
```

`dev_hotreload`, `admin`, `webadmin`, `resourcebrowser`, and `resourcemanager` are permanently blocked. Names containing anything other than letters, digits, `_`, or `-` are rejected.

In the MTA server console:

```text
refresh
start dev_hotreload
aclrequest list dev_hotreload
aclrequest allow dev_hotreload all
```

The request contains only these rights:

- `function.refreshResources`
- `function.restartResource`
- `function.startResource`

It does not require membership in the full Admin group.

## 2. Create a dedicated HTTP account

Create a strong, development-only account in the MTA server console:

```text
addaccount hotreload USE_A_STRONG_UNIQUE_PASSWORD
```

Grant it only access to this resource's HTTP interface. The easiest safe method is to add a dedicated group and ACL through `webadmin`. If editing `mods/deathmatch/acl.xml` while the server is stopped, the relevant entries are:

```xml
<group name="HotReloadHTTPGroup">
    <acl name="HotReloadHTTPACL" />
    <object name="user.hotreload" />
</group>

<acl name="HotReloadHTTPACL">
    <right name="resource.dev_hotreload.http" access="true" />
</acl>
```

If ACL XML was changed while MTA was running, use `reloadacl` after saving. Do not put this account in Admin and do not reuse a primary administrator account.

## 3. Install the watcher

From this directory in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item config.example.json config.json
```

`config.json` is ignored by Git. Put the dedicated account password only there.

## 4. Configure automatic resource discovery

Edit `config.json`:

```json
{
  "mta": {
    "base_url": "http://127.0.0.1:22005",
    "username": "hotreload",
    "password": "USE_A_STRONG_UNIQUE_PASSWORD",
    "hotreload_resource": "dev_hotreload",
    "timeout_seconds": 5
  },
  "watch": {
    "debounce_ms": 800,
    "ignore_initial_events": true,
    "resources_root": "C:\\MTA\\server\\mods\\deathmatch\\resources",
    "auto_sync_from_mta": true,
    "sync_interval_seconds": 3,
    "resources": []
  },
  "validation": {
    "enabled": true,
    "lua_compiler": "",
    "validate_xml": true,
    "block_reload_on_error": true
  }
}
```

Set `resources_root` to the server's real `mods\deathmatch\resources` directory. Bracketed category folders such as `[dev]` are discovered automatically. The watcher reads the allowed names from MTA every `sync_interval_seconds` and starts or stops watching their folders without restarting the watcher.

To add another resource, open the F6 panel, click **Refresh list**, select the resource, and click **Allow**. To stop watching it, click **Ignore**. No configuration edit or watcher restart is needed.

The optional `resources` array remains available for backward-compatible explicit mappings, but normally stays empty.

## 5. Run and test

The external watcher is still required because MTA does not receive reliable Windows file-change events itself. Start PowerShell once and leave it running; after that, resource selection is controlled entirely from the F6 panel without restarting PowerShell.

Start continuous watching:

```powershell
.\start_hotreload.ps1
```

The batch launcher is also available:

```bat
start_hotreload.bat
```

Direct commands:

```powershell
.\.venv\Scripts\python.exe watch_mta.py --config config.json
.\.venv\Scripts\python.exe watch_mta.py --config config.json --check
.\.venv\Scripts\python.exe watch_mta.py --config config.json --list
.\.venv\Scripts\python.exe watch_mta.py --config config.json --reload my_gamemode
```

`--check` validates configuration, the resources root, authentication, the endpoint, and all current F6 selections. It does not restart a target. `--list` shows the current MTA-selected folder mappings. `--reload` validates and reloads one currently allowed resource.

Typical watcher output:

```text
[19:42:10] [my_gamemode] Changed: client.lua
[19:42:10] [my_gamemode] Changed: web/index.html
[19:42:11] [my_gamemode] Changed: meta.xml
[19:42:12] [my_gamemode] Validating 3 changed file(s)...
[19:42:12] [my_gamemode] Validation passed (1 syntax-checked)
[19:42:12] [my_gamemode] Sending reload request...
[19:42:12] [my_gamemode] Restart accepted: Resource restart requested; previous state: running
```

MTA's debug log will contain corresponding `[dev_hotreload]` messages. Several filesystem events from a Codex/editor atomic save are expected; the per-resource debounce turns them into one request.

## Lua syntax validation

MTA uses Lua syntax compatible with the Lua 5.1 era. Install or build a trusted Lua 5.1-compatible compiler and set an absolute path:

```json
"lua_compiler": "C:\\Tools\\Lua51\\luac.exe"
```

The watcher runs it as `luac.exe -p <changed-file>` using an argument array, never a shell command. Output, exit status, and line numbers are reported. With an empty value, one startup warning is printed and Lua validation is explicitly reported as skipped. XML, EDF, and map files use Python's XML parser. HTML, CSS, JavaScript, images, fonts, and audio trigger reloads but are not statically validated.

If `block_reload_on_error` is `true`, a detected Lua/XML error blocks that batch. Fix and save the file to trigger a fresh batch. Deletions are not validated because the deleted content no longer exists.

## Files watched and ignored

Watched extensions include Lua, XML, map, EDF, HTML, CSS, JavaScript, JSON, text, PNG/JPEG/WebP/SVG/GIF, MP3/OGG/WAV, TTF, WOFF, and WOFF2. File creation, modification, deletion, rename/move, atomic save, and directory creation/deletion are handled recursively.

Git metadata, common IDE settings, Python environments/caches, `node_modules`, `dist`, `build`, temporary/swap files, watcher logs, and OS metadata are ignored.

## Troubleshooting

- **HTTP 401:** The username/password is wrong or the MTA account does not exist. Update `config.json`; the watcher never prints the password.
- **HTTP 403:** Add `user.hotreload` to the dedicated ACL group and grant `resource.dev_hotreload.http`. Reload ACL configuration.
- **HTTP 404:** Confirm the URL uses the actual `<httpport>`, `dev_hotreload` is started, its name matches `hotreload_resource`, and the HTTP exports are present.
- **Connection refused:** Start MTA, enable its HTTP server, verify the port, and keep the URL on `127.0.0.1`. The watcher retries temporary connection failures with capped backoff and continues watching after a failed batch.
- **ACL permission denied in MTA:** Run `aclrequest list dev_hotreload`, then `aclrequest allow dev_hotreload all`. Confirm all three requested rights show as allowed.
- **Resource not found:** Confirm the mapping name matches the resource folder's MTA name and it has a valid `meta.xml`. The endpoint performs one non-global discovery refresh for newly created resources.
- **Resource starts and immediately stops:** Inspect the MTA debug log for a runtime or load error in the target. The independent watcher and endpoint remain alive; fix and save again.
- **Malformed `meta.xml`:** The watcher prints the line and column and blocks the reload when configured. Correct the XML and save.
- **Lua syntax error:** Configure `luac` to catch it before restart, or inspect MTA's debug output when no compiler is configured.
- **Changed client file not appearing:** Ensure it is referenced correctly in `meta.xml`, watch for client download/runtime errors, and confirm clients received the restarted resource. Browser assets may also require closing/reopening the CEF page or disabling its application cache during development.
- **Atomic save produces many events:** This is normal. Increase `debounce_ms` if an editor writes for longer than the current quiet period. Duplicate filenames are combined within each batch.
- **Targeted refresh fails:** Check the three resource ACL requests and the target's `meta.xml`. The response is reported as `RESOURCE_REFRESH_FAILED`.
- **Restart/start fails:** Check the specific `RESOURCE_RESTART_FAILED` or `RESOURCE_START_FAILED` message and the MTA log for the target's load failure.

## Security and disabling

This system is intended only for local development:

- Use `127.0.0.1`, and restrict the MTA HTTP port to localhost with the firewall.
- Use a dedicated low-privilege account with a strong password stored only in ignored `config.json`.
- Keep a strict resource allowlist. The endpoint never accepts arbitrary commands, Lua, or paths.
- Do not expose the MTA web interface publicly and never use the primary Admin account.
- Stop or disable `dev_hotreload` outside development.

To disable Hot Reload, press Ctrl+C in the watcher and run this in the MTA console:

```text
stop dev_hotreload
```

For a longer-term disable, remove `dev_hotreload` from automatic startup, remove the dedicated HTTP ACL object, and securely delete the local `config.json` if its credential is no longer needed.

## Tests

The normal test suite does not need `watchdog` or a running MTA server:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

HTTP calls are mocked. A live MTA server is required only for the final `--check` and real reload integration test.
