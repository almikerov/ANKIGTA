"""Read the string constants a Lua chunk actually holds.

A localization check that greps the `.lua` file answers the wrong question. It
sees strings inside comments, misses strings built by concatenation across two
lines, and passes the moment someone reformats the file. What decides whether a
player reads a hard-coded sentence is the constant table the compiler produced,
so that is what this module reads: it asks the same Lua 5.1 interpreter the
resource runs on to `string.dump` the chunk, then walks the constants out of the
bytecode.

The layout is Lua 5.1's `lundump.c`:

- a 12-byte header: `\\x1bLua`, version, format, endianness, and the sizes of
  `int`, `size_t`, `Instruction` and `lua_Number`, then the integral flag;
- then one function block, nested: source name, line range, upvalue/parameter
  counts, the code array, the constant array, the nested prototypes, and the
  debug tables.

Constants are tagged `0` nil, `1` boolean, `3` number and `4` string, and a
dumped string carries its terminating NUL inside its length.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from lupa.lua51 import LuaRuntime


LUA_SIGNATURE = b"\x1bLua"
LUA_TNIL = 0
LUA_TBOOLEAN = 1
LUA_TNUMBER = 3
LUA_TSTRING = 4


class BytecodeError(AssertionError):
    """The dumped chunk did not match the Lua 5.1 layout."""


@dataclass
class _Header:
    little_endian: bool
    size_t: int
    size_int: int
    size_instruction: int
    size_number: int


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.at = 0

    def take(self, count: int) -> bytes:
        if self.at + count > len(self.data):
            raise BytecodeError("dumped chunk ended early")
        chunk = self.data[self.at : self.at + count]
        self.at += count
        return chunk

    def byte(self) -> int:
        return self.take(1)[0]


def _read_header(reader: _Reader) -> _Header:
    if reader.take(4) != LUA_SIGNATURE:
        raise BytecodeError("not a dumped Lua chunk")
    version = reader.byte()
    if version != 0x51:
        raise BytecodeError(f"expected Lua 5.1 bytecode, got version {version:#x}")
    reader.byte()  # format: 0 is the official one
    little_endian = reader.byte() == 1
    size_int = reader.byte()
    size_t = reader.byte()
    size_instruction = reader.byte()
    size_number = reader.byte()
    reader.byte()  # integral flag: 0 when lua_Number is a float
    return _Header(
        little_endian=little_endian,
        size_t=size_t,
        size_int=size_int,
        size_instruction=size_instruction,
        size_number=size_number,
    )


def _integer(reader: _Reader, width: int, little_endian: bool) -> int:
    return int.from_bytes(reader.take(width), "little" if little_endian else "big")


def _string(reader: _Reader, header: _Header) -> str | None:
    length = _integer(reader, header.size_t, header.little_endian)
    if length == 0:
        return None
    # The dumped length counts the terminating NUL the compiler added.
    return reader.take(length)[:-1].decode("utf-8", errors="surrogateescape")


def _read_function(reader: _Reader, header: _Header, into: list[str]) -> None:
    read_int = lambda: _integer(reader, header.size_int, header.little_endian)

    _string(reader, header)  # source
    read_int()  # line defined
    read_int()  # last line defined
    reader.byte()  # upvalues
    reader.byte()  # parameters
    reader.byte()  # is_vararg
    reader.byte()  # max stack size

    reader.take(read_int() * header.size_instruction)  # code

    for _ in range(read_int()):  # constants
        tag = reader.byte()
        if tag == LUA_TNIL:
            continue
        if tag == LUA_TBOOLEAN:
            reader.byte()
        elif tag == LUA_TNUMBER:
            reader.take(header.size_number)
        elif tag == LUA_TSTRING:
            value = _string(reader, header)
            if value is not None:
                into.append(value)
        else:
            raise BytecodeError(f"unknown constant tag {tag}")

    for _ in range(read_int()):  # nested prototypes
        _read_function(reader, header, into)

    reader.take(read_int() * header.size_int)  # line info
    for _ in range(read_int()):  # local variables
        _string(reader, header)
        read_int()
        read_int()
    for _ in range(read_int()):  # upvalue names
        _string(reader, header)


def string_constants(path: Path) -> list[str]:
    """Every string constant the compiled chunk holds, nested functions included.

    Comments are gone by this point, and a string split across source lines with
    `..` arrives as its two halves — which is the honest answer, because that is
    what the interpreter holds.
    """
    # `encoding=None` keeps Lua strings as bytes on the way back: bytecode is
    # not text, and decoding it as UTF-8 would fail on the first opcode.
    lua = LuaRuntime(unpack_returned_tuples=True, encoding=None)
    source = path.read_bytes()
    chunk = lua.eval(b"loadstring")(source, b"@" + path.name.encode("utf-8"))
    if chunk is None:
        raise BytecodeError(f"could not compile {path}")
    dumped = lua.eval(b"string.dump")(chunk)

    reader = _Reader(dumped)
    header = _read_header(reader)
    found: list[str] = []
    _read_function(reader, header, found)
    return found
