from __future__ import annotations

from pathlib import Path

from lupa.lua51 import LuaRuntime


PROBE = (
    Path(__file__).parents[1]
    / "tools"
    / "devserver"
    / "ankigta_probe"
    / "server.lua"
)


def test_acl_check_answers_through_the_probe_command_file() -> None:
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(
        r'''
        files = {}
        resourceRoot = {}
        root = {}

        function fileExists(path)
            return files[path] ~= nil
        end

        local function handle(path)
            return {path = path, position = 0}
        end

        function fileCreate(path)
            files[path] = ""
            return handle(path)
        end

        function fileDelete(path)
            files[path] = nil
            return true
        end

        function fileOpen(path)
            if files[path] == nil then
                return false
            end
            return handle(path)
        end

        function fileGetSize(opened)
            return string.len(files[opened.path])
        end

        function fileRead(opened, size)
            local first = opened.position + 1
            local value = string.sub(files[opened.path], first, first + size - 1)
            opened.position = opened.position + string.len(value)
            return value
        end

        function fileSetPos(opened, position)
            opened.position = position
            return true
        end

        function fileWrite(opened, value)
            local current = files[opened.path]
            local before = string.sub(current, 1, opened.position)
            local after = string.sub(current, opened.position + string.len(value) + 1)
            files[opened.path] = before .. value .. after
            opened.position = opened.position + string.len(value)
            return true
        end

        function fileClose()
            return true
        end

        function getResourceFromName(name)
            return {name = name}
        end

        function hasObjectPermissionTo(_, right)
            return right == "general.ModifyOtherObjects"
        end

        function addEventHandler(name, _, callback)
            if name == "onResourceStart" then
                start_handler = callback
            end
            return true
        end

        function setTimer(callback, _, repeats)
            if repeats == 0 then
                poll_callback = callback
            end
            return {callback = callback}
        end

        function addCommandHandler()
            return true
        end
        '''
    )
    lua.execute(PROBE.read_text(encoding="utf-8"))
    lua.globals().start_handler()
    lua.globals().files["@command.txt"] = "acl-check ankigta"

    lua.globals().poll_callback()

    result = str(lua.globals().files["@result.txt"])
    permission_lines = [line for line in result.splitlines() if line.startswith("  ")]
    assert permission_lines[0].endswith("general.ModifyOtherObjects         yes")
    assert permission_lines[1].endswith("general.http                       NO")
    assert len(permission_lines) == 9
