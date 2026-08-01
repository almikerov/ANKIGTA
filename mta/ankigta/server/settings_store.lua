ANKIGTA = ANKIGTA or {}

-- The server's half of the settings (ADR 0014): world and study state, which
-- is persisted, shared and undoable, plus this side's local connection
-- override, which is none of those three.
--
-- Everything here goes through the shared schema. The store decides *where* a
-- setting lives; the schema decides whether this side may write it, whether
-- the value is acceptable and whether the change belongs in Change History.
-- Keeping that split is the whole point: a store that also knew the ranges
-- would be a second copy of them.

local SIDE = "server"

local SettingsStore = {
    side = SIDE,
    values = {},
    loaded = false,
}

local function schema()
    return ANKIGTA.Settings
end

--- Settings this side persists in its own database.
local function isStored(key)
    return schema().writeKind(SIDE, key) == "authority"
end

--- Settings this side holds only as a local connection override.
local function isOverride(key)
    return schema().writeKind(SIDE, key) == "local_override"
end

local function isSecret(key)
    local definition = schema().definition(key)
    return definition ~= nil and definition.rule.kind == "secret"
end

--- Re-read persisted settings, filling in defaults for everything unset.
--
-- Called on resource start, so a restart restores exactly what the user chose
-- and nothing else: a stored value the current schema rejects is dropped by
-- `Store.listUserSettings` and the default takes its place.
function SettingsStore.load()
    local values = {}
    for key, definition in pairs(schema().schema) do
        if isStored(key) and definition.default ~= nil then
            values[key] = definition.default
        end
    end

    local persisted, readError = ANKIGTA.Store.listUserSettings()
    if not persisted then
        SettingsStore.values = values
        SettingsStore.loaded = false
        return false, readError
    end
    for key, value in pairs(persisted) do
        if isStored(key) then
            values[key] = value
        end
    end

    SettingsStore.values = values
    SettingsStore.loaded = true
    return true
end

local function connectionPort()
    local effective, category = ANKIGTA.ConnectionConfig.loadEffective()
    if not effective then
        return false, category
    end
    return effective.port
end

--- The value this side would act on right now.
--
-- A setting owned by another side is refused rather than answered with its
-- default: the default is not what that machine currently has, and pretending
-- otherwise reads like an answer.
function SettingsStore.get(key)
    local definition = schema().definition(key)
    if not definition then
        return false, "settings.error.unknown"
    end
    if isSecret(key) then
        -- The token is set and replaced, never read back out.
        return false, "settings.error.secret_not_readable"
    end
    if isOverride(key) then
        return connectionPort()
    end
    if not isStored(key) then
        return false, "wrong_authority"
    end
    local value = SettingsStore.values[key]
    if value == nil then
        return definition.default
    end
    return value
end

local function setConnectionOverride(key, value)
    local override, reason = schema().overrideBy(SIDE, key, value)
    if not override then
        return false, reason
    end
    if key == "connectionPort" then
        -- Replacing the port alone keeps the token that is already in force.
        return ANKIGTA.ConnectionConfig.setManual(override.value, nil, true)
    end
    local port, portError = connectionPort()
    if not port then
        return false, portError
    end
    return ANKIGTA.ConnectionConfig.setManual(port, override.value)
end

--- Change a setting this side owns, or this side's local override.
function SettingsStore.set(key, value)
    local writeKind, writeReason = schema().writeKind(SIDE, key)
    if not writeKind then
        if writeReason == "unknown_setting" then
            return false, "settings.error.unknown"
        end
        return false, writeReason
    end
    if writeKind == "local_override" then
        return setConnectionOverride(key, value)
    end

    local stored, storeError = ANKIGTA.Store.setUserSetting(key, value)
    if not stored then
        return false, storeError
    end
    SettingsStore.values[key] = schema().normalize(key, value)
    return true
end

--- Only the settings this side owns outright.
--
-- This is what the client is told: its own settings are none of the server's
-- business, and the connection override is local to whichever side made it.
function SettingsStore.owned()
    local snapshot = {}
    for key in pairs(schema().schema) do
        if isStored(key) then
            local value, reason = SettingsStore.get(key)
            if reason == nil then
                snapshot[key] = value
            end
        end
    end
    return snapshot
end

--- Every setting this side can answer for, for a caller that wants them all.
function SettingsStore.all()
    local snapshot = {}
    for key in pairs(schema().schema) do
        -- `false` is a legitimate value for a toggle, so a refusal is told
        -- apart by its reason rather than by the value being falsy.
        local value, reason = SettingsStore.get(key)
        if reason == nil then
            snapshot[key] = value
        end
    end
    return snapshot
end

ANKIGTA.SettingsStore = SettingsStore
