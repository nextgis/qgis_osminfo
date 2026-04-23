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

from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

RawElement = Dict[str, Any]
ElementKey = Tuple[str, int]


class RawElementsSubsetCollector:
    def __init__(self, raw_elements: Iterable[RawElement]) -> None:
        self._raw_elements = tuple(raw_elements)
        self._raw_elements_by_key = self._build_raw_element_index(
            self._raw_elements
        )

    def is_empty(self) -> bool:
        return len(self._raw_elements) == 0

    def all_raw_elements(self) -> Tuple[RawElement, ...]:
        return self._raw_elements

    def raw_element_for_key(
        self,
        element_key: ElementKey,
    ) -> Optional[RawElement]:
        return self._raw_elements_by_key.get(element_key)

    def collect_geometry_subset(
        self,
        requested_raw_elements: Iterable[RawElement],
    ) -> Tuple[RawElement, ...]:
        ordered_elements: List[RawElement] = []
        collected_keys: Set[ElementKey] = set()
        anonymous_members: Set[int] = set()

        for raw_element in requested_raw_elements:
            self._append_raw_element_with_dependencies(
                raw_element,
                ordered_elements,
                collected_keys,
                anonymous_members,
            )

        return tuple(ordered_elements)

    def _append_raw_element_with_dependencies(
        self,
        raw_element: RawElement,
        ordered_elements: List[RawElement],
        collected_keys: Set[ElementKey],
        anonymous_members: Set[int],
    ) -> None:
        element_key = self._raw_element_key(raw_element)
        if element_key is not None:
            if element_key in collected_keys:
                return

            collected_keys.add(element_key)
        else:
            anonymous_identifier = id(raw_element)
            if anonymous_identifier in anonymous_members:
                return

            anonymous_members.add(anonymous_identifier)

        ordered_elements.append(raw_element)

        element_type = str(raw_element.get("type", "")).lower()
        if element_type == "way":
            self._append_way_dependencies(
                raw_element,
                ordered_elements,
                collected_keys,
                anonymous_members,
            )
            return

        if element_type == "relation":
            self._append_relation_dependencies(
                raw_element,
                ordered_elements,
                collected_keys,
                anonymous_members,
            )

    def _append_way_dependencies(
        self,
        raw_way: RawElement,
        ordered_elements: List[RawElement],
        collected_keys: Set[ElementKey],
        anonymous_members: Set[int],
    ) -> None:
        if isinstance(raw_way.get("geometry"), list):
            return

        if isinstance(raw_way.get("bounds"), dict):
            return

        raw_nodes = raw_way.get("nodes")
        if not isinstance(raw_nodes, list):
            return

        for raw_node_identifier in raw_nodes:
            try:
                node_identifier = int(raw_node_identifier)
            except (TypeError, ValueError):
                continue

            raw_node = self._raw_elements_by_key.get(("node", node_identifier))
            if raw_node is None:
                continue

            self._append_raw_element_with_dependencies(
                raw_node,
                ordered_elements,
                collected_keys,
                anonymous_members,
            )

    def _append_relation_dependencies(
        self,
        raw_relation: RawElement,
        ordered_elements: List[RawElement],
        collected_keys: Set[ElementKey],
        anonymous_members: Set[int],
    ) -> None:
        raw_members = raw_relation.get("members")
        if not isinstance(raw_members, list):
            return

        for raw_member in raw_members:
            if not isinstance(raw_member, dict):
                continue

            member_type = str(raw_member.get("type", "")).lower()
            if member_type == "node":
                if (
                    raw_member.get("lat") is not None
                    and raw_member.get("lon") is not None
                ):
                    self._append_raw_element_with_dependencies(
                        raw_member,
                        ordered_elements,
                        collected_keys,
                        anonymous_members,
                    )
                    continue

                self._append_member_reference(
                    member_type,
                    raw_member,
                    ordered_elements,
                    collected_keys,
                    anonymous_members,
                )
                continue

            if member_type == "way":
                if isinstance(raw_member.get("geometry"), list):
                    self._append_raw_element_with_dependencies(
                        raw_member,
                        ordered_elements,
                        collected_keys,
                        anonymous_members,
                    )
                    continue

                self._append_member_reference(
                    member_type,
                    raw_member,
                    ordered_elements,
                    collected_keys,
                    anonymous_members,
                )
                continue

            if member_type == "relation":
                self._append_member_reference(
                    member_type,
                    raw_member,
                    ordered_elements,
                    collected_keys,
                    anonymous_members,
                )

    def _append_member_reference(
        self,
        member_type: str,
        raw_member: RawElement,
        ordered_elements: List[RawElement],
        collected_keys: Set[ElementKey],
        anonymous_members: Set[int],
    ) -> None:
        raw_reference = raw_member.get("ref", raw_member.get("id"))
        if raw_reference is None:
            return

        try:
            member_identifier = int(raw_reference)
        except (TypeError, ValueError):
            return

        raw_dependency = self._raw_elements_by_key.get(
            (member_type, member_identifier)
        )
        if raw_dependency is None:
            return

        self._append_raw_element_with_dependencies(
            raw_dependency,
            ordered_elements,
            collected_keys,
            anonymous_members,
        )

    @staticmethod
    def _raw_element_key(raw_element: RawElement) -> Optional[ElementKey]:
        raw_type = raw_element.get("type")
        raw_identifier = raw_element.get("id", raw_element.get("ref"))
        if raw_type is None or raw_identifier is None:
            return None

        try:
            return (str(raw_type).lower(), int(raw_identifier))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _build_raw_element_index(
        raw_elements: Iterable[RawElement],
    ) -> Dict[ElementKey, RawElement]:
        indexed_elements: Dict[ElementKey, RawElement] = {}
        for raw_element in raw_elements:
            element_key = RawElementsSubsetCollector._raw_element_key(
                raw_element
            )
            if element_key is None:
                continue

            indexed_elements[element_key] = raw_element

        return indexed_elements
