import requests

url = 'http://overpass-api.de/api/interpreter'

lat = 54.271533 #55.75407
lon = 48.296390 #37.63141

request = '[timeout:30][out:json];is_in(%s,%s)->.a;way(pivot.a);out tags geom;relation(pivot.a);out tags bb;'%(lat,lon)

rr = requests.post(url, data = request)

for item in rr.json()['elements']:
    print('Name: ' + item['tags']['name'])

#output = open('test.json','wb')
#output.write(str(r.json()))
#output.close()