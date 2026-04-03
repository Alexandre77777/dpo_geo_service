import streamlit as st
import folium
from folium.features import GeoJsonTooltip
from folium.plugins import Draw
from streamlit_folium import st_folium
import branca.colormap as cm

from backend import load_presets, run_analysis

#                        ОБЩИЕ НАСТРОЙКИ 
st.set_page_config(
    page_title="DPO Geo-Service",
    page_icon="🗺️",
    layout="wide",
)

#                              SESSION STATE 
for k, v in {"custom_tags": [], "results": None, "bbox": None}.items():
    st.session_state.setdefault(k, v)

presets = load_presets()
has_results = st.session_state.results is not None
results_geo = st.session_state.results.to_crs("EPSG:4326") if has_results else None

# Под шапкой браузера сразу: карта и панель настроек
map_col, control_col = st.columns([5, 2])

#                          ПАНЕЛЬ СПРАВА                          
with control_col:
    st.markdown("### 🌍 Геоаналитический сервис")
    st.caption("Буферный анализ инфраструктуры на H3‑сетке по данным OpenStreetMap")

    status_placeholder = st.empty()

    if st.session_state.bbox:
        st.success("Область выбрана на карте")
    else:
        st.warning("Слева на карте нарисуйте прямоугольник или полигон для анализа")

    btn_run_col, btn_clear_col = st.columns(2)
    run_btn = btn_run_col.button(
        "Запустить анализ",
        type="primary",
        use_container_width=True,
    )
    clear_btn = btn_clear_col.button(
        "Очистить результат",
        use_container_width=True,
        disabled=not has_results,
    )

    if results_geo is not None:
        st.download_button(
            "🗺️ Экспорт результата (GeoJSON)",
            results_geo.to_json(),
            "results.geojson",
            "application/json",
            use_container_width=True,
        )

    st.markdown("---")

    h3_res = st.select_slider(
        "Разрешение H3‑сетки", options=[7, 8, 9, 10], value=9
    )

    st.markdown("---")

    st.markdown("**Предустановленные слои**")
    preset_names = [p["name"] for p in presets]
    selected_names = st.multiselect(
        "Выберите слои:",
        options=preset_names,
        default=preset_names[:2],
    )
    selected_tags = [p.copy() for p in presets if p["name"] in selected_names]

    # ---- пользовательские слои ----
    with st.expander("Добавить свой слой"):
        c_name = st.text_input("Название слоя", key="c_name")
        c_key = st.text_input("OSM key", key="c_key", placeholder="amenity")
        c_value = st.text_input("OSM value", key="c_value", placeholder="pharmacy")
        c_buffer = st.number_input("Буфер (м)", 100, 3000, 800, step=100, key="c_buffer")

        if st.button("Добавить слой"):
            if c_name and c_key and c_value:
                st.session_state.custom_tags.append(
                    {
                        "name": c_name,
                        "key": c_key,
                        "value": c_value,
                        "buffer": c_buffer,
                        "default_weight": 0.2,
                    }
                )
                st.rerun()

    for i, t in enumerate(st.session_state.custom_tags):
        cc1, cc2 = st.columns([4, 1])
        cc1.write(f"• {t['name']}")
        if cc2.button("✖", key=f"del_{i}"):
            st.session_state.custom_tags.pop(i)
            st.rerun()

    all_tags = selected_tags + st.session_state.custom_tags

    st.markdown("---")

    # ---- буферы и веса признаков ----
    weights = {}
    if all_tags:
        st.markdown("**Буферы и веса признаков**")
        for tag in all_tags:
            col_buf, col_w = st.columns([2, 1])
            with col_buf:
                tag["buffer"] = st.number_input(
                    f"{tag['name']} (м)",
                    min_value=100,
                    max_value=3000,
                    value=int(tag.get("buffer", 800)),
                    step=100,
                    key=f"buf_{tag['name']}",
                )
            with col_w:
                weights[tag["name"]] = st.slider(
                    "Вес",
                    min_value=-1.0,
                    max_value=1.0,
                    value=0.0,
                    step=0.05,
                    key=f"w_{tag['name']}",
                )
    else:
        st.info("Добавьте хотя бы один слой для анализа.")

# ================== КАРТА СЛЕВА ==================
with map_col:
    m = folium.Map(
        location=[55.75, 37.62],
        zoom_start=11,
        attributionControl=False,
    )

    Draw(
        draw_options={
            "polyline": False,
            "polygon": True,
            "circle": False,
            "marker": False,
            "circlemarker": False,
            "rectangle": True,
        },
        edit_options={"edit": False},
    ).add_to(m)

    if results_geo is not None:
        min_val = float(results_geo["index_score"].min())
        max_val = float(results_geo["index_score"].max())

        colormap = cm.StepColormap(
            colors=["#d73027", "#fc8d59", "#fee08b", "#d9ef8b", "#1a9850"],
            vmin=min_val,
            vmax=max_val,
            caption="Индекс обеспеченности",
        )

        def style_function(feature):
            score = feature["properties"]["index_score"]
            return {
                "fillColor": colormap(score),
                "color": "black",
                "weight": 0.5,
                "fillOpacity": 0.6,
            }

        feature_names = [
            c
            for c in results_geo.columns
            if c not in ("geometry", "index_score", "h3_index")
        ]
        tooltip_fields = ["index_score"] + feature_names
        tooltip_aliases = ["Индекс (общий):"] + [f"{name}:" for name in feature_names]

        folium.GeoJson(
            results_geo.to_json(),
            name="Результаты (общий индекс)",
            style_function=style_function,
            tooltip=GeoJsonTooltip(
                fields=tooltip_fields,
                aliases=tooltip_aliases,
                localize=True,
                sticky=True,
            ),
            show=True,
        ).add_to(m)

        colormap.add_to(m)
        folium.LayerControl().add_to(m)

        b = results_geo.total_bounds
        m.fit_bounds([[b[1], b[0]], [b[3], b[2]]])

    output = st_folium(
        m,
        use_container_width=True,
        height=1000,
        key="map",
    )

    if output and output.get("all_drawings"):
        geom = output["all_drawings"][-1].get("geometry", {})
        gtype = geom.get("type")
        coords = None
        if gtype == "Polygon":
            coords = geom["coordinates"][0]
        elif gtype == "MultiPolygon":
            coords = geom["coordinates"][0][0]

        if coords:
            lons, lats = zip(*coords)
            st.session_state.bbox = [min(lons), min(lats), max(lons), max(lats)]

#                         ЛОГИКА КНОПОК 
with control_col:
    if clear_btn and has_results:
        st.session_state.results = None
        st.rerun()

    if run_btn:
        if not st.session_state.bbox:
            st.error("Сначала выберите область на карте!")
        elif not all_tags:
            st.error("Добавьте хотя бы один слой!")
        else:
            effective_weights = {n: w for n, w in weights.items() if abs(w) > 1e-6} or None
            with status_placeholder.container():
                with st.spinner("Выполняется анализ..."):
                    try:
                        res = run_analysis(
                            bbox=st.session_state.bbox,
                            tags_config=all_tags,
                            weights=effective_weights,
                            h3_resolution=h3_res,
                        )
                        st.session_state.results = (
                            res[0] if isinstance(res, tuple) else res
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"Ошибка: {e}")