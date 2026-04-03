import geopandas as gpd
import pandas as pd
import numpy as np
import h3
import osmnx as ox
from shapely.geometry import box, Polygon
from sklearn.preprocessing import MinMaxScaler
import json
import warnings

warnings.filterwarnings('ignore')

CRS_PROJ = "EPSG:3857"


def load_presets(filepath="tags_presets.json"):
    """Загружает пресеты тегов из JSON."""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)["presets"]


def load_osm_data(bbox, tags_config):
    """
    Загружает данные из OpenStreetMap.
    Логика из оригинального пайплайна.
    """
    west, south, east, north = bbox
    data = {}
    
    for tag in tags_config:
        name = tag["name"]
        osm_tag = {tag["key"]: tag["value"]}
        
        print(f"Загрузка {name}...")
        
        try:
            gdf = ox.features_from_bbox((west, south, east, north), tags=osm_tag)
            gdf = gdf.to_crs(CRS_PROJ)
            data[name] = gdf
            print(f"  Найдено: {len(gdf)} объектов")
        except Exception as e:
            print(f"  Нет данных для {name}: {e}")
            data[name] = gpd.GeoDataFrame(columns=['geometry'], crs=CRS_PROJ)
    
    return data


def create_h3_grid(bbox, resolution=9):
    """Создаёт гексагональную сетку H3."""
    bbox_polygon = box(*bbox)
    h3_indexes = list(h3.polyfill_geojson(bbox_polygon.__geo_interface__, resolution))
    
    if not h3_indexes:
        west, south, east, north = bbox
        center_lat = (south + north) / 2
        center_lng = (west + east) / 2
        h3_indexes = [h3.geo_to_h3(center_lat, center_lng, resolution)]
    
    h3_geometries = [Polygon(h3.h3_to_geo_boundary(h, geo_json=True)) for h in h3_indexes]
    
    h3_gdf = gpd.GeoDataFrame(
        {'h3_index': h3_indexes, 'geometry': h3_geometries},
        crs="EPSG:4326"
    ).to_crs(CRS_PROJ)
    
    return h3_gdf


def analyze_h3_cell(geom, data, tags_config):
    """Анализирует одну ячейку H3 с буферными зонами."""
    results = {}
    
    for tag in tags_config:
        name = tag["name"]
        buffer_radius = tag.get("buffer", 800)
        buffer_zone = geom.buffer(buffer_radius)
        
        if name not in data or data[name].empty:
            results[name] = 0
            continue
        
        gdf = data[name]
        
        try:
            intersecting = gdf[gdf.geometry.intersects(buffer_zone)]
            
            if intersecting.empty:
                results[name] = 0
            elif intersecting.geometry.iloc[0].geom_type in ['Point', 'MultiPoint']:
                results[name] = len(intersecting)
            elif intersecting.geometry.iloc[0].geom_type in ['LineString', 'MultiLineString']:
                results[name] = intersecting.geometry.length.sum()
            else:
                results[name] = intersecting.geometry.area.sum()
        except:
            results[name] = 0
    
    return results


def run_analysis(bbox, tags_config, weights=None, h3_resolution=9):
    """
    Запускает полный анализ.
    Возвращает: (h3_gdf с результатами, dict с OSM данными)
    """
    # 1. Загрузка данных
    print("=== Загрузка данных из OSM ===")
    data = load_osm_data(bbox, tags_config)
    
    # 2. Создание H3 сетки
    print("=== Создание H3 сетки ===")
    h3_gdf = create_h3_grid(bbox, h3_resolution)
    print(f"Создано ячеек: {len(h3_gdf)}")
    
    # 3. Анализ каждой ячейки
    print("=== Анализ ячеек ===")
    feature_names = [tag["name"] for tag in tags_config]
    
    results_list = []
    for idx, row in h3_gdf.iterrows():
        cell_results = analyze_h3_cell(row.geometry, data, tags_config)
        results_list.append(cell_results)
    
    results_df = pd.DataFrame(results_list)
    
    for col in feature_names:
        if col in results_df.columns:
            h3_gdf[col] = results_df[col].values
        else:
            h3_gdf[col] = 0
    
    # 4. Нормализация MinMax
    print("=== Нормализация ===")
    scaler = MinMaxScaler()
    
    if h3_gdf[feature_names].sum().sum() > 0:
        h3_gdf[feature_names] = scaler.fit_transform(h3_gdf[feature_names])
    
    # 5. Расчёт индекса
    print("=== Расчёт индекса ===")
    if weights and any(weights.values()):
        weights_array = np.array([weights.get(name, 1.0) for name in feature_names])
        weights_array = weights_array / weights_array.sum()
        h3_gdf['index_score'] = h3_gdf[feature_names].values @ weights_array
    else:
        # h3_gdf['index_score'] = h3_gdf[feature_names].mean(axis=1)
        h3_gdf['index_score'] = h3_gdf[feature_names].sum(axis=1)

    
    print("=== Готово ===")
    return h3_gdf, data
