# MTA/GTA reference-only policy

## Mandatory boundary

All ANKIGTA implementation, refactoring, testing and review chats operate only
inside the ANKIGTA repository.

The binding constraint is the **verification method**, not the process list.

They must not:

- verify anything by driving a graphical program through screenshots, synthetic
  mouse clicks or synthetic keystrokes (computer-use automation). It is slow,
  costly and unreliable, and it never becomes repeatable evidence;
- modify an installed MTA/GTA directory beyond what the deployment section
  below permits — never its logs, caches or registry state;
- modify GTA saves/settings or use a real user map as a test fixture.

### The owner's server is a working development server

The owner runs one MTA server and works against it directly. Deploying an
ANKIGTA build into it is standing permission, not a per-ticket request, and so
is keeping the development tooling under `tools/devserver/` installed and
started there.

Deployment is still not verification. A deployed build produces no automated
evidence, every automated check still runs against a disposable copy, and GUI
automation stays prohibited whatever is installed where.

What a deployment must still do:

- write only the named resource directory, the development tooling, and the
  ACL and startup list those need in order to run at all;
- back up each installed file it edits that it did not author, alongside the
  original, before the first edit;
- treat the owner's database, saves and maps as data rather than fixtures: back
  one up before touching it, and say what changed;
- be reported file by file, so it can be undone.

Installing the companion add-on into a real Anki profile remains a separate
decision and needs its own request: the add-on builds and rebuilds a filtered
deck in the bound collection and applies ratings through the scheduler, so it
changes the owner's review history rather than only their game.

### Asking the running server instead of asking the owner

`tools/devserver/` is a resource that turns the running server into something
an agent can question and drive: what is loaded in the world and what identity
each element carries, which resources are running, starting and stopping them,
the ACL, and arbitrary server Lua.

Prefer it over asking the owner to look. Four bugs in a row here lived in the
gap between real MTA and its test doubles, and each one cost a round trip
through a person pressing a key and describing what they saw. A question put to
the server answers in one line and can be repeated.

It does not relax the testing rule below. What it produces is diagnosis, not
evidence: a finding from the live server becomes a test at the highest
programmatic seam, or it did not happen.

Two things it cannot do, and neither is a reason to reach for GUI automation:
render a frame, and tell you whether what rendered is readable.

## Launching programs

Launching processes is allowed, including MTA Server. A run must:

- launch a disposable copy under the OS temporary directory or the ANKIGTA
  workspace — never launch or write inside the installed tree;
- carry only ANKIGTA fixtures and terminate deterministically, leaving no
  process, port or file behind;
- produce its evidence programmatically — exit codes, stdout, logs, emitted
  files, HTTP responses — so the check can be re-run unattended.

If proving a behavior would require a human to look at a window or a machine to
push pixels around, it is not an automated check. Implement the highest
programmatic seam instead and leave the rest to the manual checklist.

## Allowed MTA references

The MTA source reference is:

```text
C:\Проекты\Программы\GTARESTORED\PED BEHAVIOUR REFERENCE\MTA source code
```

It is concurrently used by another chat and is strictly read-only. Agents may
search and read only the files needed for the current ticket. They must not:

- edit, format, rename, move or delete anything there;
- run a build, test, generator, package manager or cache-producing tool there;
- perform Git/worktree operations or infer that it is a clean repository;
- create evidence, temporary files or indexes inside that tree.

When a source observation materially affects a decision, record the exact
relative file, observed version/provenance when available, read time and
SHA-256 of each relied-on file. Concurrent changes outside the individually
recorded files are not evidence for or against the ticket.

Agents may also consult current official MTA documentation and official
upstream source on the internet. For technical claims, prefer:

- the official MTA wiki/manual;
- official Multi Theft Auto repositories and release documentation.

Do not treat forum posts, tutorials or remembered behavior as a supported API
contract when an official source is available.

## Testing rule

Implementation chats use repository-local unit, contract, simulation and
disposable harness tests, plus launched-process harnesses where the real runtime
contract is the thing under test. They may create fixtures only inside the
ANKIGTA workspace or the operating system's temporary directory.

Prefer the cheapest seam that still proves the behavior: a launched harness
costs seconds of process startup, so reserve it for contracts a unit test cannot
pin down.

When acceptance ultimately requires a human to observe rendering, CEF, input or
Map Editor interaction, the implementation chat must:

1. implement the behavior and the highest programmatic seam;
2. produce a precise manual runtime checklist and expected evidence;
3. leave the observed-runtime item explicitly `not run`;
4. report that a human validation pass remains.

It must not weaken, silently mark passed or delete that acceptance requirement,
and it must not substitute GUI automation for the missing human check.
