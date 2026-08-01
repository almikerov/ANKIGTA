ANKIGTA = ANKIGTA or {}

-- Backups, rotation and recovery for the server database.
--
-- The one rule this module exists to enforce is negative: a damaged database is
-- never replaced without the user saying so. Everything else follows from it.
-- Nothing here deletes the primary database, nothing here restores on its own,
-- and the only function that moves the primary out of the way is the one a user
-- action calls. When it does move it, it moves it into quarantine rather than
-- into the bin, because a database that failed is the only evidence of why.
--
-- Copying is `fileCopy`, not a chunked read into Lua: a Lua string is not a
-- byte buffer, and a backup that is one byte different from the database is not
-- a backup. A copy is published under its listed name only by renaming a file
-- that has already been opened as SQLite and verified, so a name that appears
-- in the manifest never refers to a half-written file.

local Backup = {}

local DEFAULT_DATABASE_PATH = "ankigta.sqlite"
local BACKUP_DIRECTORY = "backups/"
local MANIFEST_PATH = BACKUP_DIRECTORY .. "manifest.json"
local JOURNAL_PATH = BACKUP_DIRECTORY .. "restore-journal.json"
local STAGING_PATH = BACKUP_DIRECTORY .. "staging.sqlite"
local MANIFEST_VERSION = 1

-- ADR 0016: seven daily copies and three pre-migration ones.
local DAILY_RETENTION = 7
local PREMIGRATION_RETENTION = 3

-- A daily backup is taken off the request path. F7 has a two-second envelope
-- and copying a database is not something to spend it on, so a data change only
-- marks the store dirty and a timer does the copying afterwards.
local DAILY_BACKUP_DELAY_MS = 5000

local MINIMUM_SCHEMA_VERSION = 1

Backup.databasePath = DEFAULT_DATABASE_PATH
Backup.currentSchemaVersion = MINIMUM_SCHEMA_VERSION
Backup.pendingDataChange = false
Backup.dailyTimer = nil

--- Point the module at a database and tell it which schema is current.
function Backup.configure(options)
    if type(options) ~= "table" then
        return false, "invalid_backup_configuration"
    end
    if type(options.databasePath) == "string" and options.databasePath ~= "" then
        Backup.databasePath = options.databasePath
    end
    if tonumber(options.currentSchemaVersion) then
        Backup.currentSchemaVersion = tonumber(options.currentSchemaVersion)
    end
    return true
end

-- --- small helpers ----------------------------------------------------------

local function execute(connection, statement, ...)
    local handle = dbQuery(connection, statement, ...)
    if not handle then
        return false, "query_rejected"
    end
    local rows, errorCode, errorMessage = dbPoll(handle, -1)
    if rows == false then
        return false, tostring(errorCode) .. ": " .. tostring(errorMessage)
    end
    return true, rows
end

local function connect(path)
    return dbConnect("sqlite", path, "", "", "share=0;batch=0;tag=ankigta-backup")
end

local function disconnect(connection)
    if isElement(connection) then
        destroyElement(connection)
    end
end

local function readTextFile(path)
    if not fileExists(path) then
        return nil
    end
    local handle = fileOpen(path, true)
    if not handle then
        return nil
    end
    local size = fileGetSize(handle)
    local contents = size and size > 0 and fileRead(handle, size) or ""
    fileClose(handle)
    return contents
end

local function writeTextFile(path, contents)
    local handle = fileCreate(path)
    if not handle then
        return false, "file_create_failed"
    end
    local written = fileWrite(handle, contents)
    fileFlush(handle)
    fileClose(handle)
    if not written or written < #contents then
        -- A half-written file is worse than none: delete it rather than leave
        -- a truncated manifest that decodes to nonsense.
        fileDelete(path)
        return false, "file_write_failed"
    end
    return true
end

--- Today, as the calendar sees it.
-- `getRealTime` reports `month` as 0-11 and `year` as years since 1900, so both
-- are shifted here rather than at every call site.
local function dayKey(timestamp)
    local now = getRealTime(timestamp)
    if type(now) ~= "table" then
        return "unknown"
    end
    return string.format(
        "%04d-%02d-%02d",
        (tonumber(now.year) or 0) + 1900,
        (tonumber(now.month) or 0) + 1,
        tonumber(now.monthday) or 0
    )
end

Backup.dayKey = dayKey

-- --- the manifest -----------------------------------------------------------

local function emptyManifest()
    return {version = MANIFEST_VERSION, nextId = 1, entries = {}, quarantine = {}}
end

local function readManifest()
    local contents = readTextFile(MANIFEST_PATH)
    if type(contents) ~= "string" or contents == "" then
        return emptyManifest()
    end
    local decoded = fromJSON(contents)
    if type(decoded) ~= "table" then
        outputDebugString("[ANKIGTA] backup_manifest_unreadable", 2)
        return emptyManifest()
    end
    local manifest = emptyManifest()
    manifest.nextId = tonumber(decoded.nextId) or 1
    for _, entry in ipairs(type(decoded.entries) == "table" and decoded.entries or {}) do
        if type(entry) == "table" and type(entry.path) == "string" then
            table.insert(manifest.entries, entry)
        end
    end
    for _, entry in
        ipairs(type(decoded.quarantine) == "table" and decoded.quarantine or {})
    do
        if type(entry) == "table" and type(entry.path) == "string" then
            table.insert(manifest.quarantine, entry)
        end
    end
    return manifest
end

local function writeManifest(manifest)
    local encoded = toJSON(manifest, true)
    if type(encoded) ~= "string" then
        return false, "backup_manifest_encode_failed"
    end
    local written, reason = writeTextFile(MANIFEST_PATH, encoded)
    if not written then
        return false, "backup_manifest_write_failed: " .. tostring(reason)
    end
    return true
end

-- --- verification -----------------------------------------------------------

--- Which tables a database at this schema version has to be able to answer for.
-- Pinned by floor: a version 1 copy has no `spatial_links` because version 1
-- had none, and a copy from any later version has to have it.
local function requiredTables(version)
    local required = {"schema_meta", "maps", "map_entities"}
    if version >= 3 then
        table.insert(required, "spatial_links")
    end
    return required
end

local function changeHistoryConsistent(connection)
    local exists, tables = execute(
        connection,
        "SELECT name FROM sqlite_master WHERE type = 'table' "
            .. "AND name = 'change_history_state'"
    )
    if not exists then
        return false, "backup_schema_unreadable"
    end
    if not tables[1] then
        -- Predates the Change History; nothing to be inconsistent with.
        return true
    end
    local ok, rows = execute(
        connection,
        [[
            SELECT
                state.cursor_id AS cursor_id,
                (SELECT COUNT(*) FROM change_history) AS entry_count,
                (SELECT COALESCE(MAX(history_id), 0) FROM change_history)
                    AS highest_id,
                (SELECT COUNT(*) FROM change_history
                    WHERE history_id = state.cursor_id) AS cursor_rows
            FROM change_history_state state
            WHERE state.singleton = 1
        ]]
    )
    if not ok or not rows[1] then
        return false, "backup_history_unreadable"
    end
    local cursor = tonumber(rows[1].cursor_id) or -1
    if cursor < 0 or cursor > (tonumber(rows[1].highest_id) or 0) then
        return false, "backup_history_cursor_out_of_range"
    end
    if cursor > 0 and (tonumber(rows[1].cursor_rows) or 0) ~= 1 then
        return false, "backup_history_cursor_dangling"
    end
    return true
end

--- Is this file a database ANKIGTA could actually run on?
-- Opening it is not enough and neither is `integrity_check`: a structurally
-- perfect file with a schema nothing here can read is not a recovery option.
function Backup.verify(path)
    if type(path) ~= "string" or not fileExists(path) then
        return false, "backup_missing"
    end
    local connection = connect(path)
    if not connection then
        return false, "backup_unreadable"
    end

    local integrityOk, integrityRows = execute(connection, "PRAGMA integrity_check")
    if not integrityOk or not integrityRows[1]
        or integrityRows[1].integrity_check ~= "ok"
    then
        disconnect(connection)
        return false, "backup_integrity_failed"
    end

    local versionOk, versionRows = execute(
        connection,
        "SELECT version FROM schema_meta WHERE singleton = 1"
    )
    if not versionOk or not versionRows[1] then
        disconnect(connection)
        return false, "backup_schema_missing"
    end
    local version = tonumber(versionRows[1].version)
    if not version
        or version < MINIMUM_SCHEMA_VERSION
        or version > Backup.currentSchemaVersion
    then
        disconnect(connection)
        return false, "backup_schema_unsupported"
    end

    for _, name in ipairs(requiredTables(version)) do
        local readable = execute(connection, "SELECT 1 FROM " .. name .. " LIMIT 1")
        if not readable then
            disconnect(connection)
            return false, "backup_table_unreadable"
        end
    end

    local constraintsOk, violations = execute(connection, "PRAGMA foreign_key_check")
    if not constraintsOk then
        disconnect(connection)
        return false, "backup_constraints_unreadable"
    end
    if violations[1] then
        disconnect(connection)
        return false, "backup_constraints_violated"
    end

    local historyOk, historyReason = changeHistoryConsistent(connection)
    disconnect(connection)
    if not historyOk then
        return false, historyReason
    end
    return {schemaVersion = version}
end

-- --- listing ----------------------------------------------------------------

local function verifiedEntry(entry)
    local details, reason = Backup.verify(entry.path)
    return {
        id = tonumber(entry.id) or 0,
        kind = entry.kind,
        day = entry.day,
        path = entry.path,
        createdAt = tonumber(entry.createdAt) or 0,
        schemaVersion = details and details.schemaVersion
            or tonumber(entry.schemaVersion) or false,
        verified = details and true or false,
        reason = details and false or (reason or "backup_verification_failed"),
    }
end

--- Every backup on disk, newest first, each with the answer to "can it be used".
function Backup.list()
    local manifest = readManifest()
    local listed = {}
    for _, entry in ipairs(manifest.entries) do
        if fileExists(entry.path) then
            table.insert(listed, verifiedEntry(entry))
        end
    end
    table.sort(listed, function(left, right)
        return (left.id or 0) > (right.id or 0)
    end)
    return listed
end

--- Databases kept back for diagnosis, newest first.
function Backup.quarantined()
    local manifest = readManifest()
    local kept = {}
    for _, entry in ipairs(manifest.quarantine) do
        if fileExists(entry.path) then
            table.insert(kept, {
                path = entry.path,
                reason = entry.reason or "database_corrupt",
                quarantinedAt = tonumber(entry.quarantinedAt) or 0,
            })
        end
    end
    table.sort(kept, function(left, right)
        return left.quarantinedAt > right.quarantinedAt
    end)
    return kept
end

-- --- rotation ---------------------------------------------------------------

local RETENTION = {daily = DAILY_RETENTION, premigration = PREMIGRATION_RETENTION}

--- Drop the copies past the retention for their kind, newest kept.
-- An entry whose file could not be deleted stays in the manifest. Forgetting a
-- file that is still on disk is how a backup directory grows without bound and
-- how a stale copy comes back as a recovery option later.
local function rotateEntries(manifest)
    local byKind = {}
    for _, entry in ipairs(manifest.entries) do
        byKind[entry.kind] = byKind[entry.kind] or {}
        table.insert(byKind[entry.kind], entry)
    end
    for _, entries in pairs(byKind) do
        table.sort(entries, function(left, right)
            return (tonumber(left.id) or 0) > (tonumber(right.id) or 0)
        end)
    end

    local kept = {}
    local failures = {}
    for _, entry in ipairs(manifest.entries) do
        local ranking = byKind[entry.kind] or {}
        local position = 0
        for index, candidate in ipairs(ranking) do
            if candidate == entry then
                position = index
                break
            end
        end
        local limit = RETENTION[entry.kind]
        local present = fileExists(entry.path)
        local expired = limit ~= nil and position > limit
        local retain = present and not expired
        if present and expired and not fileDelete(entry.path) then
            -- The file is still there; keeping the entry is what stops it
            -- becoming an untracked copy nothing will ever rotate again.
            table.insert(failures, entry.path)
            retain = true
        end
        if retain then
            table.insert(kept, entry)
        end
    end
    manifest.entries = kept
    if #failures > 0 then
        return false, "backup_rotation_delete_failed"
    end
    return true
end

--- Apply the retention policy on its own, outside a backup creation.
function Backup.rotate()
    local manifest = readManifest()
    local rotated, reason = rotateEntries(manifest)
    local written, writeReason = writeManifest(manifest)
    if not written then
        return false, writeReason
    end
    if not rotated then
        return false, reason
    end
    return true
end

-- --- creation ---------------------------------------------------------------

local function create(kind)
    local manifest = readManifest()
    local id = tonumber(manifest.nextId) or 1
    local finalPath = BACKUP_DIRECTORY
        .. "ankigta-" .. kind .. "-" .. tostring(id) .. ".sqlite"

    if not fileExists(Backup.databasePath) then
        return false, "backup_source_missing"
    end
    -- Anything left over from an attempt that did not finish.
    if fileExists(STAGING_PATH) then
        fileDelete(STAGING_PATH)
    end
    if not fileCopy(Backup.databasePath, STAGING_PATH, true) then
        -- A partial copy is not a backup and must not be left to be found.
        fileDelete(STAGING_PATH)
        return false, "backup_copy_failed"
    end

    local details, reason = Backup.verify(STAGING_PATH)
    if not details then
        fileDelete(STAGING_PATH)
        return false, reason or "backup_verification_failed"
    end

    -- The copy takes its listed name in one rename, after it has been opened
    -- as SQLite and verified. A run that stops between the rename and the
    -- manifest write leaves a complete file under a name nothing references;
    -- the next attempt reuses the same id, finds it and replaces it, so an
    -- interrupted backup costs one wasted copy rather than an unbounded pile.
    if fileExists(finalPath) then
        fileDelete(finalPath)
    end
    if not fileRename(STAGING_PATH, finalPath) then
        fileDelete(STAGING_PATH)
        return false, "backup_publish_failed"
    end

    local entry = {
        id = id,
        kind = kind,
        day = dayKey(),
        path = finalPath,
        createdAt = getTickCount(),
        schemaVersion = details.schemaVersion,
    }
    manifest.nextId = id + 1
    table.insert(manifest.entries, entry)
    local rotated, rotationReason = rotateEntries(manifest)
    local written, writeReason = writeManifest(manifest)
    if not written then
        return false, writeReason
    end
    if not rotated then
        return false, rotationReason
    end
    return entry
end

--- The copy taken before a migration touches anything.
function Backup.createPreMigration()
    return create("premigration")
end

--- At most one copy a day, taken after the data changed.
function Backup.createDaily()
    local today = dayKey()
    for _, entry in ipairs(readManifest().entries) do
        if entry.kind == "daily" and entry.day == today
            and fileExists(entry.path)
        then
            return entry
        end
    end
    return create("daily")
end

--- The data changed; a daily copy is due, but not on this call stack.
function Backup.noteDataChange()
    Backup.pendingDataChange = true
    if Backup.dailyTimer and isTimer(Backup.dailyTimer) then
        return true
    end
    Backup.dailyTimer = setTimer(function()
        Backup.dailyTimer = nil
        if not Backup.pendingDataChange then
            return
        end
        Backup.pendingDataChange = false
        local created, reason = Backup.createDaily()
        if not created then
            outputDebugString(
                "[ANKIGTA] daily_backup_failed: " .. tostring(reason),
                2
            )
        end
    end, DAILY_BACKUP_DELAY_MS, 1)
    return true
end

-- --- the restore journal ----------------------------------------------------

local function writeJournal(record)
    local encoded = toJSON(record, true)
    if type(encoded) ~= "string" then
        return false
    end
    return writeTextFile(JOURNAL_PATH, encoded) == true
end

local function clearJournal()
    if fileExists(JOURNAL_PATH) then
        fileDelete(JOURNAL_PATH)
    end
end

local function readJournal()
    local contents = readTextFile(JOURNAL_PATH)
    if type(contents) ~= "string" or contents == "" then
        return nil
    end
    local decoded = fromJSON(contents)
    if type(decoded) ~= "table" or type(decoded.phase) ~= "string" then
        -- A journal that cannot be read is itself a reason to stop and ask.
        return {phase = "unknown"}
    end
    return decoded
end

--- What an interrupted restore left behind, if anything.
-- The only thing this finishes on its own is the last rename of a restore the
-- user already asked for, and only when the primary path is empty so there is
-- nothing left to lose. Anything else is reported and left alone.
function Backup.recoverInterrupted()
    local journal = readJournal()
    if not journal then
        return false
    end
    if journal.phase == "quarantined"
        and type(journal.staged) == "string"
        and fileExists(journal.staged)
        and not fileExists(Backup.databasePath)
    then
        if fileRename(journal.staged, Backup.databasePath) then
            clearJournal()
            return {phase = "completed", quarantine = journal.quarantine or false}
        end
    end
    return {
        phase = journal.phase,
        staged = journal.staged or false,
        quarantine = journal.quarantine or false,
        backup = journal.backup or false,
        primaryPresent = fileExists(Backup.databasePath),
    }
end

-- --- quarantine and restore -------------------------------------------------

local function quarantinePath(manifest)
    local id = tonumber(manifest.nextId) or 1
    manifest.nextId = id + 1
    return BACKUP_DIRECTORY .. "quarantine-" .. tostring(id) .. ".sqlite"
end

--- Put the primary database beyond harm without destroying it.
-- Used on its own when the user wants the damaged file kept but has no copy to
-- restore; the restore path uses the same move.
function Backup.quarantinePrimary(reason)
    if not fileExists(Backup.databasePath) then
        return false, "quarantine_source_missing"
    end
    local manifest = readManifest()
    local destination = quarantinePath(manifest)
    if not fileRename(Backup.databasePath, destination) then
        return false, "quarantine_failed"
    end
    table.insert(manifest.quarantine, {
        path = destination,
        reason = reason or "database_corrupt",
        quarantinedAt = getTickCount(),
    })
    writeManifest(manifest)
    return destination
end

--- Restore one backup the user chose.
--
-- The order is what makes a failure survivable. The copy is staged and verified
-- while the original is still in place, so anything that goes wrong before that
-- point has touched nothing. Only then is the original moved aside -- moved,
-- never deleted -- and only then does the staged copy take its name. The source
-- backup is never renamed or removed at any point, so whatever happens there is
-- always one intact copy of the original and one intact copy of the backup.
function Backup.restore(backupId)
    local manifest = readManifest()
    local chosen = nil
    for _, entry in ipairs(manifest.entries) do
        if tostring(entry.id) == tostring(backupId) then
            chosen = entry
            break
        end
    end
    if not chosen then
        return false, "backup_not_found"
    end
    if not fileExists(chosen.path) then
        return false, "backup_missing"
    end

    local details, reason = Backup.verify(chosen.path)
    if not details then
        return false, reason or "backup_verification_failed"
    end

    if fileExists(STAGING_PATH) then
        fileDelete(STAGING_PATH)
    end
    if not fileCopy(chosen.path, STAGING_PATH, true) then
        fileDelete(STAGING_PATH)
        return false, "restore_copy_failed"
    end
    -- Verify the copy, not only its source: the bytes that will become the
    -- database are these ones.
    local stagedDetails, stagedReason = Backup.verify(STAGING_PATH)
    if not stagedDetails then
        fileDelete(STAGING_PATH)
        return false, stagedReason or "restore_verification_failed"
    end

    local quarantine = quarantinePath(manifest)
    if not writeJournal({
        phase = "staged",
        staged = STAGING_PATH,
        quarantine = quarantine,
        backup = chosen.path,
        primary = Backup.databasePath,
    }) then
        fileDelete(STAGING_PATH)
        return false, "restore_journal_failed"
    end

    if fileExists(Backup.databasePath) then
        if not fileRename(Backup.databasePath, quarantine) then
            -- The original is still where it was and the staged copy is still
            -- a file; both are recoverable, and the journal says so.
            return false, "restore_quarantine_failed"
        end
        table.insert(manifest.quarantine, {
            path = quarantine,
            reason = "replaced_by_restore",
            quarantinedAt = getTickCount(),
        })
    end
    writeJournal({
        phase = "quarantined",
        staged = STAGING_PATH,
        quarantine = quarantine,
        backup = chosen.path,
        primary = Backup.databasePath,
    })

    if not fileRename(STAGING_PATH, Backup.databasePath) then
        writeManifest(manifest)
        return false, "restore_publish_failed"
    end
    clearJournal()
    writeManifest(manifest)
    return {
        restored = chosen.path,
        quarantine = quarantine,
        schemaVersion = stagedDetails.schemaVersion,
    }
end

ANKIGTA.Backup = Backup
