"""What ANKIGTA may ask the stock `edf` resource, and from which side.

`edf` exports two different sets. Its server half exports thirty-odd
functions; its client half exports twenty-one, all of them about an element's
geometry. `edfIsRepresentation` is in the first set and not the second.

The client asked for it anyway. MTA answers a call to an export that side does
not have by logging `call: failed to call 'edf:edfIsRepresentation'` and
returning nothing -- it does not raise, so the `pcall` around it reported
success, the answer came back falsy, and the caller read that as "not a
representation". Every call. The filter it guarded never fired, and the client
log took two thousand errors a minute while it did not.

Nothing in the suite saw it: `tests/lua/sandbox.py` offers one `exports.edf`
table to whatever asks, which is one side more than MTA offers. Rather than
teach the double which half of a resource is calling it, the rule is the one
ANKIGTA actually needs -- the client does not call into `edf` at all -- and it
is read out of the compiled chunk, where a call's export name is a constant.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ElementTree
from pathlib import Path

import pytest

from tests.lua.constants import string_constants


RESOURCE = Path(__file__).resolve().parents[1] / "mta" / "ankigta"
#: `exports.edf:edfIsRepresentation(x)` compiles the method name to a constant.
EDF_FUNCTION = re.compile(r"^edf[A-Z]\w*$")


def scripts_of(*sides: str) -> list[Path]:
    manifest = ElementTree.parse(RESOURCE / "meta.xml")
    return [
        RESOURCE / str(element.get("src"))
        for element in manifest.iter("script")
        if element.get("type") in sides
    ]


def edf_functions_named_by(script: Path) -> list[str]:
    return sorted(
        {
            value
            for value in string_constants(script)
            if EDF_FUNCTION.match(value)
        }
    )


@pytest.mark.parametrize(
    "script",
    [pytest.param(path, id=path.name) for path in scripts_of("client", "shared")],
)
def test_no_client_script_calls_into_edf(script: Path) -> None:
    """The one function the client wanted from `edf` is server-only.

    A shared script counts as a client script here, because it runs there too.
    """
    called = edf_functions_named_by(script)

    assert called == [], (
        f"{script.relative_to(RESOURCE)} calls {called} on the client, where "
        "`edf` exports only its geometry helpers. MTA logs "
        "`call: failed to call` and answers nothing, which reads as a plain "
        "`false` at the call site. Read the element data `edf` itself reads, "
        "or ask the server."
    )


def test_the_server_still_asks_edf_the_things_only_it_can_answer() -> None:
    """The rule above is about the client, not about `edf`.

    Without this, deleting the last server call would pass the guard and read
    as compliance rather than as the loss it would be.
    """
    named = set()
    for script in scripts_of("server"):
        named.update(edf_functions_named_by(script))

    assert "edfIsRepresentation" in named
    assert "edfSetElementProperty" in named
