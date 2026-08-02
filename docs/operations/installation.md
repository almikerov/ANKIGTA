# Installing, updating and removing ANKIGTA

ANKIGTA is two pieces you install yourself. There is no installer, no
downloader and no auto-update:

- the **MTA resource**, a folder you copy into your own MTA Server;
- the **companion add-on**, a folder Anki loads from its add-on directory.

ANKIGTA never edits Anki's add-on directory, never downloads a package and
never restarts Anki (ADR 0023). If the add-on is missing or not answering, that
shows up as an ordinary connection failure, not as an installer screen.

Before starting, read [supported versions](../release/supported-versions.md).
Session creation and ratings are enabled only on the certified matrix.

No step in this document requires editing SQLite, editing a `.map` file, or
running SQL. If you find yourself doing either, stop: something is wrong and
the recovery paths in [backups and recovery](backups-and-recovery.md) are the
supported way out.

## What a release contains

Two archives, both built by `python -m tools.package --out dist --manifest
dist/artifacts.json`:

| Artifact | Unpacks as | Installs to |
| --- | --- | --- |
| `ankigta-mta-resource-<version>.zip` | `ankigta/` | `<MTA Server>/mods/deathmatch/resources/ankigta` |
| `ankigta-companion-<version>.ankiaddon` | the add-on's own files | `<Anki data folder>/addons21/ankigta_companion` |

`artifacts.json` lists every file with its SHA-256. Keep it: it is how you
answer "which build is installed" later, and it is the list the removal steps
below refer to.

Both archives carry the same version number, and a test holds them to it.

## Install

### 1. The MTA resource

1. Stop the MTA server, or make sure the `ankigta` resource is not running.
2. Unpack `ankigta-mta-resource-<version>.zip` into
   `<MTA Server>/mods/deathmatch/resources/`. It creates the directory
   `ankigta/`.

   **Keep that name.** MTA identifies a resource by its directory name, and the
   ACL right in the next step names `ankigta`. A folder called `ankigta-1.0.0`
   is a different resource that your account has no rights to.
3. Give your own admin account the study right. In
   `<MTA Server>/mods/deathmatch/acl.xml`, inside the group your admin account
   belongs to, add:

   ```xml
   <right name="resource.ankigta.study" access="true" />
   ```

   ANKIGTA is for one Study Player — the MTA administrator (ADR 0019). Other
   players may be on the server; they get no study state, links, markers or
   collection, and the server rejects their ANKIGTA events.
4. Start the resource: `start ankigta` in the server console.

On first start the resource creates its own database,
`resources/ankigta/ankigta.sqlite`, and a `backups/` directory beside it. Both
are yours, not ours — see [removal](#remove) before deleting anything.

### 2. The companion add-on

Anki is not launched or modified by ANKIGTA; you install this by hand.

1. Close Anki.
2. Unpack `ankigta-companion-<version>.ankiaddon` into
   `<Anki data folder>/addons21/ankigta_companion/`. On Windows the Anki data
   folder is `%APPDATA%\Anki2`.

   The archive has no top-level directory: its `__init__.py` and
   `manifest.json` go straight into `ankigta_companion/`.

   Anki's *Tools → Add-ons → Install from file…* will also take the
   `.ankiaddon` file and put it in the right place.
3. Start Anki and open the profile you intend to study from.
4. The add-on asks once for your MTA resource folder — the `ankigta` directory
   from step 1. It then picks a free loopback port, generates a token, and
   writes `connection.json` into that folder. MTA reads it; you never copy a
   port or a token by hand.

   Only `127.0.0.1` is used. LAN addresses and IPv6 `::1` are not supported
   (Prototype 0004).

### 3. Bind the Anki collection

ANKIGTA studies exactly one **Bound Anki Collection** and will not follow you
to another profile (story 8).

1. With the profile you want open, use *Tools → ANKIGTA: Bound Anki
   Collection…* in Anki.
2. Confirm the binding. The add-on writes a UUID of its own into the
   collection's configuration; that UUID, not the profile name or path, is what
   a Spatial Link points at.
3. If ANKIGTA finds a collection that looks like a copy of an already-registered
   one, it asks you to choose: *This is the previous collection* keeps the
   existing Spatial Links, *This is a new copy* takes a new UUID and starts with
   none. New copy is the default, and it is the safe answer. If the previous
   instance is still registered on this computer, the copy is treated as new
   automatically and you are not asked.

Opening a different collection pauses ANKIGTA. Nothing is migrated, and equal
`cardId` numbers in two profiles are never treated as the same card.

### 4. First run

1. In Anki, open the Bound Anki Collection. ANKIGTA does not open Anki or switch
   profiles for you.
2. Join your MTA server with the admin account holding the study right.
3. Type `/ankigta` in the chat to open the study window. It should read
   *paused*, connected.
4. Press `Начать обучение` / `Start studying`. Only this creates the
   `ANKIGTA Session` filtered deck, the Activation Zones and the Next Card
   Indicator. Connecting alone never does (story 31).

Press `F7` for the Map Entity list. It has a filter box; it searches the stored
record — identity, name, Entity Tag, type and Spatial Link state — so it finds
entities whose Runtime Instance is unloaded or gone.

## Update

An update is a copy over the top. Nothing you own is replaced by it: the
database, the backups and the connection file are not part of either archive,
and a test holds that.

1. In MTA, press `Pause studying` or `Stop` in the study window first. This
   returns the session's cards to their original decks and removes the owned
   filtered deck while something is still running to hear Anki's answer.

   Stopping the resource also asks Anki to do this, but MTA tears a resource's
   pending HTTP requests down with the resource, so a stop issued at teardown
   may not arrive. Pausing first is what makes it certain.
2. Stop the resource: `stop ankigta`.
3. Unpack the new `ankigta-mta-resource-<version>.zip` over the existing
   `resources/ankigta/`, replacing files. Do not delete the folder first.
4. Close Anki. Unpack the new companion archive over
   `addons21/ankigta_companion/`, replacing files. Leave `user_files/` alone —
   it holds your connection settings and the collection registry, and no
   release archive contains it.
5. Start Anki, then `start ankigta`.

If the new build needs a newer database schema, it migrates on first start and
writes a verified backup **before** touching anything (ADR 0016). Migrating
from every schema ANKIGTA has shipped is covered by automated tests, including
the check that the rows are still there afterwards.

Downgrading is not supported. A database migrated forward is not migrated back;
if you need the old build, restore the pre-migration backup that the upgrade
left in `backups/`.

## Remove

Read this before deleting the resource folder: **your Spatial Links live inside
it.** MTA gives a resource its own directory for files, so
`resources/ankigta/ankigta.sqlite` and `resources/ankigta/backups/` are in the
folder you are about to delete.

1. In MTA, press `Stop` in the study window. This returns every card of the
   session to its original deck and removes the `ANKIGTA Session` filtered
   deck. Confirm in Anki that no deck named `ANKIGTA Session` remains.
2. `stop ankigta` in the server console.
3. **Take your data out first**, if you may ever want it:

   - `resources/ankigta/ankigta.sqlite` — every Map Entity, Spatial Link,
     Entity Tag, radius and the Change History;
   - `resources/ankigta/backups/` — the rotating copies of the same.

   Copy them somewhere outside the resource folder. They are ordinary SQLite
   files and stay readable with no ANKIGTA installed.
4. Delete `resources/ankigta/`, and remove the
   `<right name="resource.ankigta.study" .../>` line from `acl.xml`.
5. In Anki, close the program and delete
   `addons21/ankigta_companion/` — including `user_files/`, which holds the
   connection token and the collection registry. Anki's *Tools → Add-ons →
   Delete* does the same thing.

   Removing the add-on does not change a single card, note, deck or review. The
   collection UUID it wrote stays in the collection's configuration and is
   harmless; if you reinstall later and keep your database, your Spatial Links
   still resolve.

Nothing about removal edits your Anki collection beyond the session cleanup in
step 1, and nothing edits a `.map` file at any point.

## Reinstall

Unpack the resource archive again into `resources/`. If you left
`ankigta.sqlite` in place, the build adopts it and your links are still there.
If you moved it away, you get an empty world — and you get it by moving a file,
not by editing a database.

Both paths are covered by the certification suite
(`pytest tests/test_certification.py`).

## When something will not connect

- The study window shows a category, not a stack trace. `Подключиться` /
  `Connect` is always available while disconnected and retries immediately
  without turning background reconnection off.
- *Tools → ANKIGTA: Companion Connection…* in Anki shows what is published and
  is where the folder, port and token are changed.
- Both sides have advanced fields for a manual port and token. Typing one puts
  that side into Manual Connection Mode: automatic publication stops
  overwriting it. If the two sides disagree, the connection is refused with an
  explicit error rather than one side quietly winning — align them by hand or
  put both back into Automatic Connection Mode.
- The existing token is never displayed and never written to ordinary logs. You
  can replace it; you cannot read it back.
- v1 trusts this Windows computer and the programs on it. The token keeps
  stray requests out and keeps the card browser away from the control API; it
  is not a defence against a local administrator or malware.
