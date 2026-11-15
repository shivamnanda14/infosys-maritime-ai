import requests
from seed_data import BASE_PORTS

# Auto-built from BASE_PORTS in seed_data.py — always in sync with the port list
# (currently 50 ports). Each BASE_PORTS row is:
# (name, country, congestion_index, avg_dwell_days, lat, lon, region)
PORT_COORDS = {p[0]: (p[4], p[5]) for p in BASE_PORTS}

_DEFAULT_COORDS = (1.29, 103.85)  # Singapore Port as a safe fallback

def fetch_port_weather(port_name):
    coords = PORT_COORDS.get(port_name, _DEFAULT_COORDS)
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={coords[0]}&longitude={coords[1]}&current_weather=true"
        r = requests.get(url, timeout=3)
        if r.status_code == 200:
            cw = r.json().get('current_weather', {})
            windspeed = cw.get('windspeed', 15.0)
            severity = 1 if windspeed < 20 else (2 if windspeed < 40 else 3)
            return {'windspeed': windspeed, 'temperature': cw.get('temperature', 22.0), 'severity': severity}
    except Exception:
        pass
    return {'windspeed': 18.5, 'temperature': 24.0, 'severity': 2}
