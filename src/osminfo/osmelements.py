from typing import List

from qgis.core import QgsGeometry, QgsPointXY

from .osmtags import title_rules


class PolygonCreator:
    """docstring for PolygonCreator"""

    __is_outer: bool

    def __init__(self, is_outer: bool = True):
        self.curves = []
        self.__is_outer = is_outer

    def addCurve(self, lon_lat_pairs):
        curve = None
        for i in range(len(self.curves)):
            if self.curves[i][-1] == lon_lat_pairs[0]:
                curve = self.curves.pop(i)
                curve.extend(lon_lat_pairs[0:])
                break
            elif self.curves[i][0] == lon_lat_pairs[-1]:
                curve = lon_lat_pairs[:-1]
                curve.extend(self.curves.pop(i))
                break
            elif self.curves[i][0] == lon_lat_pairs[0]:
                lon_lat_pairs_tmp = lon_lat_pairs
                lon_lat_pairs_tmp.reverse()
                curve = lon_lat_pairs_tmp[:-1]
                curve.extend(self.curves.pop(i))
                break
            elif self.curves[i][-1] == lon_lat_pairs[-1]:
                lon_lat_pairs_tmp = lon_lat_pairs
                lon_lat_pairs_tmp.reverse()
                curve = self.curves.pop(i)
                curve.extend(lon_lat_pairs_tmp[0:])
                break

        if curve is not None:
            self.addCurve(curve)
        else:
            self.curves.append(lon_lat_pairs)

    def isPolygon(self):
        return (
            len(self.curves) == 1 and self.curves[0][0] == self.curves[0][-1]
        )

    def isOuter(self):
        return self.__is_outer

    def getPoints(self):
        points = []
        for curve in self.curves:
            points.extend(curve)
        return points


class OsmElement:
    """docstring for OsmElement"""

    def __init__(self, osm_type, osm_id, tags=None, **kwargs):
        self.__type = osm_type
        self.__id = osm_id
        self.__tags = tags if tags is not None else {}

        self.__relation_role = kwargs.get("relation_role")
        self.__bounds = kwargs.get("bounds")

        self.__qgisGeometry = None

    def __str__(self):
        return f"{self.__class__.__name__} id={self.__id}"

    def asQgisGeometry(self) -> QgsGeometry:
        if self.__qgisGeometry is None:
            self.__qgisGeometry = self._convertToQgisGeometry()

        return QgsGeometry(self.__qgisGeometry)

    def _convertToQgisGeometry(self) -> QgsGeometry:
        raise NotImplementedError("Not Implemented Culture")

    def type(self):
        return self.__type

    @property
    def osm_id(self):
        return self.__id

    @property
    def tags(self):
        return self.__tags

    @property
    def relationRole(self):
        return self.__relation_role

    @property
    def bounds(self):
        return self.__bounds

    def title(self, locale):
        title = self.__tags.get(
            f"name:{locale}", self.__tags.get("name", None)
        )

        if title is None:
            for tag, rule in list(title_rules.items()):
                if tag in self.tags:
                    try:
                        title = rule.format(**self.__tags)
                    except Exception:
                        pass

        if title is None:
            # print(self.__tags)
            title = str(self.__tags.get("id", self.__id))

        return title


class OsmNode(OsmElement):
    """docstring for OsmNode"""

    def __init__(self, osm_id, lon_lat, tags=None, **kwargs):
        (lon, lat) = lon_lat
        super().__init__("node", osm_id, tags, **kwargs)

        self.__lon = lon
        self.__lat = lat

    def _convertToQgisGeometry(self) -> QgsGeometry:
        return QgsGeometry.fromPointXY(QgsPointXY(self.__lon, self.__lat))


class OsmWay(OsmElement):
    """docstring for OsmWay"""

    def __init__(self, osm_id, lon_lat_pairs, tags=None, **kwargs):
        super().__init__("way", osm_id, tags, **kwargs)

        self.__lon_lat_pairs = lon_lat_pairs

    def getLonLatPairs(self):
        return self.__lon_lat_pairs

    def closed(self):
        if len(self.__lon_lat_pairs) < 3:
            return False

        if self.__lon_lat_pairs[0] != self.__lon_lat_pairs[-1]:
            return False

        return True

    # TODO Check tags
    def _canBeArea(self):
        # ! tags is absent for relation ways
        # if self.tags.get(u'area', u'no') != u'yes':
        #   return False

        return self.closed()

    def _convertToQgisGeometry(self) -> QgsGeometry:
        # TODO can be diffs geom in same time. Check it!
        if self._canBeArea():
            return QgsGeometry.fromPolygonXY(
                [[QgsPointXY(lon, lat) for lon, lat in self.__lon_lat_pairs]]
            )
        else:
            return QgsGeometry.fromPolylineXY(
                [QgsPointXY(lon, lat) for lon, lat in self.__lon_lat_pairs]
            )

    def checkRelationRole(self, relation_role_name):
        return self.relationRole == relation_role_name

    def isOuter(self):
        return self.checkRelationRole("outer")

    def isInner(self):
        return self.checkRelationRole("inner")


class OsmRelation(OsmElement):
    """docstring for OsmRelation"""

    def __init__(self, osm_id, osm_elements, tags=None, **kwargs):
        super().__init__("relation", osm_id, tags, **kwargs)

        self.__osm_elements = osm_elements

    def _convertToQgisGeometry(self) -> QgsGeometry:
        if self._isArea():
            ways = [
                osm_element
                for osm_element in self.__osm_elements
                if isinstance(osm_element, OsmWay)
            ]

            is_polygon_finished = True
            polygon_creators: List[PolygonCreator] = []
            for osm_element in ways:
                if is_polygon_finished:
                    is_polygon_finished = False
                    polygon_creators.append(
                        PolygonCreator(is_outer=osm_element.isOuter())
                    )

                polygon_creators[-1].addCurve(
                    [
                        QgsPointXY(lon, lat)
                        for lon, lat in osm_element.getLonLatPairs()
                    ]
                )
                if polygon_creators[-1].isPolygon():
                    is_polygon_finished = True

            return polygon_creators_to_multipolygon(polygon_creators)
        else:
            lines = []
            for osm_element in self.__osm_elements:
                if osm_element.isOuter():
                    lines.append(
                        [
                            QgsPointXY(lon, lat)
                            for lon, lat in osm_element.getLonLatPairs()
                        ]
                    )

            return QgsGeometry.fromMultiPolylineXY(lines)

    def _isArea(self):
        return self.tags.get("type", "none") in ["multipolygon", "boundary"]


def parseOsmElement(json):
    element_type = json.get("type", "")
    if element_type == "relation":
        return parseOsmRelation(json)
    elif element_type == "way":
        return parseOsmWay(json)
    elif element_type == "node":
        return parseOsmNode(json)

    return None


def parseOsmRelation(json):
    osm_elements = []

    for member in json.get("members", []):
        osm_element = parseOsmElement(member)
        if osm_element is not None:
            osm_elements.append(osm_element)

    return OsmRelation(
        json.get("id", "<unknown>"),
        osm_elements,
        json.get("tags", {}),
    )


def parseOsmWay(json):
    lon_lat_pairs = [
        (coords.get("lon"), coords.get("lat"))
        for coords in json.get("geometry", [])
    ]

    return OsmWay(
        json.get("id", json.get("ref", "<unknown>")),
        lon_lat_pairs,
        json.get("tags", {}),
        relation_role=json.get("role"),
        bounds=json.get("bounds"),
    )


def parseOsmNode(json):
    lon = json.get("lon")
    lat = json.get("lat")
    return OsmNode(
        json.get("id", "<unknown>"),
        (lon, lat),
        json.get("tags", {}),
        relation_role=json.get("role"),
        bounds=json.get("bounds"),
    )


def polygon_creators_to_multipolygon(
    polygon_creators: List[PolygonCreator],
) -> QgsGeometry:
    polygons: List[QgsGeometry] = []
    inner_rings: List[QgsGeometry] = []

    for polygon_creator in polygon_creators:
        if not polygon_creator.isPolygon():
            continue

        if polygon_creator.isOuter():
            polygon = QgsGeometry.fromPolygonXY([polygon_creator.getPoints()])
            polygons.append(polygon)
        else:
            polyline = QgsGeometry.fromPolylineXY(polygon_creator.getPoints())
            inner_rings.append(polyline)

    polygons.sort(key=lambda geometry: geometry.area())
    added_rings = []
    for polygon in polygons:
        for i, inner_ring in enumerate(inner_rings):
            if i in added_rings:
                continue
            if polygon.contains(inner_ring):
                polygon.addRing(inner_ring.asPolyline())
                added_rings.append(i)

    if len(inner_rings) > len(added_rings):
        for i, inner_ring in enumerate(inner_rings):
            if i in added_rings:
                continue
            polygon = QgsGeometry.fromPolygonXY([inner_ring.asPolyline()])
            polygons.append(polygon)

    multipolygon = QgsGeometry.fromMultiPolygonXY([])
    for polygon in polygons:
        multipolygon.addPartGeometry(polygon)

    return multipolygon
