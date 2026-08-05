"""
Minimal Python port of devalue's `unflatten` — enough to read a Nuxt 3
`__NUXT_DATA__` SSR payload (see cinestar.py, the one cinema that needs it).

The payload is a flat JSON array: index 0 is the root reference, and every
other element is either a primitive, a plain array/object whose own values
are indices back into this same array, or a `[typeTag, ...]` tuple for a
handled type (Date, Set, Map, RegExp, BigInt) or a Nuxt/Vue reactivity
wrapper (Ref, Reactive, ShallowReactive, ShallowRef, and their readonly
variants). The wrappers just unwrap to their pointed-at value — real Vue
reactivity semantics don't matter here, only the underlying data does.

Verified against devalue's own source (Rich-Harris/devalue, src/parse.js)
rather than guessed, since getting the reference-resolution order wrong
silently produces plausible-looking garbage instead of an error.
"""

from __future__ import annotations

from typing import Any

_UNSET = object()

# Nuxt/Vue reactivity wrappers: unwrap to hydrate(value[1]) with no further
# transform, since we only want the underlying data, not real reactive
# object identity.
_IDENTITY_TAGS = {
    "Ref", "Reactive", "ShallowReactive", "ShallowRef",
    "Readonly", "ReadonlyReactive", "Computed",
}


def unflatten(values: list) -> Any:
    """Deserialize a devalue-flattened array (a parsed __NUXT_DATA__ payload)."""
    hydrated: list = [_UNSET] * len(values)

    def hydrate(index: int) -> Any:
        if hydrated[index] is not _UNSET:
            return hydrated[index]
        value = values[index]

        if value is None or not isinstance(value, (list, dict)):
            hydrated[index] = value
            return value

        if isinstance(value, list):
            if value and isinstance(value[0], str):
                tag = value[0]
                if tag in _IDENTITY_TAGS or tag == "Set":
                    if len(value) < 2:
                        # e.g. a bare ["Set"] for an empty collection/wrapper —
                        # Nuxt's own "once" effect-tracking set is one of these.
                        result = [] if tag == "Set" else None
                        hydrated[index] = result
                        return result
                    hydrated[index] = None  # placeholder, breaks reference cycles
                    result = hydrate(value[1])
                    hydrated[index] = result
                    return result
                if tag == "Date":
                    hydrated[index] = value[1]  # ISO string is good enough here
                    return value[1]
                if tag == "Map":
                    pairs = hydrate(value[1]) if len(value) > 1 else []
                    result = {pair[0]: pair[1] for pair in pairs}
                    hydrated[index] = result
                    return result
                if tag in ("RegExp", "BigInt"):
                    result = value[1] if len(value) > 1 else None
                    hydrated[index] = result
                    return result
                # Not a recognized type tag — don't crash a daily unattended
                # scrape over an unhandled devalue extension; surface it so
                # it's visible in output instead of silently wrong.
                result = {"__unhandled_devalue_tag__": tag, "raw": value}
                hydrated[index] = result
                return result

            # Plain array: its own items are indices.
            result = []
            hydrated[index] = result
            for i in value:
                result.append(hydrate(i))
            return result

        # Plain object: its own values are indices.
        result = {}
        hydrated[index] = result
        for key, i in value.items():
            result[key] = hydrate(i)
        return result

    return hydrate(0)
