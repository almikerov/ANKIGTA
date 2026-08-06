"""Panel rebuild 06 — what a Text Label says, between a note and a drawn line.

The three decisions `shared/text_label.lua` owns: which field a label shows
when the chosen one cannot be shown, what is left of a field once Anki's markup
is off it, and where a long answer stops. None of them needs a world, a store
or a companion, so all of them are asked here directly.

Executed in the same Lua 5.1 the resource runs in, so the UTF-8 walk is the one
that will really cut a line in the game rather than Python's idea of a string.
"""

from __future__ import annotations

from typing import Any, Iterator

import pytest

from tests.lua import MtaSandbox


@pytest.fixture
def lua() -> Iterator[MtaSandbox]:
    sandbox = MtaSandbox()
    try:
        sandbox.load("shared/text_label.lua")
        yield sandbox
    finally:
        sandbox.close()


def plain(sandbox: MtaSandbox, value: Any) -> str:
    return str(
        sandbox.eval(
            "function(value) return ANKIGTA.TextLabel.plainText(value) end"
        )(value)
    )


def fields(sandbox: MtaSandbox, pairs: list[tuple[str, str]]) -> Any:
    return sandbox.lua.table_from(
        [
            sandbox.lua.table_from({"name": name, "value": value})
            for name, value in pairs
        ]
    )


def choose(
    sandbox: MtaSandbox, pairs: list[tuple[str, str]], requested: str = ""
) -> dict[str, Any]:
    return dict(
        sandbox.to_python(
            sandbox.eval(
                """
                function(fields, requested)
                    return ANKIGTA.TextLabel.choose(fields, requested)
                end
                """
            )(fields(sandbox, pairs), requested)
        )
    )


def wrap(
    sandbox: MtaSandbox, text: str, width: int = 28, lines: int = 3
) -> dict[str, Any]:
    answer = sandbox.to_python(
        sandbox.eval(
            """
            function(text, width, lines)
                return ANKIGTA.TextLabel.wrap(text, width, lines)
            end
            """
        )(text, width, lines)
    )
    result = dict(answer)
    got = result.get("lines")
    result["lines"] = [] if got in (None, False) else list(got)
    return result


# --- what is left of a field ------------------------------------------------


def test_markup_becomes_a_space_rather_than_nothing(lua: MtaSandbox) -> None:
    """`one<br>two` is two words. Deleting the tag outright draws `onetwo`."""
    assert plain(lua, "one<br>two") == "one two"
    assert plain(lua, "<b>bold</b> text") == "bold text"


def test_a_field_holding_only_media_has_no_words(lua: MtaSandbox) -> None:
    """Which is what makes it fall through rather than merely be short."""
    assert plain(lua, '<img src="a.png">') == ""
    assert plain(lua, "[sound:hello.mp3]") == ""
    assert plain(lua, "[anki:play:q:0]") == ""
    assert (
        lua.eval("function(v) return ANKIGTA.TextLabel.hasWords(v) end")(
            "[sound:hello.mp3]"
        )
        is False
    )


def test_entities_are_decoded_including_numeric_ones(lua: MtaSandbox) -> None:
    assert plain(lua, "a &amp; b") == "a & b"
    assert plain(lua, "&lt;tag&gt;") == "<tag>"
    assert plain(lua, "&#72;&#105;") == "Hi"
    assert plain(lua, "&#x4F60;&#x597D;") == "你好"


def test_non_breaking_space_collapses_like_any_other_space(
    lua: MtaSandbox,
) -> None:
    """A field pasted out of a browser carries them, and a line that starts
    with one looks wrongly indented."""
    assert plain(lua, "a b") == "a b"
    assert plain(lua, "&nbsp;&nbsp;") == ""


def test_an_unknown_entity_is_left_alone_rather_than_guessed_at(
    lua: MtaSandbox,
) -> None:
    assert plain(lua, "&copy;") == "&copy;"


# --- which field ------------------------------------------------------------


def test_no_field_asked_for_takes_the_first_one_with_words(
    lua: MtaSandbox,
) -> None:
    chosen = choose(lua, [("Front", ""), ("Back", "answer")], "")

    assert chosen["text"] == "answer"
    assert chosen["fieldName"] == "Back"
    assert chosen["fallback"] is False


def test_the_field_asked_for_is_the_one_shown(lua: MtaSandbox) -> None:
    chosen = choose(lua, [("Front", "question"), ("Back", "answer")], "Back")

    assert chosen["text"] == "answer"
    assert chosen["fieldName"] == "Back"
    assert chosen["fallback"] is False
    assert chosen["reason"] is False


def test_a_field_this_note_type_lacks_falls_through_and_says_so(
    lua: MtaSandbox,
) -> None:
    chosen = choose(lua, [("Front", "question")], "Meaning")

    assert chosen["text"] == "question"
    assert chosen["fieldName"] == "Front"
    assert chosen["fallback"] is True
    assert chosen["reason"] == "field_missing"
    # And it still remembers what was asked for, so the panel can name both.
    assert chosen["requestedField"] == "Meaning"


def test_a_field_holding_only_media_falls_through_and_says_which(
    lua: MtaSandbox,
) -> None:
    """A different reason from a missing field: the field is there, and the
    player's answer about it was not wrong -- there is simply nothing to read
    in it."""
    chosen = choose(
        lua,
        [("Front", '<img src="a.png">'), ("Back", "answer")],
        "Front",
    )

    assert chosen["text"] == "answer"
    assert chosen["fieldName"] == "Back"
    assert chosen["fallback"] is True
    assert chosen["reason"] == "field_wordless"


def test_a_note_with_no_words_at_all_says_so_and_shows_nothing(
    lua: MtaSandbox,
) -> None:
    chosen = choose(lua, [("Front", ""), ("Back", "[sound:a.mp3]")], "Front")

    assert chosen["text"] == ""
    assert chosen["fieldName"] == ""
    assert chosen["reason"] == "no_words"


def test_the_first_field_with_words_is_the_note_types_own_order(
    lua: MtaSandbox,
) -> None:
    """"First" is a question about the order the note type declares, which is
    why the cache keeps fields as a list rather than as a mapping."""
    chosen = choose(lua, [("Back", "second"), ("Front", "first")], "")

    assert chosen["fieldName"] == "Back"


# --- where it stops ---------------------------------------------------------


def test_short_text_is_one_line_and_says_nothing_was_dropped(
    lua: MtaSandbox,
) -> None:
    assert wrap(lua, "short answer") == {
        "lines": ["short answer"],
        "truncated": False,
    }


def test_wrapping_happens_between_words(lua: MtaSandbox) -> None:
    wrapped = wrap(lua, "one two three four five six seven", width=10)

    assert wrapped["lines"][:2] == ["one two", "three four"]
    # And what did not fit is said, not implied: `seven` is off the end.
    assert wrapped["lines"][2] == "five six…"
    assert wrapped["truncated"] is True


def test_no_character_class_answers_about_the_c_locale(lua: MtaSandbox) -> None:
    """`%s` is `isspace`, and in a Windows-1252 locale `isspace(0xA0)` is true.

    0xA0 is the last byte of U+4F60, so collapsing whitespace with `%s+` ate
    it and handed the renderer two bytes and half a character. Found in this
    harness on the first note that was not ASCII.
    """
    assert plain(lua, "你好 世界") == "你好 世界"
    assert plain(lua, "  你好  ") == "你好"
    assert wrap(lua, "你好 世界", width=8)["lines"] == ["你好 世界"]


def test_past_the_line_limit_the_last_line_ends_in_an_ellipsis(
    lua: MtaSandbox,
) -> None:
    """A line that simply stops reads as the whole answer, and a player who
    read half an answer and thought they read all of it has been told
    something false."""
    wrapped = wrap(lua, "alpha bravo charlie delta echo foxtrot", width=12)

    assert wrapped["truncated"] is True
    assert wrapped["lines"][-1].endswith("…")
    assert len(wrapped["lines"]) == 3


def test_the_ellipsis_fits_inside_the_line_rather_than_past_it(
    lua: MtaSandbox,
) -> None:
    """Otherwise the one line that says something was left out is the one line
    that runs off the side of the screen."""
    wrapped = wrap(lua, "aaaa bbbb cccc dddd eeee ffff gggg", width=9)

    for line in wrapped["lines"]:
        assert (
            lua.eval("function(s) return ANKIGTA.TextLabel.characterCount(s) end")(
                line
            )
            <= 9
        )


def test_a_word_longer_than_a_line_is_broken_rather_than_overrun(
    lua: MtaSandbox,
) -> None:
    """One unbroken word is a label that reaches off the side of the screen."""
    wrapped = wrap(lua, "abcdefghijklmnopqrstuvwxyz", width=10, lines=3)

    assert wrapped["lines"][0] == "abcdefghij"
    assert wrapped["lines"][1] == "klmnopqrst"


def test_a_line_is_measured_in_characters_not_bytes(lua: MtaSandbox) -> None:
    """`#` counts bytes in Lua 5.1, so a byte limit cuts a two-byte letter in
    half and hands the renderer a broken character."""
    wrapped = wrap(lua, "你好世界", width=3, lines=2)

    # Four characters at three per line: the second line holds the fourth, and
    # neither is half a character.
    assert wrapped["lines"][0] == "你好世"
    assert wrapped["lines"][1] == "界"


def test_nothing_to_say_wraps_to_no_lines_at_all(lua: MtaSandbox) -> None:
    """There is no such thing as an empty Text Label: an object wearing a blank
    line reads as broken."""
    assert wrap(lua, "")["lines"] == []


def test_build_chooses_then_wraps_in_one_call(lua: MtaSandbox) -> None:
    built = lua.to_python(
        lua.eval(
            """
            function(f)
                return ANKIGTA.TextLabel.build(f, "Meaning", 8, 2)
            end
            """
        )(fields(lua, [("Front", "one two three four five")]))
    )

    assert built["fallback"] is True
    assert built["reason"] == "field_missing"
    assert list(built["lines"])[0] == "one two"
    assert built["truncated"] is True
