# ANKIGTA dev control

A file-driven control channel for a **local development server**.

Write a command into `command.txt`. It runs within a second, the answer is
appended to `result.txt`, and the command file is emptied so nothing runs
twice. `report.txt` holds the last world report.

```bash
echo "probe" > command.txt      # then read result.txt a second later
```

## Why it exists

Every bug in this project so far cost a round trip through a person standing in
the world: press a key, click a thing, report back. Nearly every question was
about a fact the server already knew — which elements exist, what identity each
carries, which resources are running. This asks the server directly.

## Commands

Run `help` for the current list. In short: `probe`, `report`, `list`, `start`,
`stop`, `restart`, `refresh`, `refreshall`, `players`, `say`, `acl-add`,
`acl-right`, `call`, `exec`, `shutdown`.

`exec` takes arbitrary server Lua and answers with its value:

```
exec return #getElementsByType("object")
exec return getResourceState(getResourceFromName("ankigta"))
```

## Do not put this on a public server

`exec` runs arbitrary Lua as the server, and the only thing guarding it is
write access to this folder. On a local box that is exactly the point. Anywhere
else it is a way in.

It is registered in `mtaserver.conf` with `startup="1"` and is in the `Admin`
ACL group, which is what lets it start and stop resources and edit the ACL.
Remove both when this server stops being a development one.


## Granting rights at runtime

`acl-grant <resource>` puts `resource.<name>` in the `Admin` group and saves.
`acl-check <resource>` reports what it may actually do, asked of the server
rather than read off the file.

That distinction is the whole point. MTA reads `acl.xml` at start and writes it
back **from memory** on the way out, so editing the file under a running server
is overwritten and silently lost — the file looks right and the server
disagrees. Going through the ACL API changes the memory the server will write,
so it sticks.

This resource is the one exception and has to be bootstrapped by hand: put
`resource.ankigta_probe` in the `Admin` group with the server **stopped**.
After that it can grant to anything else without one.
