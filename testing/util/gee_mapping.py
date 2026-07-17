import ee
import pandas as pd

from ...app.config import LAT, LON, GEE_PROJECT, GEE_MAP

def get_clc_mapping(input: str, output: str):
    ee.Initialize(project=GEE_PROJECT)

    df = pd.read_csv(input)

    features = []
    for _, row in df.iterrows():
        if pd.isna(row[LON]) or pd.isna(row[LAT]):
            continue
        geom = ee.Geometry.Point([row[LON], row[LAT]])
        features.append(ee.Feature(geom, {'row_id': row['row_id']}))

    fc = ee.FeatureCollection(features)

    corine = ee.Image(GEE_MAP).select('landcover')

    sampled = corine.sampleRegions(collection=fc, scale=100, geometries=True)
    rows = [f['properties'] for f in sampled.getInfo()['features']]
    pd.DataFrame(rows).to_csv(output, index=False)

if __name__ == '__main__':
    pass
