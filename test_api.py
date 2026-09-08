import urllib.request, urllib.error
req = urllib.request.Request('http://127.0.0.1:8000/v3/web/status', method='GET')
try:
    print(urllib.request.urlopen(req).getcode())
except urllib.error.HTTPError as e:
    print(e.code)
