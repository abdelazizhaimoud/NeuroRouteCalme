import numpy as np
from main import haversine_km
mid_lon = np.array([-7.6, -7.5])
mid_lat = np.array([33.5, 33.6])
h_lon, h_lat = -7.61, 33.57
print("Result:")
try:
    print(haversine_km(mid_lon, mid_lat, h_lon, h_lat))
except Exception as e:
    print("Error:", e)
