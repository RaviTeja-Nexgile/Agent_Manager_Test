"""Shared Pydantic base and helpers for API schemas."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    """Base for response models read from ORM objects."""

    model_config = ConfigDict(from_attributes=True)


def selected_values(value_text: str | None, value_json: Any | None) -> list[Any] | None:
    """Interpret a multi-select attribute payload as a list of selections (GAP-PCR-04).

    A capped attribute is normally written as a JSON list. A single scalar (or a
    plain ``value_text``) is a legitimate one-selection write, so it counts as
    one rather than being rejected — a caller should not have to wrap a lone
    code in a list to satisfy the validator.

    Returns ``None`` when there is nothing to count, so callers can tell "no
    selections supplied" apart from "zero selections": the former skips the cap
    check entirely.

    Lives here rather than in ``features.crashes`` because both the API write
    path and the QC worker must agree on what counts as a selection, and
    ``workers.tasks`` cannot import from ``features.crashes`` (that module
    already imports the workers).
    """
    if isinstance(value_json, list):
        return value_json
    if value_json is not None:
        return [value_json]
    if value_text is not None and value_text != "":
        return [value_text]
    return None
