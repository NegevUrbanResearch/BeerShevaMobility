#!/usr/bin/env python3
"""National folium map of inbound trip counts by origin zone."""

import json
import logging
from pathlib import Path

import branca.colormap as cm
import folium
import geopandas as gpd
import numpy as np
import pandas as pd
from branca.element import Element, MacroElement
from folium.plugins import MarkerCluster
from jinja2 import Template

from mobility.config import ATTRACTION_CENTERS_SHP, OUTPUT_DIR, OUTPUT_ROOT
from mobility.utils.work_trip_filter import filter_to_work_trips
from mobility.utils.zone_utils import clean_zone_id

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

INNOVATION_DISTRICT_POIS = [
    ("BGU", "Ben-Gurion University"),
    ("Soroka_Hospital", "Soroka Medical Center"),
    ("Gev_Yam", "Gav-Yam High-Tech Park"),
]

BEER_SHEVA_CENTER = [31.2695, 34.8065]
POLYGON_MIN_ZOOM = 13

PALETTE = {
    "canvas": "#e6eee8",
    "surface": "#f8fbf9",
    "text": "#101317",
    "text_secondary": "#49454f",
    "border": "#79747e",
    "accent": "#368393",
    "accent_soft": "#c9eaf1",
}

BLUE_SCALE = [
    "#eff8fb", "#c9eaf1", "#9fd3e0", "#73b8c9", "#4e9cae",
    "#368393", "#2b6979", "#1f4f5c", "#143742",
]

DESIGN_HEAD = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600&family=Libre+Bodoni:wght@400;500&family=Open+Sans:wght@400;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
    .leaflet-popup-content, .leaflet-tooltip { font-family: "Open Sans", system-ui, sans-serif; color: #101317; }
    .leaflet-tooltip { border: 1px solid #79747e; border-radius: 10px; box-shadow: 0 4px 14px rgba(15,23,42,0.08); }
    .legend text { font-family: "Open Sans", system-ui, sans-serif !important; }
</style>
"""

CLUSTER_ICON_FUNCTION = """
function(cluster) {
    var tripTotal = 0;
    cluster.getAllChildMarkers().forEach(function(marker) {
        tripTotal += marker.options.tripCount || 0;
    });
    var childCount = cluster.getChildCount();
    var sizeClass = 'small';
    if (childCount >= 100) {
        sizeClass = 'large';
    } else if (childCount >= 10) {
        sizeClass = 'medium';
    }
    return L.divIcon({
        html: '<div><span>' + tripTotal + '</span></div>',
        className: 'marker-cluster marker-cluster-' + sizeClass,
        iconSize: new L.Point(40, 40)
    });
}
"""

INVISIBLE_ICON = folium.DivIcon(html="", icon_size=(0, 0), icon_anchor=(0, 0), class_name="invisible-marker")

DISTRICT_POI_NAMES = {7: "BGU", 11: "Soroka", 12: "Gav-Yam"}


def district_label_html(name: str) -> str:
    return (
        "<div style=\"font: 700 11px/1 'Open Sans', system-ui, sans-serif;"
        " text-transform: uppercase; letter-spacing: 0.03em; color: #101317;"
        " text-align: center; white-space: nowrap;"
        " text-shadow: 0 0 3px #fff, 0 0 3px #fff, 0 0 4px #fff;\">"
        f"{name}</div>"
    )


class MapTitle(MacroElement):
    _template = Template(
        """
        {% macro header(this, kwargs) %}
        <div style="
            position: fixed;
            top: 14px;
            left: 14px;
            max-width: 340px;
            z-index: 9999;
            background: #f8fbf9;
            color: #101317;
            padding: 12px 16px 14px;
            border: 1px solid #79747e;
            border-radius: 16px;
            box-shadow: 5px 5px 0 rgb(16 19 23 / 0.4);
        ">
            <div style="font: 700 0.7rem/1 'Open Sans', system-ui, sans-serif;
                text-transform: uppercase; letter-spacing: 0.08em; color: #368393;
                margin-bottom: 6px;">Innovation District</div>
            <div style="font: 500 1.25rem/1.2 'Libre Bodoni', Georgia, serif;
                letter-spacing: -0.01em; color: #101317;">{{this.title}}</div>
        </div>
        {% endmacro %}
        """
    )

    def __init__(self, title: str):
        super().__init__()
        self.title = title


class DetailZoomToggle(MacroElement):
    _template = Template(
        """
        {% macro script(this, kwargs) %}
            var map = {{this.map_name}};
            var polygonLayer = {{this.polygon_layer_name}};
            var clusterLayer = {{this.cluster_layer_name}};
            var minZoom = {{this.min_zoom}};

            function toggleLayer(layer, shouldShow) {
                if (shouldShow && !map.hasLayer(layer)) {
                    layer.addTo(map);
                } else if (!shouldShow && map.hasLayer(layer)) {
                    map.removeLayer(layer);
                }
            }

            function updateDetailLevels() {
                var showPolygons = map.getZoom() >= minZoom;
                var incoming = showPolygons ? polygonLayer : clusterLayer;
                var outgoing = showPolygons ? clusterLayer : polygonLayer;
                toggleLayer(incoming, true);
                requestAnimationFrame(function() { toggleLayer(outgoing, false); });
            }

            map.on('zoomend', updateDetailLevels);
            updateDetailLevels();
        {% endmacro %}
        """
    )

    def __init__(self, trip_map, polygon_layer, cluster_layer, min_zoom: int):
        super().__init__()
        self.map_name = trip_map.get_name()
        self.polygon_layer_name = polygon_layer.get_name()
        self.cluster_layer_name = cluster_layer.get_name()
        self.min_zoom = min_zoom


class BringToFront(MacroElement):
    _template = Template(
        """
        {% macro script(this, kwargs) %}
            var districtLayer = {{this.layer_name}};
            function bringDistrictFront() {
                if (districtLayer.bringToFront) { districtLayer.bringToFront(); }
            }
            {{this.map_name}}.on('zoomend overlayadd', bringDistrictFront);
            bringDistrictFront();
        {% endmacro %}
        """
    )

    def __init__(self, trip_map, layer):
        super().__init__()
        self.map_name = trip_map.get_name()
        self.layer_name = layer.get_name()


class DistrictLabelScaler(MacroElement):
    _template = Template(
        """
        {% macro script(this, kwargs) %}
            var map = {{this.map_name}};
            var baseZoom = {{this.base_zoom}};
            function scaleDistrictLabels() {
                var scale = Math.pow(2, map.getZoom() - baseZoom);
                document.querySelectorAll('.innovation-district-label > div').forEach(function(el) {
                    el.style.transformOrigin = 'center center';
                    el.style.transform = 'scale(' + scale + ')';
                });
            }
            map.on('zoomend', scaleDistrictLabels);
            map.whenReady(function() { setTimeout(scaleDistrictLabels, 150); });
        {% endmacro %}
        """
    )

    def __init__(self, trip_map, base_zoom: int):
        super().__init__()
        self.map_name = trip_map.get_name()
        self.base_zoom = base_zoom


def load_zone_trip_totals(work_trips_only: bool) -> pd.DataFrame:
    totals = None
    for file_stem, _ in INNOVATION_DISTRICT_POIS:
        df = pd.read_csv(OUTPUT_DIR / f"{file_stem}_inbound_trips.csv")
        if work_trips_only:
            df = filter_to_work_trips(df)
        per_zone = df.groupby("tract", as_index=False)["total_trips"].sum()
        per_zone = per_zone.rename(columns={"total_trips": file_stem})
        totals = per_zone if totals is None else totals.merge(per_zone, on="tract", how="outer")

    poi_columns = [file_stem for file_stem, _ in INNOVATION_DISTRICT_POIS]
    totals[poi_columns] = totals[poi_columns].fillna(0)
    totals["total_trips"] = totals[poi_columns].sum(axis=1)
    totals = totals[totals["total_trips"] > 0].copy()
    totals["tract_clean"] = totals["tract"].apply(clean_zone_id)
    totals["display_trips"] = totals["total_trips"].round().astype(int)
    for file_stem in poi_columns:
        totals[f"{file_stem}_display"] = totals[file_stem].round().astype(int)
    return totals


def load_zone_geometries() -> gpd.GeoDataFrame:
    zones = gpd.read_file(OUTPUT_DIR / "zones.geojson")
    zones = zones.set_crs(epsg=2039, allow_override=True)
    centroids = gpd.GeoDataFrame(geometry=zones.geometry.centroid, crs=zones.crs).to_crs(
        epsg=4326
    )
    zones = zones.to_crs(epsg=4326)
    zones = zones.assign(
        tract_clean=zones["YISHUV_STAT11"].apply(clean_zone_id),
        centroid_lat=centroids.geometry.y,
        centroid_lon=centroids.geometry.x,
    )
    return zones


def zone_info_html(row) -> str:
    city = row["SHEM_YISHUV_ENGLISH"] or "Unknown"
    rows = [
        ("Gav-Yam High-Tech Park", int(row["Gev_Yam_display"])),
        ("Soroka Medical Center", int(row["Soroka_Hospital_display"])),
        ("Ben-Gurion University", int(row["BGU_display"])),
    ]
    part_rows = "".join(
        f"""<tr>
            <td style="padding: 3px 12px 3px 0; color: #49454f;">{name}</td>
            <td style="padding: 3px 0; text-align: right; color: #101317;
                font-family: 'JetBrains Mono', ui-monospace, monospace; font-weight: 600;">{value:,}</td>
        </tr>"""
        for name, value in rows
    )
    return f"""<div style="font: 12px/1.45 'Open Sans', system-ui, sans-serif; min-width: 190px; color: #101317;">
        <div style="font: 600 13px/1.1 'Fraunces', Georgia, serif; letter-spacing: -0.02em; color: #101317;">{city}</div>
        <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em;
            color: #49454f; margin-bottom: 6px;">Zone {row['tract_clean']}</div>
        <div style="padding-bottom: 5px; border-bottom: 1px solid #79747e;">
            <span style="font: 400 22px/1 'Libre Bodoni', Georgia, serif; color: #368393;">{int(row['display_trips']):,}</span>
            <span style="font-size: 11px; color: #49454f;"> total trips</span>
        </div>
        <table style="width: 100%; border-collapse: collapse; margin-top: 6px;">{part_rows}</table>
    </div>"""


def nice_step(span: float) -> int:
    if span <= 0:
        return 1
    magnitude = 10 ** np.floor(np.log10(span))
    return max(int(round(span / magnitude) * magnitude), 1)


def build_green_colormap(max_trips: int) -> cm.LinearColormap:
    n = len(BLUE_SCALE)
    sqrt_index = [round(max_trips * (i / (n - 1)) ** 2) for i in range(n)]
    step = nice_step(max_trips / 4)
    ticks = list(range(0, max_trips + 1, step))
    if max_trips - ticks[-1] >= step / 2:
        ticks.append(max_trips)
    colormap = cm.LinearColormap(
        colors=BLUE_SCALE,
        index=sqrt_index,
        vmin=0,
        vmax=max_trips,
        tick_labels=ticks,
        text_color=PALETTE["text"],
    )
    colormap.caption = "Inbound trips"
    colormap.width = 300
    return colormap


def build_zone_layer(gdf: gpd.GeoDataFrame, colormap: cm.LinearColormap) -> folium.GeoJson:
    def style(feature):
        trips = max(int(feature["properties"]["display_trips"]), 1)
        return {
            "fillColor": colormap(trips),
            "color": "#143742",
            "weight": 1.1,
            "fillOpacity": 0.72,
        }

    def highlight(_feature):
        return {"weight": 2.5, "color": "#101317", "fillOpacity": 0.86}

    return folium.GeoJson(
        data=json.loads(gdf.to_json()),
        name="Statistical zones (TAZ)",
        style_function=style,
        highlight_function=highlight,
        tooltip=folium.GeoJsonTooltip(fields=["info_html"], labels=False),
        popup=folium.GeoJsonPopup(fields=["info_html"], labels=False),
    )


def add_innovation_district(trip_map: folium.Map) -> None:
    district = gpd.read_file(ATTRACTION_CENTERS_SHP)
    district = district[district["ID"].isin([7, 11, 12])]
    if district.crs is None:
        district = district.set_crs(epsg=2039)
    district = district.to_crs(epsg=4326)

    group = folium.FeatureGroup(name="Innovation District", control=False)
    district_polygons = folium.GeoJson(
        data=json.loads(district.to_json()),
        style_function=lambda _f: {
            "fillColor": "#fcd68d",
            "fillOpacity": 0.18,
            "color": "#e08a0c",
            "weight": 3,
        },
        tooltip="Innovation District \u2014 trip destination",
    )
    district_polygons.add_to(group)

    for _, row in district.iterrows():
        name = DISTRICT_POI_NAMES.get(int(row["ID"]), "")
        centroid = row.geometry.centroid
        folium.Marker(
            location=[centroid.y, centroid.x],
            icon=folium.DivIcon(
                html=district_label_html(name),
                icon_size=(90, 14),
                icon_anchor=(45, 7),
                class_name="innovation-district-label",
            ),
        ).add_to(group)
    group.add_to(trip_map)
    trip_map.add_child(BringToFront(trip_map, district_polygons))
    trip_map.add_child(DistrictLabelScaler(trip_map, POLYGON_MIN_ZOOM))


def create_zone_trip_map(
    output_path: Path | None = None,
    work_trips_only: bool = False,
) -> Path:
    totals = load_zone_trip_totals(work_trips_only)
    zones = load_zone_geometries()
    gdf = zones.merge(totals, on="tract_clean", how="inner")
    gdf = gdf.dropna(subset=["centroid_lat", "centroid_lon", "geometry"])
    gdf["info_html"] = gdf.apply(zone_info_html, axis=1)

    title = (
        "Inbound Work Trips to the Innovation District by Origin Zone"
        if work_trips_only
        else "Inbound Trips to the Innovation District by Origin Zone"
    )

    max_trips = max(int(gdf["display_trips"].max()), 1)
    colormap = build_green_colormap(max_trips)

    trip_map = folium.Map(
        location=BEER_SHEVA_CENTER,
        zoom_start=13,
        tiles="CartoDB Voyager",
        control_scale=True,
    )
    trip_map.get_root().header.add_child(Element(DESIGN_HEAD))
    trip_map.add_child(MapTitle(title))

    zone_layer = build_zone_layer(gdf, colormap)
    colormap.add_to(trip_map)

    zone_layer.add_to(trip_map)
    add_innovation_district(trip_map)

    marker_cluster = MarkerCluster(
        name="Trip clusters",
        icon_create_function=CLUSTER_ICON_FUNCTION,
        options={
            "disableClusteringAtZoom": 20,
            "maxClusterRadius": 60,
            "spiderfyOnMaxZoom": False,
            "showCoverageOnHover": False,
        },
    ).add_to(trip_map)

    for _, row in gdf.iterrows():
        trip_count = int(row["display_trips"])
        city = row["SHEM_YISHUV_ENGLISH"] or "Unknown"
        folium.Marker(
            location=[row["centroid_lat"], row["centroid_lon"]],
            icon=INVISIBLE_ICON,
            tooltip=f"{city}: {trip_count:,} trips",
            tripCount=trip_count,
        ).add_to(marker_cluster)

    trip_map.add_child(
        DetailZoomToggle(trip_map, zone_layer, marker_cluster, POLYGON_MIN_ZOOM)
    )

    folium.LayerControl().add_to(trip_map)

    if output_path is None:
        folder = OUTPUT_ROOT / ("working_trips" if work_trips_only else "dashboard_data")
        filename = "zone_trip_map_work.html" if work_trips_only else "zone_trip_map.html"
        output_path = folder / filename
    else:
        output_path = Path(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    trip_map.save(str(output_path))
    logger.info("Saved %s zones to %s", len(gdf), output_path)
    return output_path


if __name__ == "__main__":
    create_zone_trip_map(
        output_path=OUTPUT_ROOT / "working_trips" / "zone_trip_map.html",
        work_trips_only=True,
    )
