import folium
from main import DENSITY_HOTSPOTS
from pathlib import Path

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)
OUTPUT_PATH = OUTPUT_DIR / "map_center_check.html"

# Base map centered roughly on Casablanca
m = folium.Map(location=[33.5731, -7.6114], zoom_start=12, tiles="CartoDB dark_matter")

# Iterate over all defined hotspots
for idx, (lon, lat) in enumerate(DENSITY_HOTSPOTS, 1):
    center = (lat, lon)
    
    # Draw the center point (Red Star)
    folium.Marker(
        center, 
        icon=folium.Icon(color="red", icon="star"),
        popup=f"Hotspot {idx}: {lat:.4f}, {lon:.4f}"
    ).add_to(m)
    
    # Draw the bands (radii are in meters for folium.Circle)
    # 1km band (density 0.85) - Red
    folium.Circle(
        center,
        radius=1000,
        color="red",
        fill=True,
        fill_color="red",
        fill_opacity=0.15,
        weight=2,
        tooltip=f"Hotspot {idx}: 1km band (density 0.85)"
    ).add_to(m)
    
    # 3km band (density 0.60) - Orange
    folium.Circle(
        center,
        radius=3000,
        color="orange",
        fill=True,
        fill_color="orange",
        fill_opacity=0.1,
        weight=1,
        tooltip=f"Hotspot {idx}: 3km band (density 0.60)"
    ).add_to(m)
    
    # 6km band (density 0.40) - Yellow
    folium.Circle(
        center,
        radius=6000,
        color="yellow",
        fill=True,
        fill_color="yellow",
        fill_opacity=0.05,
        weight=1,
        tooltip=f"Hotspot {idx}: 6km band (density 0.40)"
    ).add_to(m)

# Add a legend
legend_html = """
<div style="position:fixed;bottom:30px;left:30px;z-index:1000;
            background:#1a1a2e;padding:12px 16px;border-radius:8px;
            border:1px solid #444;color:white;font-family:sans-serif;font-size:13px;">
    <b>Density Bands (Multi-Hotspot)</b><br>
    <span style="color:red">&#9733;</span> Hotspot Center<br>
    <span style="color:red">&#9673;</span> 1km (Density: 0.85)<br>
    <span style="color:orange">&#9673;</span> 3km (Density: 0.60)<br>
    <span style="color:yellow">&#9673;</span> 6km (Density: 0.40)
</div>
"""
m.get_root().html.add_child(folium.Element(legend_html))

m.save(str(OUTPUT_PATH))
print(f"Map successfully generated at: {OUTPUT_PATH}")
