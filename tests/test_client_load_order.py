"""A client script may not read the shared schema while its chunk loads.

MTA hands a running client a changed `cache="false"` script one restart before
a changed or newly added shared one. The client scripts are all `cache="false"`
and every shared script is not, so there is a window on every incremental
reload in which `client/*.lua` runs and `ANKIGTA.Settings` is not there yet.

`client/panel.lua` already guards `ANKIGTA.EntityTypes` against exactly this,
with a comment saying so. Ticket 05 then added
`bindKey(schema().reservedKeys.panel, ...)` at chunk level, which read the
schema at load time -- and a Lua chunk that errors stops. Everything below that
line stopped registering with it, which meant F7 *and*
`/ankigta-connection`, the two ways into the panel, went at once. It shipped
that way and the owner found it by pressing F7 and getting nothing.

So the rule is checked rather than remembered: load each client script with the
shared modules absent, and require it not to raise.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator
from xml.etree import ElementTree

import pytest

from tests.lua import MtaSandbox


REPO_ROOT = Path(__file__).resolve().parents[1]


def manifest_scripts(*kinds: str) -> list[str]:
    manifest = ElementTree.parse(REPO_ROOT / "mta" / "ankigta" / "meta.xml")
    return [
        str(element.get("src"))
        for element in manifest.iter("script")
        if element.get("type") in kinds
    ]


@pytest.fixture
def client() -> Iterator[MtaSandbox]:
    sandbox = MtaSandbox()
    try:
        for script in manifest_scripts("shared", "client"):
            sandbox.load(script)
        sandbox.trigger("onClientResourceStart")
        yield sandbox
    finally:
        sandbox.close()


@pytest.mark.parametrize("script", manifest_scripts("client"))
def test_a_client_script_loads_without_the_shared_modules(script: str) -> None:
    """The incremental-reload window, reproduced: client scripts, no shared."""
    sandbox = MtaSandbox()
    try:
        sandbox.load(script)
    finally:
        sandbox.close()


def test_the_panel_key_is_bound_once_the_resource_has_started(
    client: MtaSandbox,
) -> None:
    reserved = client.eval(
        "function() return ANKIGTA.Settings.reservedKeys.panel end"
    )()
    assert client.bound_keys.get((reserved, "down")), (
        f"nothing is bound to {reserved}: the panel cannot be opened"
    )


def test_the_panel_names_a_key_even_with_the_schema_absent() -> None:
    """What the binding asks for, asked with nothing to ask.

    Not a whole resource start with the shared scripts missing: the client does
    get them, only later than the `cache="false"` ones, and other modules are
    entitled to read the schema from their start handler. What is pinned here
    is narrower and is the thing that broke -- the panel names a key rather
    than raising, whatever the schema is doing.
    """
    sandbox = MtaSandbox()
    try:
        for script in manifest_scripts("client"):
            sandbox.load(script)
        key, fallback = sandbox.eval(
            "function() return ANKIGTA.Panel.key(), ANKIGTA.Panel.fallbackKey end"
        )()
        assert key == fallback
    finally:
        sandbox.close()


def test_the_fallback_is_the_key_the_schema_reserves(client: MtaSandbox) -> None:
    """A fallback that opens a different key from the reserved one is worse
    than no fallback: it would bind a key `activationKey` is still free to
    take."""
    reserved, fallback = client.eval(
        """
        function()
            return ANKIGTA.Settings.reservedKeys.panel, ANKIGTA.Panel.fallbackKey
        end
        """
    )()
    assert fallback == reserved


def test_the_way_in_by_command_survives_the_same_window() -> None:
    """`/ankigta-connection` is the answer to "the key is bound to something
    else or the panel is the thing that is wrong", so it has to outlive
    whatever took the key binding down.

    It is registered below the line that used to raise, which is how both ways
    into the panel went at once. Loading the chunk alone is the check: the
    handler exists by the end of the file or it does not.
    """
    sandbox = MtaSandbox()
    try:
        for script in manifest_scripts("client"):
            sandbox.load(script)
        assert "ankigta-connection" in sandbox.commands
    finally:
        sandbox.close()
