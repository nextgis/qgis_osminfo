# NextGIS OSMInfo Plugin
# Copyright (C) 2026  NextGIS
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or any
# later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, see <https://www.gnu.org/licenses/>.

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Union

from osminfo.openstreetmap.models import OsmElementType


class WizardBounds(str, Enum):
    """Enumerate supported geographic scopes for wizard searches."""

    BBOX = "bbox"
    AREA = "area"
    AROUND = "around"
    GLOBAL = "global"


class LogicalOperator(str, Enum):
    """Enumerate boolean operators supported by the wizard AST."""

    OR = "or"
    XOR = "xor"
    MINUS = "minus"
    AND = "and"


class ConditionQueryType(str, Enum):
    """Enumerate condition forms recognized by the wizard parser."""

    TYPE = "type"
    META = "meta"
    KEY = "key"
    NO_KEY = "nokey"
    EQ = "eq"
    NEQ = "neq"
    LIKE = "like"
    LIKE_LIKE = "likelike"
    NOT_LIKE = "notlike"
    SUBSTR = "substr"
    FREE_FORM = "free form"


class MetaQueryType(str, Enum):
    """Enumerate metadata predicates supported by the wizard."""

    USER = "user"
    UID = "uid"
    NEWER = "newer"
    ID = "id"


@dataclass(frozen=True)
class RegexValue:
    """Store a regular expression value with an optional modifier.

    Represent the parsed regex payload used by like-style wizard conditions.

    :ivar regex: Regex pattern without surrounding delimiters.
    :ivar modifier: Optional Overpass regex modifier.
    """

    regex: str
    modifier: str = ""


@dataclass(frozen=True)
class ConditionNode:
    """Store a leaf predicate in the wizard abstract syntax tree.

    Describe one parsed search condition before normalization or semantic
    resolution.

    :ivar query: Parsed condition kind.
    :ivar key: Tag key, when the predicate targets a key.
    :ivar val: String or regex payload associated with the condition.
    :ivar meta: Metadata selector for meta predicates.
    :ivar type: OSM element type for type predicates.
    :ivar free: Raw free-form preset text.
    """

    query: ConditionQueryType
    key: Optional[str] = None
    val: Optional[Union[str, RegexValue]] = None
    meta: Optional[MetaQueryType] = None
    type: Optional[OsmElementType] = None
    free: Optional[str] = None


@dataclass(frozen=True)
class LogicalNode:
    """Store a boolean expression node in the wizard AST.

    Combine nested wizard expressions with a single logical operator.

    :ivar logical: Operator joining child expressions.
    :ivar queries: Child expressions in evaluation order.
    """

    logical: LogicalOperator
    queries: List[WizardExpression] = field(default_factory=list)


WizardExpression = Union[ConditionNode, LogicalNode]


@dataclass(frozen=True)
class WizardSearch:
    """Store the parsed wizard search before normalization.

    Combine the top-level bounds selector with the parsed expression tree.

    :ivar bounds: Geographic scope requested by the user.
    :ivar query: Parsed expression tree.
    :ivar area: Area placeholder or geocoding text, when required.
    """

    bounds: WizardBounds
    query: WizardExpression
    area: Optional[str] = None


@dataclass(frozen=True)
class NormalizedConjunction:
    """Store a flattened conjunction of leaf conditions.

    Represent one AND-only branch produced during AST normalization.

    :ivar logical: Logical operator used for the conjunction.
    :ivar queries: Leaf conditions belonging to the branch.
    """

    logical: LogicalOperator = LogicalOperator.AND
    queries: List[ConditionNode] = field(default_factory=list)


@dataclass(frozen=True)
class NormalizedQuery:
    """Store a normalized disjunction of conjunctions.

    Represent the wizard query in disjunctive normal form for later semantic
    resolution and rendering.

    :ivar logical: Top-level operator joining conjunctions.
    :ivar queries: Normalized conjunction branches.
    """

    logical: LogicalOperator = LogicalOperator.OR
    queries: List[NormalizedConjunction] = field(default_factory=list)


@dataclass(frozen=True)
class NormalizedWizardSearch:
    """Store a wizard search after boolean normalization.

    Preserve the requested bounds while replacing the raw AST with the
    normalized query structure.

    :ivar bounds: Geographic scope requested by the user.
    :ivar query: Normalized query representation.
    :ivar area: Area placeholder or geocoding text, when required.
    """

    bounds: WizardBounds
    query: NormalizedQuery
    area: Optional[str] = None


@dataclass(frozen=True)
class ResolvedConjunction:
    """Store a conjunction after semantic type expansion.

    Capture the narrowed OSM element types and resolved tag conditions for one
    normalized branch.

    :ivar types: Allowed OSM element types for the branch.
    :ivar conditions: Resolved conditions for rendering.
    """

    types: List[OsmElementType] = field(default_factory=list)
    conditions: List[ConditionNode] = field(default_factory=list)


@dataclass(frozen=True)
class ResolvedWizardSearch:
    """Store a wizard search after semantic resolution.

    Hold the fully resolved conjunctions that can be rendered into Overpass QL.

    :ivar bounds: Geographic scope requested by the user.
    :ivar conjunctions: Resolved conjunction branches.
    :ivar area: Area placeholder or geocoding text, when required.
    :ivar used_free_form: Whether free-form preset resolution was used.
    """

    bounds: WizardBounds
    conjunctions: List[ResolvedConjunction] = field(default_factory=list)
    area: Optional[str] = None
    used_free_form: bool = False


@dataclass(frozen=True)
class FreeFormResolution:
    """Store the semantic result of resolving one free-form preset.

    Provide element-type restrictions and generated tag conditions for the
    matching preset.

    :ivar types: OSM element types allowed by the preset geometry.
    :ivar conditions: Tag conditions contributed by the preset.
    """

    types: List[OsmElementType] = field(default_factory=list)
    conditions: List[ConditionNode] = field(default_factory=list)


@dataclass(frozen=True)
class RenderedWizardQuery:
    """Store the final rendered Overpass query and its metadata.

    Expose the rendered query text together with basic metadata used by the
    calling query builder.

    :ivar query: Rendered Overpass QL query.
    :ivar bounds: Geographic scope used during rendering.
    :ivar query_count: Number of rendered query clauses.
    :ivar used_free_form: Whether free-form preset resolution was used.
    """

    query: str
    bounds: WizardBounds
    query_count: int
    used_free_form: bool = False
