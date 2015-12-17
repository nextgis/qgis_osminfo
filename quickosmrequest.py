import requests

url = 'http://overpass-api.de/api/interpreter'
payload = {'key1': 'value1', 'key2': 'value2'}

lat = 55.75407
lon = 37.63141

request = '[timeout:5][out:json];is_in(%s,%s)->.a;way(pivot.a);out tags geom(55.7528637550784,37.625319957733154,55.75534521134387,37.635018825531006);relation(pivot.a);out tags bb;'%(lat,lon)

r = requests.post(url, data = request)

output = open('test.json','wb')
output.write(str(r.json()))
output.close()