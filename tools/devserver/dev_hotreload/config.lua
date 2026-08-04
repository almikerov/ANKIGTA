HOTRELOAD_CONFIG = {
    -- Optional initial defaults. Runtime changes made with /hotreload are saved
    -- separately and override these values, so this table normally stays empty.
    defaultAllowedResources = {},
    stateFile = "@hotreload_state.xml",
    commandName = "hotreload",
    -- How often Autoupdate looks, in ms. Each pass reads every declared
    -- file of every allowed resource, because MTA offers no modification
    -- time to compare instead.
    autoupdateInterval = 2000,
    -- Whether Autoupdate also picks up resources that were not there before.
    -- A folder dropped into `resources/` is invisible until the resource list
    -- is refreshed, so the file poll cannot see it: there is nothing yet to
    -- fingerprint. Discovery refreshes, then allows and starts what appeared.
    discoverNewResources = true,
    -- How often Discovery looks, in ms. Much rarer than the file poll, because
    -- a discovery pass refreshes MTA's whole resource list rather than reading
    -- the files of the few resources being watched.
    discoveryInterval = 10000,
    -- Whether this resource reloads itself when its own files change. It is
    -- the one resource the rest of this cannot reload -- it is blocked from
    -- being managed, so that the panel cannot be used to stop the panel -- and
    -- without this every edit to it ended in a restart by hand.
    selfReload = true,
    logPrefix = "[dev_hotreload]",
    -- Resources inside these standard MTA categories are treated as bundled.
    -- Root resources and resources in any other category are treated as custom.
    bundledOrganizationalPaths = {
        ["[admin]"] = true,
        ["[editor]"] = true,
        ["[gamemodes]"] = true,
        ["[gameplay]"] = true,
        ["[managers]"] = true,
        ["[web]"] = true,
    },
}
