import re
print("TEST 72:", re.findall(r"[\w\u00C0-\u1EF9]+|\d+", "72".lower()))
print("TEST H2O:", re.findall(r"[\w\u00C0-\u1EF9]+|\d+", "H2O".lower()))
