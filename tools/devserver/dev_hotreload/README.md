# dev_hotreload

Reload a resource the moment its files change, and manage resources from inside the game instead of from the console.

It stands on its own. No other resource has to be installed, no MTA account has to exist, no port has to be agreed on, and nothing here talks to the network. Download it, drop the folder into `resources/`, start it.

- **Autoupdate** watches the files of the resources you allow and reloads one when it changes.
- **The panel** (F6 by default) lists every resource MTA knows, with its state, and can start, stop, restart and reload them.
- **The change report** says which files moved and by how much on every reload.
- **Discovery** picks up a resource folder dropped in while the server is running.
- **A file channel** lets anything outside the game ask for a reload — an editor hook, a build script, a file watcher.

Press **F6** in MTA to open the resource manager UI — or whatever key you have chosen; see *Choosing the open key* below. It displays every resource currently detected by MTA, its runtime state, and whether Hot Reload is allowed, ignored, or permanently blocked. The interface starts in English. Use the **Language / Язык** drop-down at the top to select English or Русский; the choice is saved locally for the next MTA session.

Use the live name search and the **Show allowed only** and **Custom resources only** filters to narrow the list. The custom-only filter hides resources from the standard bundled MTA categories configured in `config.lua`. Select a row and use the single action button, or double-click a row, to switch between allowed and ignored. Blocked resources remain read-only.

## Running resources by hand

The panel is also a plain resource manager. Select a row and use **Start**, **Stop** or **Restart** — no name to type, which is the point of having them here rather than at the console.

These are deliberately *not* Hot Reload. A reload means "the files changed, pick them up" and only applies to a resource Hot Reload is allowed to touch; these three are ordinary resource control and work on ignored resources too. Watching a resource's files and running it are separate questions.

Protected resources stay out of reach: the same guard that refuses to reload them refuses to stop them, which is what stops this panel being used to stop this panel.

Stopping needs one ACL right the earlier version never asked for. A right added to `meta.xml` after you last ran `aclrequest allow dev_hotreload all` is **not** covered by that grant — run it again, or Stop will report that MTA refused.

## Seeing what changed

Every reload reports which files moved and by how much, as `+added -removed` lines:

```text
INFO: [dev_hotreload]   my_resource: client/panel.lua  +67 -0
INFO: [dev_hotreload]   my_resource: meta.xml  +1 -1
```

The same report appears in the panel under **Last change** and, briefly, in chat. It is reported on *every* reload path, not just the file watch, so a reload driven through the file channel, by the panel, or by the console says the same thing.

How it is counted: lines are compared as multisets, not by position. Editing a line therefore reads as `+1 -1` rather than `0`, and a line merely moved counts as neither. This reports how much moved — it is not a patch. A file appearing or disappearing is marked `(added)` / `(removed)`. A file too large to have kept its previous content reports `?` rather than `+0 -0`, because "changed by an unknown amount" and "changed by nothing" must not print the same.

The first sight of a resource reports nothing: there is no previous version to compare against, and announcing every file as added the first time anything is watched would be noise rather than news.

## Reloading itself

This resource was the one thing it could not reload. It is blocked from being managed — so that the panel cannot be used to stop the panel — and being blocked also kept it out of the file watch, so every edit to it ended in a restart by hand.

It now watches its own files on the same tick as everyone else's and restarts itself when they change, on its own path rather than through the reload that refuses blocked names. `selfReload` in `config.lua` turns it off.

Before restarting, it compiles its own Lua files and refuses to restart if any of them does not. The failure mode is not symmetrical: a typo in another resource is reported by a tool that is still running, while a typo here would take the tool down with it and leave nothing running to fix it from. Compiling does not execute anything — it is a syntax check.

That check needs `function.loadstring`. Without it the resource says so once and reloads itself unchecked, which is still better than not reloading at all.

## Choosing the open key

The **Open key** button at the bottom of the panel rebinds it. Press the button, then press the key you want; Escape cancels. The choice is saved next to the language in `@ui_settings.xml` and applies from the next MTA session onwards as well.

Mouse buttons, Escape and Enter are refused: a mouse button would fire while clicking inside the very panel it opens, and the other two are how you get out of one. If a saved key is not one this MTA build knows, the panel says so and falls back to F6 rather than becoming unopenable.

## Picking up newly added resources

Autoupdate watches the files of resources MTA already knows. A resource folder that is *dropped in* while the server runs is not one of those: MTA read its resource list at boot, the new name is not in it, and so there is nothing yet to fingerprint. Until now that meant typing `refresh` and then `start` by hand.

Discovery closes that gap. On its own slower timer it refreshes the resource list, compares it against the names it saw last time, and for anything that turned up it marks the resource allowed and starts it — after which the normal file watch keeps it reloading on every edit. Two settings in `config.lua` control it:

- `discoverNewResources` (default `true`) — whether to look at all.
- `discoveryInterval` (default `10000` ms) — how often. Deliberately much rarer than `autoupdateInterval`, because a discovery pass refreshes MTA's whole resource list rather than reading a few files.

Only **custom** resources are adopted. A refresh also surfaces bundled MTA resources that simply were never loaded, and starting those is not what dropping a folder in was asking for. Blocked resources are never touched.

A newly added resource is typically picked up on the *second* pass rather than the first: the refresh that makes MTA load it does not make it appear in the same tick's resource list, so it is seen as new on the following one.

Copying a folder is not atomic, and MTA can scan it between the manifest landing and the scripts that manifest names — the resource is then real but broken, and starting it fails. Discovery retries such a name on the next few passes rather than writing it off, and gives up after three, so a partial copy completes on its own while a genuinely broken resource does not fill the console forever.

Discovery runs while Autoupdate is on. `hotreload discover` forces a pass from the console at any time; the first call with no baseline yet only records the current list, and says so, rather than adopting every resource on the server.

There is deliberately **no button** for it. Discovery is a convenience for the hands-off case, and the panel already has an explicit path that does the same thing without surprises: **Refresh list** makes a newly dropped resource visible, then **Start** runs it and **Allow** puts it under the file watch. A button that silently allowed and started resources would be doing two mutating things under a name that sounds like a read.

Selections are saved in the private `@hotreload_state.xml` file. The UI requires the logged-in account to have `command.hotreload` ACL permission. Restricted console commands remain available as an emergency fallback:

```text
hotreload list
hotreload status my_resource
hotreload allow my_resource
hotreload ignore my_resource
hotreload refresh
hotreload discover
```

The command is ACL-restricted. The server console can use it directly; an in-game administrator needs the `command.hotreload` right. Protected administrative and web-management resources can never be enabled.

## Installing

Put this directory anywhere under `mods/deathmatch/resources`, then, in the server console:

```text
refresh
start dev_hotreload
aclrequest allow dev_hotreload all
```

That grants the four rights in `meta.xml`: `refreshResources`, `restartResource`, `startResource`, `stopResource`, plus `general.ModifyOtherObjects`, which is what MTA gates reading another resource's files on — how the file watch notices a change. Nothing else is needed, and no account is involved.

Run `aclrequest allow` again after updating this resource: rights added to `meta.xml` after your last grant are not covered by it, and the first symptom is Stop reporting that MTA refused.

Unless, that is, you put `resource.dev_hotreload` in the `Admin` ACL group instead, which covers every right including ones added later. Worth knowing before chasing a permission problem that is not there: ask the server rather than reading `acl.xml`, because the two disagree whenever the file was edited under a running server.

```text
hotreload status dev_hotreload
```

## Driving it from outside

Anything that can write a file in this folder can ask for a reload. Write one request line into `command.txt`; it runs within a quarter of a second and one JSON object per request is appended to `result.txt`.

```text
status
reload {"resource": "my_resource", "requestId": "abc"}
```

`requestId` is echoed back, so an answer can be matched to the request that earned it rather than to whatever arrived next. The command file is emptied before the requests in it run, so a request that restarts something is not found again on the way back up.

This used to be an HTTP endpoint behind an MTA account. The account needed a password, and every caller had to keep that password somewhere — in practice, in plain text. A `.gitignore` keeps a secret out of a publication, not off a disk. There is no secret here to keep, and no listener either, so nothing about this resource can be reached from the network at all.

The two exported functions, `reloadResourceByName(name)` and `getHotReloadStatus()`, remain available to other resources through `exports` for anyone who prefers to call them directly.

This resource is for localhost development only. Stop it outside development:

```text
stop dev_hotreload
```


## Autoupdate, Reload and Startup

**Autoupdate** is a checkbox in the panel, off by default. On, the server takes
a fingerprint of every file each allowed resource declares in its `meta.xml`
and compares it every couple of seconds; a resource whose files changed is
reloaded on its own. MTA gives Lua no modification time, so the fingerprint is
the content itself — which is why this is off unless asked for, and why the
interval is `autoupdateInterval` in `config.lua`.

Flipping it on takes a baseline first, so switching it on does not reload
everything at once.

**Reload allowed** reloads every allowed resource now, without waiting.

**Startup** is per resource and independent of Hot Reload: a resource can be
started at boot without being watched, and watched without being started.

The column answers one question — will this resource start on boot — as `yes`
or `no`. That includes the state every resource has whether or not Hot Reload
is installed: the server's own list, read with
`getServerConfigSetting("resource")` fresh each time the catalog is built, so
it cannot drift from the file.

Underneath there are two ways a resource gets to `yes`, and only one of them is
ours to change. MTA exposes no
`setServerConfigSetting`, and the server's `SetSetting` accepts only a short
list of scalar settings that `<resource>` is not among — so `mtaserver.conf`
cannot be written from a running server at all. Hot Reload's own flag starts
the resource shortly after Hot Reload itself starts, which reaches the same
end, and that is the flag the **Toggle startup** button switches. Pressed on a
resource the config already starts, it explains that rather than pretending to
change anything — which is the one place the distinction needs to surface, and
the reason the column itself does not carry it.

This column used to show only Hot Reload's flag under the plain heading
"Startup", which read as the server's answer and was not: two dozen resources
MTA genuinely autostarts were displayed as not starting.

Both also work from the console:

```
hotreload autoupdate on
hotreload reload
```
