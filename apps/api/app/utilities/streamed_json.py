"""The complete parts of a JSON object whose text is still arriving.

A model streams its structured answer as text, one fragment at a time. `closed_items` reads the
text received so far and returns, for each top-level property whose value is an array, the
object items of that array whose closing brace has arrived, parsed. An item still open, a
property whose value is not an array, and anything after a malformed item are left out, so the
result only ever holds whole items, in the order the text gives them.
"""

from __future__ import annotations

import json
from typing import Any


def closed_items(text: str) -> dict[str, list[Any]]:
    """The whole object items of each top-level array property of the JSON object `text`
    begins, by property name; an array with no whole item yet maps to an empty list."""
    items: dict[str, list[Any]] = {}
    depth = 0
    in_string = escaped = False
    string_start = 0
    expecting_key = False
    key: str | None = None
    array_key: str | None = None
    item_start = -1
    for i, c in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                in_string = False
                if depth == 1 and expecting_key:
                    key = json.loads(text[string_start : i + 1])
                    expecting_key = False
            continue
        if c == '"':
            in_string = True
            string_start = i
        elif c in "{[":
            depth += 1
            if depth == 1:
                if c != "{":
                    return items
                expecting_key = True
            elif depth == 2 and c == "[" and key is not None:
                array_key = key
                items.setdefault(key, [])
            elif depth == 3 and array_key is not None and c == "{":
                item_start = i
        elif c in "}]":
            if depth == 3 and c == "}" and array_key is not None and item_start >= 0:
                try:
                    items[array_key].append(json.loads(text[item_start : i + 1]))
                except ValueError:
                    return items
                item_start = -1
            elif depth == 2 and c == "]":
                array_key = None
            depth -= 1
            if depth <= 0:
                return items
        elif c == "," and depth == 1:
            expecting_key = True
    return items
