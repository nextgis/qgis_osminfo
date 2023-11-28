from qgis.core import QgsGeometry

from .osmtags import *
from .compat import qgsGeometryFromPointXY, qgsGeometryFromPolygonXY, qgsGeometryFromPolylineXY, qgsGeometryFromMultiPolygonXY, qgsGeometryFromMultiPolylineXY, QgsPointXY

class PolygonCreator(object):
    """docstring for PolygonCreator"""
    def __init__(self):
        super(PolygonCreator, self).__init__()

        self.curves = []

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
        return \
            len(self.curves) == 1 and self.curves[0][0] == self.curves[0][-1]

    def getPoints(self):
        points = []
        for curve in self.curves:
            points.extend(curve)
        return points


class OsmElement(object):
    """docstring for OsmElement"""
    def __init__(self, type, id, tags={}, **kwargs):
        super(OsmElement, self).__init__()

        self.__type = type
        self.__id = id
        self.__tags = tags

        self.__relation_role = kwargs.get(u'relation_role')
        self.__bounds = kwargs.get(u'bounds')

        self.__qgisGeometry = None

    def __str__(self):
        return "%s id=%s" % (self.__class__.__name__, self.__id)

    # def asQgisGeometry(self):
    #     if self.__qgisGeometry is None:
    #         self.__qgisGeometry =self._asQgisGeometry()

    #     return self.__qgisGeometry

    def asQgisGeometry(self) -> QgsGeometry:
        raise NotImplementedError('Not Implemented Culture')

    def type(self):
        return self.__type

    @property
    def id(self):
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
            u'name:%s' % locale,
            self.__tags.get(
                u'name',
                None
            )
        )

        if title is None:
            for tag, rule in list(title_rules.items()):
                if tag in self.tags:
                    try:
                        title = rule.format(**self.__tags)
                    except:
                        pass

        if title is None:
            print(self.__tags)
            title = str(self.__tags.get(
                u"id",
                self.__id
            ))

        return title


class OsmNode(OsmElement):
    """docstring for OsmNode"""
    def __init__(self, id, lon_lat, tags={}, **kwargs):
        (lon, lat) = lon_lat
        super(OsmNode, self).__init__(u'node', id, tags, **kwargs)

        self.__lon = lon
        self.__lat = lat

    def asQgisGeometry(self) -> QgsGeometry:
        return qgsGeometryFromPointXY(QgsPointXY(self.__lon, self.__lat))


class OsmWay(OsmElement):
    """docstring for OsmWay"""
    def __init__(self, id, lon_lat_pairs, tags={}, **kwargs):
        super(OsmWay, self).__init__(u'way', id, tags, **kwargs)

        self.__lon_lat_pairs = lon_lat_pairs

    def getLonLatPairs(self):
        return self.__lon_lat_pairs

    def closed(self):
        if len(self.__lon_lat_pairs) < 3:
            return False

        if self.__lon_lat_pairs[0] != self.__lon_lat_pairs[-1]:
            return False

        return True

    #TODO Check tags
    def _canBeArea(self):
        # ! tags is absent for relation ways
        # if self.tags.get(u'area', u'no') != u'yes':
        #   return False

        return self.closed()

    def asQgisGeometry(self) -> QgsGeometry:
        # TODO can be diffs geom in same time. Check it!
        if self._canBeArea():
            return qgsGeometryFromPolygonXY([
                [QgsPointXY(lon, lat) for lon, lat in self.__lon_lat_pairs], []
            ])
        else:
            return qgsGeometryFromPolylineXY([
                QgsPointXY(lon, lat) for lon, lat in self.__lon_lat_pairs
            ])

    def checkRelationRole(self, relation_role_name):
        return self.relationRole == relation_role_name

    def isOuter(self):
        return self.checkRelationRole(u'outer')

    def isInner(self):
        return self.checkRelationRole(u'inner')


class OsmRelation(OsmElement):
    """docstring for OsmRelation"""
    def __init__(self, id, osm_elements, tags={}, **kwargs):
        super(OsmRelation, self).__init__(u'relation', id, tags, **kwargs)

        self.__osm_elements = osm_elements

    def asQgisGeometry(self) -> QgsGeometry:
        if self._isArea():
            polygones = []

            polygon_outer_finished = False
            polygon = [PolygonCreator(), ]

            ways = [osm_element for osm_element in self.__osm_elements if isinstance(osm_element, OsmWay)]
            for osm_element in ways:
                if osm_element.isOuter():
                    if polygon_outer_finished:
                        polygon_outer_finished = False
                        polygones.append([pc.getPoints() for pc in polygon])
                        polygon = [PolygonCreator(), ]

                    # print "    ", osm_element.getLonLatPairs()
                    # print "try add curve"
                    polygon[0].addCurve([QgsPointXY(lon, lat) for lon, lat in osm_element.getLonLatPairs()])

                    if polygon[0].isPolygon():
                        polygon_outer_finished = True

                elif osm_element.isInner():
                    if len(polygon) == 1 or polygon[-1].isPolygon():
                        polygon.append( PolygonCreator() )
                    polygon[-1].addCurve([QgsPointXY(lon, lat) for lon, lat in osm_element.getLonLatPairs()])

            if polygon[0].isPolygon():
                polygones.append([pc.getPoints() for pc in polygon])

            # print "polygones: ", len(polygones)
            return qgsGeometryFromMultiPolygonXY(polygones)
            # return [QgsGeometry.fromPolygon(polygon) for polygon in polygones]
        else:
            lines = []
            for osm_element in self.__osm_elements:
                if osm_element.isOuter():
                    lines.append( [QgsPointXY(lon, lat) for lon, lat in osm_element.getLonLatPairs()] )

            return qgsGeometryFromMultiPolylineXY(lines)

    def _isArea(self):
        return self.tags.get(u'type', 'none') in [u'multipolygon', u'boundary']


def parseOsmElement(json):
    element_type = json.get(u'type', u'')
    if element_type == u'relation':
        return parseOsmReletion(json)
    elif element_type == u'way':
        return parseOsmWay(json)
    elif element_type == u'node':
        return parseOsmNode(json)

    return None


def parseOsmReletion(json):
    osm_elements = []

    for member in json.get(u'members',[]):
        osm_element = parseOsmElement(member)
        if osm_element is not None:
            osm_elements.append(
                osm_element
            )

    return OsmRelation(
        json.get(u'id', '<unknown>'),
        osm_elements,
        json.get(u'tags', {}),
    )

def parseOsmWay(json):
    lon_lat_pairs = [ (coords.get(u'lon'), coords.get(u'lat')) for coords in json.get(u'geometry', []) ]

    return OsmWay(
        json.get(u'id', json.get(u'ref','<unknown>')),
        lon_lat_pairs,
        json.get(u'tags', {}),
        relation_role=json.get(u'role'),
        bounds=json.get(u'bounds')
    )

def parseOsmNode(json):
    lon = json.get(u'lon')
    lat = json.get(u'lat')
    return OsmNode(
        json.get(u'id', '<unknown>'),
        (lon, lat),
        json.get(u'tags', {}),
        relation_role=json.get(u'role'),
        bounds=json.get(u'bounds')
    )
