"""The strict structured-output form of a JSON schema, and the answer mapped back from it.

Strict structured outputs require every property of every object to be listed in `required`.
`to_strict` lists them all and makes each optional property nullable instead, so the model
writes `null` where it would have left the property out. `drop_optional_nulls` removes those
`null` values again, so the answer has the shape of the original schema. It drops `null` only
under property names that are optional somewhere in the original schema; a schema where the same
name is required and nullable elsewhere would need a path-aware mapping instead.
`drop_optional_empties` does the same for empty strings and lists, which a model whose
structured outputs keep optional properties optional writes for properties it means to leave
out.

`to_required_form` is a variant for providers that cap the number of union-typed properties a
schema may hold (Claude allows 16): every property is required too, but an optional string or
array property keeps its type and is written empty when unset (an enum also accepts ""), and
only the other optional properties become nullable. `drop_optional_nulls` and
`drop_optional_empties` together map its answers back.
"""

from __future__ import annotations

import copy
from typing import Any


def to_strict(schema: dict[str, Any]) -> tuple[dict[str, Any], frozenset[str]]:
    """The strict form of `schema` and the names of the properties that were optional."""
    optional: set[str] = set()
    strict = _strict_node(copy.deepcopy(schema), optional)
    return strict, frozenset(optional)


def to_required_form(schema: dict[str, Any]) -> tuple[dict[str, Any], frozenset[str]]:
    """The required form of `schema` and the names of the properties that were optional."""
    optional: set[str] = set()
    required = _strict_node(copy.deepcopy(schema), optional, empty_when_unset=True)
    return required, frozenset(optional)


def drop_optional_nulls(value: Any, optional: frozenset[str]) -> Any:
    """`value` without the `null` members whose names are in `optional`, at every depth."""
    if isinstance(value, list):
        return [drop_optional_nulls(item, optional) for item in value]
    if isinstance(value, dict):
        return {
            key: drop_optional_nulls(item, optional)
            for key, item in value.items()
            if not (item is None and key in optional)
        }
    return value


def drop_optional_empties(value: Any, optional: frozenset[str]) -> Any:
    """`value` without the empty-string and empty-list members whose names are in `optional`,
    at every depth."""
    if isinstance(value, list):
        return [drop_optional_empties(item, optional) for item in value]
    if isinstance(value, dict):
        return {
            key: drop_optional_empties(item, optional)
            for key, item in value.items()
            if not (key in optional and (item == "" or item == []))
        }
    return value


def _strict_node(node: Any, optional: set[str], empty_when_unset: bool = False) -> Any:
    if isinstance(node, list):
        return [_strict_node(item, optional, empty_when_unset) for item in node]
    if not isinstance(node, dict):
        return node
    for key in ("properties", "$defs"):
        if isinstance(node.get(key), dict):
            node[key] = {
                name: _strict_node(sub, optional, empty_when_unset)
                for name, sub in node[key].items()
            }
    for key, sub in list(node.items()):
        if key not in ("properties", "$defs"):
            node[key] = _strict_node(sub, optional, empty_when_unset)
    properties = node.get("properties")
    if isinstance(properties, dict):
        required = set(node.get("required", ()))
        for name, sub in properties.items():
            if name not in required:
                optional.add(name)
                if empty_when_unset and _can_be_empty(sub):
                    if "enum" in sub and "" not in sub["enum"]:
                        sub["enum"] = [*sub["enum"], ""]
                elif not _nullable(sub):
                    properties[name] = {"anyOf": [sub, {"type": "null"}]}
        node["required"] = list(properties)
        node["additionalProperties"] = False
    return node


def _can_be_empty(schema: Any) -> bool:
    return isinstance(schema, dict) and schema.get("type") in ("string", "array")


def _nullable(schema: Any) -> bool:
    if not isinstance(schema, dict):
        return False
    kind = schema.get("type")
    if kind == "null" or (isinstance(kind, list) and "null" in kind):
        return True
    return any(_nullable(option) for option in schema.get("anyOf", ()))
