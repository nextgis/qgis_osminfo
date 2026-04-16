from enum import Enum


class OsmElementType(str, Enum):
    NODE = "node"
    WAY = "way"
    RELATION = "relation"
