"""Generate a click-to-pick-coordinates map for Casablanca."""
import folium
from folium.plugins import MousePosition
from pathlib import Path

m = folium.Map(location=[33.5731, -7.6114], zoom_start=13, tiles="CartoDB positron")
MousePosition(position="topright", separator=", ", prefix="Coords:", num_digits=4).add_to(m)
m.add_child(folium.LatLngPopup())

Path("outputs").mkdir(exist_ok=True)
m.save("outputs/pick_coordinates.html")
print("Saved: outputs/pick_coordinates.html")
print("Open it in your browser, click any point, and it shows (lat, lng).")
print("Copy those into demo.py START/END variables.")
