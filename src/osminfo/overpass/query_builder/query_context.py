from dataclasses import dataclass, field, replace
from typing import Dict, Optional

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
)
from qgis.gui import QgsMapCanvas

from osminfo.core.exceptions import OsmInfoQueryBuilderError


@dataclass(frozen=True)
class QueryContext:
    bbox: QgsRectangle
    center: QgsPointXY
    geocode_ids: Dict[str, str] = field(default_factory=dict)
    geocode_areas: Dict[str, str] = field(default_factory=dict)
    geocode_bboxes: Dict[str, str] = field(default_factory=dict)
    geocode_coords: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_map_canvas(cls, map_canvas: QgsMapCanvas) -> "QueryContext":
        try:
            extent = QgsRectangle(map_canvas.extent())
            center = QgsPointXY(extent.center())

            destination_crs = map_canvas.mapSettings().destinationCrs()
            wgs84 = QgsCoordinateReferenceSystem.fromEpsgId(4326)
            if destination_crs.postgisSrid() != 4326:
                transformer = QgsCoordinateTransform(
                    destination_crs,
                    wgs84,
                    QgsProject.instance(),
                )
                extent = transformer.transformBoundingBox(extent)
                center = QgsPointXY(transformer.transform(center))
        except Exception as error:
            raise OsmInfoQueryBuilderError(
                log_message="Failed to build query context from map canvas",
                user_message="Failed to read current map extent.",
                detail=str(error),
            ) from error

        return cls(
            bbox=extent,
            center=center,
        )

    def with_geocoding(
        self,
        *,
        geocode_ids: Optional[Dict[str, str]] = None,
        geocode_areas: Optional[Dict[str, str]] = None,
        geocode_bboxes: Optional[Dict[str, str]] = None,
        geocode_coords: Optional[Dict[str, str]] = None,
    ) -> "QueryContext":
        updated_geocode_ids = dict(self.geocode_ids)
        updated_geocode_areas = dict(self.geocode_areas)
        updated_geocode_bboxes = dict(self.geocode_bboxes)
        updated_geocode_coords = dict(self.geocode_coords)
        if geocode_ids is not None:
            updated_geocode_ids.update(geocode_ids)
        if geocode_areas is not None:
            updated_geocode_areas.update(geocode_areas)
        if geocode_bboxes is not None:
            updated_geocode_bboxes.update(geocode_bboxes)
        if geocode_coords is not None:
            updated_geocode_coords.update(geocode_coords)

        return replace(
            self,
            geocode_ids=updated_geocode_ids,
            geocode_areas=updated_geocode_areas,
            geocode_bboxes=updated_geocode_bboxes,
            geocode_coords=updated_geocode_coords,
        )

    @classmethod
    def format_bbox(cls, extent: QgsRectangle) -> str:
        return cls.format_bbox_coordinates(
            extent.yMinimum(),
            extent.xMinimum(),
            extent.yMaximum(),
            extent.xMaximum(),
        )

    @classmethod
    def format_bbox_coordinates(
        cls,
        south: float,
        west: float,
        north: float,
        east: float,
    ) -> str:
        formatted_south = cls._format_coordinate(south)
        formatted_west = cls._format_coordinate(west)
        formatted_north = cls._format_coordinate(north)
        formatted_east = cls._format_coordinate(east)
        return (
            f"{formatted_south},{formatted_west},"
            f"{formatted_north},{formatted_east}"
        )

    @classmethod
    def format_center(cls, latitude: float, longitude: float) -> str:
        formatted_latitude = cls._format_coordinate(latitude)
        formatted_longitude = cls._format_coordinate(longitude)
        return f"{formatted_latitude},{formatted_longitude}"

    @classmethod
    def format_center_point(cls, center: QgsPointXY) -> str:
        return cls.format_center(center.y(), center.x())

    @staticmethod
    def _format_coordinate(value: float) -> str:
        return f"{value:.15f}".rstrip("0").rstrip(".")
