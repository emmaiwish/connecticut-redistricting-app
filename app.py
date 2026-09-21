from shiny import App, ui, render, reactive
import geopandas as gpd
import pandas as pd
import json
import copy
import os
import math

# --- Data Loading ---
towns_gdf = gpd.read_file("data/tl_2025_09_cousub.shp")
towns_gdf = towns_gdf.to_crs(epsg=4326)

towns_clean = towns_gdf.copy()
for col in towns_clean.columns:
    if col != "geometry":
        towns_clean[col] = towns_clean[col].apply(
            lambda x: str(x) if hasattr(x, "isoformat") else x
        )

town_name_field = "NAME"

towns_clean["district"] = 0
towns_clean["unit_type"] = towns_clean[town_name_field].apply(
    lambda x: "water" if str(x).strip().lower() == "county subdivisions not defined" else "town"
)
water_mask = towns_clean["unit_type"] == "water"
water_indices = sorted(
    towns_clean.index[water_mask].tolist(),
    key=lambda idx: towns_clean.at[idx, "geometry"].centroid.x
)
for i, idx in enumerate(water_indices, start=1):
    towns_clean.at[idx, town_name_field] = f"Water Area {i}"

combined_gdf = towns_clean.copy()
towns_geojson = json.loads(combined_gdf.to_json())

N_TOWNS = len(towns_clean[towns_clean["unit_type"] == "town"])
N_WATER = len(towns_clean[towns_clean["unit_type"] == "water"])

# --- Columns to always hide ---
HIDDEN_COLS = {"state_fips", "county_fips", "town_fips"}

# --- Load Demographics ---
DEMO_FILE = "data/ct_towns_demographics.csv"
demo_df = None
demo_cols = []
numeric_demo_cols = []

if os.path.exists(DEMO_FILE):
    demo_df = pd.read_csv(DEMO_FILE)
    demo_df["municipality"] = demo_df["municipality"].str.strip()
    demo_cols = [
        c for c in demo_df.columns
        if c != "municipality" and c.lower() not in HIDDEN_COLS
    ]
    numeric_demo_cols = [
        c for c in demo_cols
        if pd.to_numeric(demo_df[c], errors="coerce").notna().any()
    ]

# --- District Colors ---
district_colors = {
    0: "#d9d9d9",
    1: "#e41a1c",
    2: "#377eb8",
    3: "#4daf4a",
    4: "#984ea3",
    5: "#ff7f00",
}

# --- Helpers ---
def pretty_label(col_name: str) -> str:
    return col_name.replace("_", " ").title()


def format_value(col, val):
    try:
        num = float(val)
        if col.startswith("pct_"):
            return f"{num:.1f}%"
        elif num >= 1000:
            return f"{num:,.0f}"
        else:
            return f"{num:g}"
    except (ValueError, TypeError):
        return str(val)


def build_demo_tooltip_lookup():
    """Returns { TOWN_NAME_UPPER: "<html table>" } for map hover tooltips."""
    if demo_df is None:
        return {}
    lookup = {}
    for _, row in demo_df.iterrows():
        name = str(row["municipality"]).strip().upper()
        rows_html = ""
        for col in demo_cols:
            val = row[col]
            if pd.isna(val) or str(val).strip() == "":
                continue
            rows_html += (
                f'<tr>'
                f'<td style="color:#bbb;padding:1px 6px 1px 0;white-space:nowrap">{pretty_label(col)}</td>'
                f'<td style="font-weight:600;text-align:right">{format_value(col, val)}</td>'
                f'</tr>'
            )
        lookup[name] = (
            f'<table style="font-size:0.82em;border-collapse:collapse">{rows_html}</table>'
            if rows_html else ""
        )
    return lookup


# --- Heatmap GeoJSON (built once at startup) ---
def build_heatmap_geojson():
    geo = copy.deepcopy(towns_geojson)
    if (
        demo_df is not None
        and "Voter_Reg_D_20" in demo_df.columns
        and "Voter_Reg_R_20" in demo_df.columns
    ):
        lookup = {}
        for _, row in demo_df.iterrows():
            muni = row["municipality"].strip().upper()
            d = pd.to_numeric(row.get("Voter_Reg_D_20", 0), errors="coerce") or 0
            r = pd.to_numeric(row.get("Voter_Reg_R_20", 0), errors="coerce") or 0
            total = d + r
            lean = round((d - r) / total, 4) if total > 0 else 0
            diff = int(d - r)
            lookup[muni] = {"lean": lean, "diff": diff, "dem": int(d), "rep": int(r)}
        for f in geo["features"]:
            name = f["properties"].get(town_name_field, "").strip().upper()
            info = lookup.get(name, {"lean": 0, "diff": 0, "dem": 0, "rep": 0})
            f["properties"]["lean"] = info["lean"]
            f["properties"]["reg_diff"] = info["diff"]
            f["properties"]["reg_dem"] = info["dem"]
            f["properties"]["reg_rep"] = info["rep"]
    else:
        for f in geo["features"]:
            f["properties"]["lean"] = 0
            f["properties"]["reg_diff"] = 0
            f["properties"]["reg_dem"] = 0
            f["properties"]["reg_rep"] = 0
    return json.dumps(geo)


# --- Population Density GeoJSON (built once at startup) ---
def build_popdensity_geojson():
    geo = copy.deepcopy(towns_geojson)
    if demo_df is not None and "Pop_Total_20" in demo_df.columns:
        lookup = {}
        for _, row in demo_df.iterrows():
            muni = row["municipality"].strip().upper()
            pop = pd.to_numeric(row.get("Pop_Total_20", 0), errors="coerce") or 0
            lookup[muni] = int(pop)
        all_pops = [v for v in lookup.values() if v > 0]
        pop_min = min(all_pops) if all_pops else 0
        pop_max = max(all_pops) if all_pops else 1
        for f in geo["features"]:
            name = f["properties"].get(town_name_field, "").strip().upper()
            pop = lookup.get(name, 0)
            f["properties"]["pop_total"] = pop
            f["properties"]["pop_min"] = pop_min
            f["properties"]["pop_max"] = pop_max
    else:
        for f in geo["features"]:
            f["properties"]["pop_total"] = 0
            f["properties"]["pop_min"] = 0
            f["properties"]["pop_max"] = 1
    return json.dumps(geo)


heatmap_geojson_str = build_heatmap_geojson()
popdensity_geojson_str = build_popdensity_geojson()

# Serialize static data once at module load
_demo_lookup_json = json.dumps(build_demo_tooltip_lookup())
_geojson_str = json.dumps(towns_geojson)
_colors_str = json.dumps(district_colors)
_town_field = town_name_field


# ---------------------------------------------------------------------------
# Polsby-Popper compactness score
# ---------------------------------------------------------------------------
def compute_compactness_scores(current_geojson):
    """
    Compute per-district Polsby-Popper compactness scores.
    PP = 4π·Area / Perimeter²  →  range (0, 1], 1 = perfect circle.

    Works by dissolving the assigned towns into a single district polygon
    using the original GeoDataFrame (projected to a metre-based CRS for
    accurate area/perimeter measurement), then applying the formula.

    Returns dict  {district_int: score_float or None}
    """
    scores = {}

    # Build a name → district mapping from the reactive GeoJSON
    town_to_district = {
        f["properties"].get(town_name_field, "").strip().upper():
        f["properties"].get("district", 0)
        for f in current_geojson["features"]
    }

    # Work in a projected CRS (CT State Plane metres) for accurate geometry
    gdf = combined_gdf.copy()
    gdf["_district"] = (
        gdf[town_name_field].str.strip().str.upper()
        .map(town_to_district)
        .fillna(0)
        .astype(int)
    )

    # Project to EPSG:2234 (Connecticut State Plane, US feet) — good for CT
    gdf_proj = gdf.to_crs(epsg=2234)

    for d in range(1, 6):
        subset = gdf_proj[gdf_proj["_district"] == d]
        if subset.empty:
            scores[d] = None
            continue
        dissolved = subset.union_all()          # single (multi)polygon
        area      = dissolved.area              # sq feet
        perimeter = dissolved.length            # feet
        if perimeter == 0:
            scores[d] = None
        else:
            pp = (4 * math.pi * area) / (perimeter ** 2)
            scores[d] = round(min(pp, 1.0), 4)   # clamp to 1 just in case

    return scores


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
app_ui = ui.page_fillable(
    ui.tags.head(
        ui.tags.script(src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"),
        ui.tags.link(
            rel="stylesheet",
            href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css",
        ),
        ui.tags.style("""
            #map  { width: 100%; height: 100%; min-height: 700px; }
            #heatmap { width: 100%; height: 100%; }
            #popdensitymap { width: 100%; height: 100%; }
            body { margin: 0; }

            .tab-pane[data-value="Voter Registration Heatmap"],
            .tab-pane[data-value="Population Map"] {
                overflow: visible !important;
                height: calc(100vh - 80px);
            }
            .heatmap-wrapper {
                height: calc(100vh - 80px);
                position: relative;
            }

            .bslib-sidebar-layout {
                height: calc(100vh - 80px) !important;
                overflow: hidden !important;
            }
            .bslib-sidebar-layout > .sidebar {
                height: calc(100vh - 80px) !important;
                overflow-y: auto !important;
                overflow-x: hidden !important;
            }
            .bslib-sidebar-layout > .main {
                height: calc(100vh - 80px) !important;
                overflow: hidden !important;
            }

            .demo-placeholder {
                color: #999;
                font-style: italic;
                font-size: 0.85em;
                padding: 4px 0;
            }

            /* --- Combined District Summary --- */
            .district-summary-section { margin-top: 4px; }

            .unassigned-box {
                background: #f0f0f0;
                border: 1px solid #dee2e6;
                border-radius: 5px;
                padding: 6px 10px;
                margin-bottom: 6px;
                font-size: 0.88em;
                color: #555;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }

            .district-summary-section details {
                border: 1px solid #dee2e6;
                border-radius: 5px;
                margin-bottom: 6px;
                background: #fff;
            }
            .district-summary-section summary {
                padding: 6px 10px;
                cursor: pointer;
                font-weight: 600;
                font-size: 0.88em;
                list-style: none;
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 6px;
            }
            .district-summary-section summary::-webkit-details-marker { display: none; }
            .district-summary-section .d-inner {
                padding: 4px 10px 8px 10px;
                font-size: 0.84em;
            }
            .d-summary-left { display: flex; align-items: center; gap: 6px; }
            .d-town-count {
                font-size: 0.82em;
                color: #666;
                font-weight: 400;
                white-space: nowrap;
            }
            .d-swatch {
                display: inline-block;
                width: 11px; height: 11px;
                border-radius: 2px;
                flex-shrink: 0;
            }
            .d-total-table { width: 100%; border-collapse: collapse; }
            .d-total-table td { padding: 2px 3px; }
            .d-total-table td:last-child { text-align: right; font-weight: 600; }
            .d-total-table td:first-child { color: #555; }

            /* Compactness score badge */
            .compact-score {
                display: inline-block;
                font-size: 0.78em;
                font-weight: 700;
                padding: 1px 6px;
                border-radius: 10px;
                margin-left: 4px;
                color: white;
            }

            /* Heatmap z-index */
            .leaflet-control-container { z-index: 1000 !important; }
            .leaflet-bottom { z-index: 1000 !important; }

            /* Export button */
            .export-btn-row {
                margin-top: 8px;
            }
        """),
        # ----------------------------------------------------------------
        # Static map bootstrap
        # ----------------------------------------------------------------
        ui.tags.script(f"""
        window._ctDistrictColors = {_colors_str};
        window._ctTownField      = "{_town_field}";
        window._ctGeoJSON        = {_geojson_str};
        window._ctDemoLookup     = {_demo_lookup_json};
        window._ctFeatureStyles  = {{}};
        window._ctGeoLayer       = null;
        window._ctMap            = null;

        function initCTMap() {{
            if (window._ctMap) {{
                window._ctMap.remove();
                window._ctMap = null;
                window._ctGeoLayer = null;
            }}

            window._ctGeoJSON.features.forEach(function(f) {{
                var name = f.properties[window._ctTownField] || "";
                window._ctFeatureStyles[name] = window._ctDistrictColors[0];
            }});

            var map = L.map('map').setView([41.6, -72.7], 8);
            window._ctMap = map;

            L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                attribution: '&copy; OpenStreetMap contributors',
                maxZoom: 19
            }}).addTo(map);

            function getStyle(feature) {{
                var name = feature.properties[window._ctTownField] || "";
                return {{
                    color: "white",
                    weight: 1,
                    fillColor: window._ctFeatureStyles[name] || "#d9d9d9",
                    fillOpacity: 0.7
                }};
            }}

            var geojsonLayer = L.geoJSON(window._ctGeoJSON, {{
                style: getStyle,
                onEachFeature: function(feature, layer) {{
                    var name      = feature.properties[window._ctTownField] || "Unknown";
                    var nameUpper = name.toUpperCase();
                    var demoHtml  = window._ctDemoLookup[nameUpper] || "";
                    var tipContent =
                        '<div style="font-weight:700;font-size:1em;margin-bottom:4px">' + name + '</div>' +
                        (demoHtml
                            ? demoHtml
                            : '<div style="color:#aaa;font-size:0.82em;font-style:italic">No demographic data</div>');
                    layer.bindTooltip(tipContent, {{ sticky: true, maxWidth: 320 }});
                    layer.on('mouseover', function(e) {{
                        e.target.setStyle({{ color: 'black', weight: 2, fillOpacity: 0.9 }});
                    }});
                    layer.on('mouseout', function(e) {{
                        geojsonLayer.resetStyle(e.target);
                    }});
                    var unitType = feature.properties.unit_type || "town";
                    layer.on('click', function(e) {{
                        Shiny.setInputValue('clicked_town', name, {{priority: 'event'}});
                    }});
                    if (unitType === "water") {{
                        layer.setStyle({{ dashArray: "4 3", weight: 1.5 }});
                    }}
                }}
            }}).addTo(map);

            window._ctGeoLayer = geojsonLayer;
            map.fitBounds(geojsonLayer.getBounds());
        }}

        function updateCTMapColors(featureStyles) {{
            if (!window._ctGeoLayer) return;
            window._ctFeatureStyles = featureStyles;
            window._ctGeoLayer.setStyle(function(feature) {{
                var name = feature.properties[window._ctTownField] || "";
                return {{
                    color: "white",
                    weight: 1,
                    fillColor: featureStyles[name] || "#d9d9d9",
                    fillOpacity: 0.7
                }};
            }});
        }}

        document.addEventListener('DOMContentLoaded', function() {{
            var attempts = 0;
            var interval = setInterval(function() {{
                attempts++;
                if (typeof L !== 'undefined' && document.getElementById('map')) {{
                    clearInterval(interval);
                    initCTMap();
                }} else if (attempts > 50) {{
                    clearInterval(interval);
                }}
            }}, 100);
        }});
        """),
    ),
    ui.navset_tab(
        # ============================================================
        # TAB 1 – Redistricting Tool
        # ============================================================
        ui.nav_panel(
            "Redistricting Tool",
            ui.layout_sidebar(
                ui.sidebar(
                    ui.h3("Connecticut Redistricting Tool"),
                    ui.p("Choose a district, then click towns to assign them."),
                    ui.input_select(
                        "active_district",
                        "Current district",
                        choices={
                            "1": "District 1",
                            "2": "District 2",
                            "3": "District 3",
                            "4": "District 4",
                            "5": "District 5",
                        },
                        selected="1",
                    ),
                    ui.div(
                        ui.input_action_button(
                            "reset_current_btn",
                            "Reset Current District",
                            class_="btn-warning w-100 mb-2",
                        ),
                        ui.input_action_button(
                            "reset_btn",
                            "Reset All Districts",
                            class_="btn-danger w-100",
                        ),
                        style="margin-top: 6px;",
                    ),
                    ui.hr(),
                    ui.h5("District Summary"),
                    ui.output_ui("district_summary"),
                    ui.hr(),
                    ui.div(
                        ui.download_button(
                            "export_csv",
                            "Export District Results (CSV)",
                            class_="btn-success w-100",
                        ),
                        class_="export-btn-row",
                    ),
                    width=340,
                ),
                ui.div(
                    ui.tags.div(id="map"),
                    ui.tags.input(id="clicked_town", type="hidden", value=""),
                    ui.output_ui("map_color_patch"),
                ),
            ),
        ),
        # ============================================================
        # TAB 2 – Voter Registration Heatmap
        # ============================================================
        ui.nav_panel(
            "Voter Registration Heatmap",
            ui.div(
                ui.output_ui("heatmap_ui"),
                class_="heatmap-wrapper",
            ),
        ),
        # ============================================================
        # TAB 3 – Population Map
        # ============================================================
        ui.nav_panel(
            "Population Map",
            ui.div(
                ui.output_ui("popdensity_ui"),
                class_="heatmap-wrapper",
            ),
        ),
    ),
)


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
def server(input, output, session):

    district_map = reactive.value(copy.deepcopy(towns_geojson))

    # ----------------------------------------------------------------
    # Reset ALL districts
    # ----------------------------------------------------------------
    @reactive.effect
    @reactive.event(input.reset_btn)
    def reset_all_districts():
        fresh = copy.deepcopy(towns_geojson)
        for f in fresh["features"]:
            f["properties"]["district"] = 0
        district_map.set(fresh)

    # ----------------------------------------------------------------
    # Reset CURRENT district only
    # ----------------------------------------------------------------
    @reactive.effect
    @reactive.event(input.reset_current_btn)
    def reset_current_district():
        current_district = int(input.active_district())
        current = copy.deepcopy(district_map())
        for f in current["features"]:
            if f["properties"].get("district") == current_district:
                f["properties"]["district"] = 0
        district_map.set(current)

    # ----------------------------------------------------------------
    # Assign district on town click — toggle off 2nd click if same district
    # ----------------------------------------------------------------
    @reactive.effect
    @reactive.event(input.clicked_town)
    def assign_district():
        clicked_name = input.clicked_town()
        if not clicked_name:
            return
        selected_district = int(input.active_district())
        current = copy.deepcopy(district_map())
        for f in current["features"]:
            if f["properties"].get(town_name_field) == clicked_name:
                current_district = f["properties"].get("district", 0)
                # Toggle: clicking the same district deselects the town
                if current_district == selected_district:
                    f["properties"]["district"] = 0
                else:
                    f["properties"]["district"] = selected_district
                break
        district_map.set(current)

    # ----------------------------------------------------------------
    # Color patch
    # ----------------------------------------------------------------
    @output
    @render.ui
    def map_color_patch():
        current = district_map()
        feature_styles = {}
        for f in current["features"]:
            name     = f["properties"].get(town_name_field, "")
            district = f["properties"].get("district", 0)
            feature_styles[name] = district_colors.get(district, "#d9d9d9")
        styles_json = json.dumps(feature_styles)
        return ui.HTML(f"<script>updateCTMapColors({styles_json});</script>")

    # ----------------------------------------------------------------
    # District Summary + Demographic Totals + Compactness
    # ----------------------------------------------------------------
    @output
    @render.ui
    def district_summary():
        current = district_map()

        counts = {i: 0 for i in range(6)}
        for f in current["features"]:
            d = f["properties"].get("district", 0)
            counts[d] = counts.get(d, 0) + 1

        agg = {i: {} for i in range(1, 6)}
        if demo_df is not None and numeric_demo_cols:
            town_district = {
                f["properties"].get(town_name_field, "").strip().upper():
                f["properties"].get("district", 0)
                for f in current["features"]
            }
            df = demo_df.copy()
            df["_district"] = (
                df["municipality"].str.upper().map(town_district).fillna(0).astype(int)
            )
            for d in range(1, 6):
                subset = df[df["_district"] == d]
                for col in numeric_demo_cols:
                    vals = pd.to_numeric(subset[col], errors="coerce")
                    if vals.notna().any():
                        agg[d][col] = vals.sum()

        # Compute compactness scores for all districts
        compactness = compute_compactness_scores(current)

        n_unassigned = counts[0]
# Split unassigned count into towns vs water areas
        unassigned_towns = sum(
            1 for f in current["features"]
            if f["properties"].get("district", 0) == 0
            and f["properties"].get("unit_type", "town") == "town"
        )
        unassigned_water = sum(
            1 for f in current["features"]
            if f["properties"].get("district", 0) == 0
            and f["properties"].get("unit_type", "water") == "water"
        )
        parts = []
        if unassigned_towns > 0:
            parts.append(f'{unassigned_towns} town{"s" if unassigned_towns != 1 else ""}')
        if unassigned_water > 0:
            parts.append(f'{unassigned_water} water area{"s" if unassigned_water != 1 else ""}')
        unassigned_html = (
            f'<div class="unassigned-box">'
            f'<span style="font-weight:600">Unassigned</span>'
            f'<span>{" + ".join(parts)}</span>'
            f'</div>'
        ) if n_unassigned > 0 else ""

        def compactness_badge(score):
            """Return a colored pill badge for a compactness score."""
            if score is None:
                return ""
            # Color: red (low) → yellow → green (high)
            if score >= 0.40:
                bg = "#28a745"   # green
            elif score >= 0.20:
                bg = "#fd7e14"   # orange
            else:
                bg = "#dc3545"   # red
            return (
                f'<span class="compact-score" style="background:{bg}" '
                f'title="Polsby-Popper compactness (0–1, higher is more compact)">'
                f'PP: {score:.3f}</span>'
            )

        blocks = []
        for i in range(1, 6):
            color       = district_colors[i]
            town_count  = counts[i]
            count_label = f'{town_count} town{"s" if town_count != 1 else ""}'
            score       = compactness.get(i)
            badge       = compactness_badge(score)

            if agg[i]:
                rows = "".join(
                    f'<tr>'
                    f'<td>{pretty_label(col)}</td>'
                    f'<td>{format_value(col, val)}</td>'
                    f'</tr>'
                    for col, val in agg[i].items()
                )
                # Prepend compactness row to the demographic table
                compact_row = ""
                if score is not None:
                    compact_row = (
                        f'<tr>'
                        f'<td style="color:#555">Compactness (PP)</td>'
                        f'<td style="font-weight:700">{score:.4f}</td>'
                        f'</tr>'
                    )
                inner = f'<table class="d-total-table">{compact_row}{rows}</table>'
            else:
                if score is not None:
                    inner = (
                        f'<table class="d-total-table">'
                        f'<tr><td style="color:#555">Compactness (PP)</td>'
                        f'<td style="font-weight:700">{score:.4f}</td></tr>'
                        f'</table>'
                    )
                else:
                    inner = '<p style="color:#aaa;font-size:0.82em;font-style:italic;margin:2px 0">No towns assigned yet.</p>'

            blocks.append(
                f'<details>'
                f'<summary>'
                f'  <div class="d-summary-left">'
                f'    <span class="d-swatch" style="background:{color}"></span>'
                f'    District {i}'
                f'    {badge}'
                f'  </div>'
                f'  <span class="d-town-count">{count_label}</span>'
                f'</summary>'
                f'<div class="d-inner">{inner}</div>'
                f'</details>'
            )

        return ui.HTML(
            f'<div class="district-summary-section">'
            f'{unassigned_html}'
            f'{"".join(blocks)}'
            f'</div>'
        )

    # ----------------------------------------------------------------
    # Export CSV 
    # ----------------------------------------------------------------
    @render.download(filename="district_results.csv")
    def export_csv():
        current = district_map()

        # Build town → district mapping
        town_district = {
            f["properties"].get(town_name_field, "").strip().upper():
            f["properties"].get("district", 0)
            for f in current["features"]
        }

        # Town-level export
        rows = []
        for f in current["features"]:
            town_name = f["properties"].get(town_name_field, "")
            district  = f["properties"].get("district", 0)
            row = {"municipality": town_name, "district": district}
            if demo_df is not None:
                match = demo_df[
                    demo_df["municipality"].str.upper() == town_name.upper()
                ]
                if not match.empty:
                    for col in demo_cols:
                        row[col] = match.iloc[0][col]
            rows.append(row)

        town_df = pd.DataFrame(rows).sort_values(["district", "municipality"])

        # Compactness scores
        compactness = compute_compactness_scores(current)

        # District summary
        summary_rows = []
        if demo_df is not None and numeric_demo_cols:
            df = demo_df.copy()
            df["_district"] = (
                df["municipality"].str.upper().map(town_district).fillna(0).astype(int)
            )
            town_counts = (
                df.groupby("_district").size().reset_index(name="town_count")
            )
            for d in range(0, 6):
                label = "Unassigned" if d == 0 else f"District {d}"
                subset = df[df["_district"] == d]
                tc = int(town_counts[town_counts["_district"] == d]["town_count"].sum()) if d in town_counts["_district"].values else 0
                srow = {"district": label, "town_count": tc}
                # Add compactness (N/A for unassigned)
                srow["compactness_pp"] = (
                    compactness.get(d) if d > 0 else None
                )
                for col in numeric_demo_cols:
                    vals = pd.to_numeric(subset[col], errors="coerce")
                    srow[col] = round(vals.sum(), 2) if vals.notna().any() else 0
                summary_rows.append(srow)
            summary_df = pd.DataFrame(summary_rows)
        else:
            from collections import Counter
            dist_counts = Counter(town_district.values())
            summary_rows = []
            for d in range(0, 6):
                label = "Unassigned" if d == 0 else f"District {d}"
                summary_rows.append({
                    "district": label,
                    "town_count": dist_counts.get(d, 0),
                    "compactness_pp": compactness.get(d) if d > 0 else None,
                })
            summary_df = pd.DataFrame(summary_rows)

        import io
        buf = io.StringIO()
        buf.write("# DISTRICT SUMMARY\n")
        summary_df.to_csv(buf, index=False)
        buf.write("\n# TOWN-LEVEL ASSIGNMENTS\n")
        town_df.to_csv(buf, index=False)
        buf.seek(0)
        yield buf.read()

    # ----------------------------------------------------------------
    # Voter Registration Heatmap
    # ----------------------------------------------------------------
    @output
    @render.ui
    def heatmap_ui():
        town_field = town_name_field

        heatmap_html = f"""
        <div id="heatmap" style="width:100%;height:calc(100vh - 90px);"></div>
        <script>
        (function() {{
            if (window._ctHeatMap) {{
                window._ctHeatMap.remove();
                window._ctHeatMap = null;
            }}

            var map = L.map('heatmap', {{ zoomControl: true }}).setView([41.6, -72.7], 8);
            window._ctHeatMap = map;

            L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                attribution: '&copy; OpenStreetMap contributors',
                maxZoom: 19,
                opacity: 0.30
            }}).addTo(map);

            var townField   = "{town_field}";
            var geojsonData = {heatmap_geojson_str};

            function leanToColor(lean) {{
                lean = Math.max(-1, Math.min(1, lean));
                var r, g, b;
                if (lean < 0) {{
                    var t = -lean;
                    r = Math.round(255 + (204 - 255) * t);
                    g = Math.round(255 + (  0 - 255) * t);
                    b = Math.round(255 + (  0 - 255) * t);
                }} else if (lean > 0) {{
                    var t = lean;
                    r = Math.round(255 + (  0 - 255) * t);
                    g = Math.round(255 + ( 51 - 255) * t);
                    b = Math.round(255 + (204 - 255) * t);
                }} else {{
                    r = 255; g = 255; b = 255;
                }}
                return 'rgb(' + r + ',' + g + ',' + b + ')';
            }}

            var geojsonLayer = L.geoJSON(geojsonData, {{
                style: function(feature) {{
                    return {{
                        color: "#888",
                        weight: 0.8,
                        fillColor: leanToColor(feature.properties.lean || 0),
                        fillOpacity: 0.88
                    }};
                }},
                onEachFeature: function(feature, layer) {{
                    var name  = feature.properties[townField] || "Unknown";
                    var lean  = feature.properties.lean || 0;
                    var diff  = feature.properties.reg_diff || 0;
                    var pct   = Math.abs(lean * 100).toFixed(1);
                    var party = lean > 0 ? "Dem" : lean < 0 ? "Rep" : "Tied";

                    var absDiff = Math.abs(diff);
                    var diffFormatted = absDiff.toLocaleString();
                    var diffLabel = "";
                    if (diff > 0) {{
                        diffLabel = '+' + diffFormatted + ' Democrats';
                    }} else if (diff < 0) {{
                        diffLabel = '+' + diffFormatted + ' Republicans';
                    }} else {{
                        diffLabel = 'Even';
                    }}

                    var tipHtml =
                        '<div style="font-weight:700;font-size:1em;margin-bottom:3px">' + name + '</div>' +
                        '<div style="font-size:0.9em;color:#444">' +
                            party + (lean !== 0 ? ' +' + pct + '%' : '') +
                        '</div>' +
                        '<div style="font-size:0.85em;color:#666;margin-top:2px">' + diffLabel + '</div>';

                    layer.bindTooltip(tipHtml, {{sticky: true}});
                    layer.on('mouseover', function(e) {{
                        e.target.setStyle({{ weight: 2, color: '#333', fillOpacity: 0.98 }});
                    }});
                    layer.on('mouseout', function(e) {{
                        geojsonLayer.resetStyle(e.target);
                    }});
                }}
            }}).addTo(map);

            map.fitBounds(geojsonLayer.getBounds());

            var legend = L.control({{position: 'bottomright'}});
            legend.onAdd = function() {{
                var div = L.DomUtil.create('div');
                div.style.cssText =
                    'background:white;padding:10px 14px;border-radius:6px;' +
                    'box-shadow:0 2px 10px rgba(0,0,0,0.4);font-size:12px;' +
                    'line-height:1.5;min-width:200px;z-index:9999;position:relative;';
                div.innerHTML =
                    '<div style="font-weight:700;margin-bottom:8px;font-size:13px">2020 Voter Registration</div>' +
                    '<div style="font-size:11px;font-weight:700;color:#cc0000;margin-bottom:3px;">&#9632; Republican</div>' +
                    '<div style="height:14px;width:170px;border-radius:3px;margin-bottom:3px;' +
                         'background:linear-gradient(to right,#ffffff,#cc0000);' +
                         'border:1px solid rgba(0,0,0,0.1)"></div>' +
                    '<div style="display:flex;justify-content:space-between;width:170px;font-size:10px;color:#666;margin-bottom:8px">' +
                         '<span>Low majority</span><span>High majority</span></div>' +
                    '<div style="font-size:11px;font-weight:700;color:#0033cc;margin-bottom:3px;">&#9632; Democrat</div>' +
                    '<div style="height:14px;width:170px;border-radius:3px;margin-bottom:3px;' +
                         'background:linear-gradient(to right,#ffffff,#0033cc);' +
                         'border:1px solid rgba(0,0,0,0.1)"></div>' +
                    '<div style="display:flex;justify-content:space-between;width:170px;font-size:10px;color:#666">' +
                         '<span>Low majority</span><span>High majority</span></div>';
                return div;
            }};
            legend.addTo(map);
        }})();
        </script>
        """
        return ui.HTML(heatmap_html)

    # ----------------------------------------------------------------
    # Population Density Map
    # ----------------------------------------------------------------
    @output
    @render.ui
    def popdensity_ui():
        town_field = town_name_field

        popdensity_html = f"""
        <div id="popdensitymap" style="width:100%;height:calc(100vh - 90px);"></div>
        <script>
        (function() {{
            if (window._ctPopMap) {{
                window._ctPopMap.remove();
                window._ctPopMap = null;
            }}

            var map = L.map('popdensitymap', {{ zoomControl: true }}).setView([41.6, -72.7], 8);
            window._ctPopMap = map;

            L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                attribution: '&copy; OpenStreetMap contributors',
                maxZoom: 19,
                opacity: 0.25
            }}).addTo(map);

            var townField   = "{town_field}";
            var geojsonData = {popdensity_geojson_str};

            var popValues = geojsonData.features
                .map(function(f) {{ return f.properties.pop_total || 0; }})
                .filter(function(v) {{ return v > 0; }});
            var popMin = Math.min.apply(null, popValues);
            var popMax = Math.max.apply(null, popValues);

            function popToColor(pop) {{
                if (popMax === popMin) return 'rgb(100,0,150)';
                var normRaw = (pop - popMin) / (popMax - popMin);
                var t = Math.sqrt(Math.max(0, Math.min(1, normRaw)));
                var r = Math.round(232 + (59  - 232) * t);
                var g = Math.round(213 + (7   - 213) * t);
                var b = Math.round(245 + (100 - 245) * t);
                return 'rgb(' + r + ',' + g + ',' + b + ')';
            }}

            var geojsonLayer = L.geoJSON(geojsonData, {{
                style: function(feature) {{
                    var pop = feature.properties.pop_total || 0;
                    return {{
                        color: "#666",
                        weight: 0.8,
                        fillColor: popToColor(pop),
                        fillOpacity: 0.88
                    }};
                }},
                onEachFeature: function(feature, layer) {{
                    var name = feature.properties[townField] || "Unknown";
                    var pop  = feature.properties.pop_total || 0;
                    var popFmt = pop.toLocaleString();

                    var tipHtml =
                        '<div style="font-weight:700;font-size:1em;margin-bottom:3px">' + name + '</div>' +
                        '<div style="font-size:0.9em;color:#444">Population: <strong>' + popFmt + '</strong></div>';

                    layer.bindTooltip(tipHtml, {{sticky: true}});
                    layer.on('mouseover', function(e) {{
                        e.target.setStyle({{ weight: 2, color: '#222', fillOpacity: 0.98 }});
                    }});
                    layer.on('mouseout', function(e) {{
                        geojsonLayer.resetStyle(e.target);
                    }});
                }}
            }}).addTo(map);

            map.fitBounds(geojsonLayer.getBounds());

            var legend = L.control({{position: 'bottomright'}});
            legend.onAdd = function() {{
                var div = L.DomUtil.create('div');
                div.style.cssText =
                    'background:white;padding:10px 14px;border-radius:6px;' +
                    'box-shadow:0 2px 10px rgba(0,0,0,0.4);font-size:12px;' +
                    'line-height:1.5;min-width:200px;z-index:9999;position:relative;';
                div.innerHTML =
                    '<div style="font-weight:700;margin-bottom:8px;font-size:13px">2020 Population</div>' +
                    '<div style="height:14px;width:170px;border-radius:3px;margin-bottom:4px;' +
                         'background:linear-gradient(to right,#e8d5f5,#3b0764);' +
                         'border:1px solid rgba(0,0,0,0.1)"></div>' +
                    '<div style="display:flex;justify-content:space-between;width:170px;font-size:10px;color:#666">' +
                         '<span>Lower</span><span>Higher</span></div>' +
                    '<div style="margin-top:6px;font-size:10px;color:#888">Pop. range: ' +
                         popMin.toLocaleString() + ' \u2013 ' + popMax.toLocaleString() + '</div>';
                return div;
            }};
            legend.addTo(map);
        }})();
        </script>
        """
        return ui.HTML(popdensity_html)


app = App(app_ui, server)
