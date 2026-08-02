# Driving a development server

`ankigta_probe/` is a resource that turns a local MTA server into something an
agent can ask questions of and act on, instead of asking a person to press keys
and report back.

Copy it into `<MTA Server>/mods/deathmatch/resources/`, register it in
`mtaserver.conf` with `startup="1"`, and put `resource.ankigta_probe` in the
`Admin` ACL group.

Then, from anywhere with filesystem access:

```bash
echo "probe" > <resources>/ankigta_probe/command.txt
sleep 2 && tail -40 <resources>/ankigta_probe/result.txt
```

Read its own `README.md` for the command list and for why it must never be on a
public server.

## Why this is here

Four bugs in a row lived in the gap between real MTA and the test doubles that
stand in for it: `toJSON` wrapping its argument list, an event with a handler
and no `addEvent`, a cursor hidden so `onClientClick` never fired, and `me:ID`
being present only while the stock editor has the map open. The suite was green
through all four. A question put to the running server answers each of them in
one line, and that is the loop worth having.

The suite is still the regression net. This is the loop that finds things.


## Granting it rights

Put `resource.<name>` in the `Admin` ACL group, **with the server stopped**.
MTA reads `acl.xml` at start and writes it back from memory on the way out, so
an edit made under a running server is overwritten and silently lost. From a
running server the supported route is the console:

```
aclrequest allow <resource> all
```

Reading another resource's files — which is how a file watcher notices a change
— is gated on `general.ModifyOtherObjects`, and MTA logs a warning per attempt
when it is missing. A watcher that retries twice a second turns one unfixed
permission into an unreadable console, so it stops asking after the first
refusal and says so once.
