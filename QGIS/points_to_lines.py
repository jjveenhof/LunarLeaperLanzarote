"""
Convert GPR GNSS point CSVs to GeoJSON line files for QGIS.

Inputs:
    Data/GNSS/Cleaned/CleanedGNSS_GPR_Lines.csv
    Data/GNSS/Cleaned/CleanedGNSS_GPR_FlowerPetals.csv

Outputs:
    Data/GNSS/Cleaned/GPR_Lines.geojson
    Data/GNSS/Cleaned/GPR_FlowerPetals.geojson

CRS: REGCAN95 / UTM zone 27N (EPSG:4083)
"""

import json
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).parents[2] / "Data" / "GNSS" / "Cleaned"

EPSG = 4083

# Order field per line group
LINE_ORDER = {
    2: "Time",
    3: "Meter",
    5: "Meter",
}

PETAL_LINES = ["FP1", "FP2", "FP3"]


def make_feature(coords, line_id):
    return {
        "type": "Feature",
        "properties": {"line": str(line_id)},
        "geometry": {
            "type": "LineString",
            "coordinates": [[e, n] for e, n in coords],
        },
    }


def points_to_lines(df, groups, order_field_map):
    features = []
    for line_id, order_field in order_field_map.items():
        pts = df[df["Line"] == line_id].copy()
        if pts.empty:
            print(f"Warning: no points found for line {line_id}")
            continue
        pts = pts.sort_values(order_field)
        coords = list(zip(pts["Easting"], pts["Northing"]))
        features.append(make_feature(coords, line_id))
    return features


def petals_to_lines(df, petal_ids):
    features = []
    for fp in petal_ids:
        pts = df[df["Line"] == fp].copy()
        if pts.empty:
            print(f"Warning: no points found for {fp}")
            continue
        pts = pts.sort_values("Time")
        coords = list(zip(pts["Easting"], pts["Northing"]))
        features.append(make_feature(coords, fp))
    return features


def write_geojson(features, path):
    geojson = {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {"name": f"urn:ogc:def:crs:EPSG::{EPSG}"},
        },
        "features": features,
    }
    with open(path, "w") as f:
        json.dump(geojson, f, indent=2)
    print(f"Written: {path} ({len(features)} lines)")


def main():
    lines_csv = DATA_DIR / "CleanedGNSS_GPR_Lines.csv"
    petals_csv = DATA_DIR / "CleanedGNSS_GPR_FlowerPetals.csv"

    lines_df = pd.read_csv(lines_csv)
    lines_df["Time"] = pd.to_datetime(lines_df["Time"], format="%d.%m.%Y %H:%M:%S")
    petals_df = pd.read_csv(petals_csv)
    petals_df["Time"] = pd.to_datetime(petals_df["Time"], format="%d.%m.%Y %H:%M:%S")

    line_features = points_to_lines(lines_df, LINE_ORDER.keys(), LINE_ORDER)
    write_geojson(line_features, DATA_DIR / "GPR_Lines.geojson")

    petal_features = petals_to_lines(petals_df, PETAL_LINES)
    write_geojson(petal_features, DATA_DIR / "GPR_FlowerPetals.geojson")


if __name__ == "__main__":
    main()
