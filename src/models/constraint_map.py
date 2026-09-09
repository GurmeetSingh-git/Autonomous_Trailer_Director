"""Constraint map schema."""

from typing import Any

from pydantic import BaseModel, Field


class ConstraintMap(BaseModel):
    """Policies and contracts that constrain trailer generation."""

    policies: list[dict[str, Any]] = Field(default_factory=list)
    contracts: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
