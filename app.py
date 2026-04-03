# ═══════════════════════════════════════════════════════════════════════════
# app.py — Фронтенд геоаналитического сервиса
# ═══════════════════════════════════════════════════════════════════════════
#
# Этот модуль реализует пользовательский интерфейс:
# - Интерактивная карта для выбора области
# - Панель настройки параметров анализа
# - Визуализация результатов
# - Экспорт данных
#
# Фреймворк: Streamlit (декларативный UI на Python)
# Карта: Folium (обёртка над Leaflet.js)
# ═══════════════════════════════════════════════════════════════════════════

# ---------------------------------------------------------------------------
# ИМПОРТ БИБЛИОТЕК
# ---------------------------------------------------------------------------

# Streamlit — фреймворк для создания веб-интерфейса
import streamlit as st

# Folium — библиотека для создания интерактивных карт
# Под капотом использует JavaScript-библиотеку Leaflet
import folium
from folium.features import GeoJsonTooltip   # Всплывающие подсказки
from folium.plugins import Draw              # Инструменты рисования

# Интеграция Folium со Streamlit
from streamlit_folium import st_folium

# Цветовые шкалы для карт
import branca.colormap as cm

# Импорт функций бэкенда
# Фронтенд знает только о публичном API бэкенда
from backend import load_presets, run_analysis

# ---------------------------------------------------------------------------
# КОНФИГУРАЦИЯ СТРАНИЦЫ
# ---------------------------------------------------------------------------
# set_page_config должен вызываться первым!

st.set_page_config(
    page_title="DPO Geo-Service",    # Заголовок вкладки браузера
    page_icon="🗺️",                   # Иконка (эмодзи или путь к файлу)
    layout="wide",                    # Широкий макет (для карты)
)

# ---------------------------------------------------------------------------
# ИНИЦИАЛИЗАЦИЯ SESSION STATE
# ---------------------------------------------------------------------------
#
# Session State — механизм Streamlit для сохранения данных между
# перезапусками скрипта. Без него при каждом действии пользователя
# все переменные сбрасывались бы.
#
# Жизненный цикл Streamlit:
# 1. Пользователь открывает страницу → скрипт выполняется
# 2. Пользователь нажимает кнопку → скрипт выполняется ЗАНОВО
# 3. Session State сохраняет данные между перезапусками

# Инициализация переменных состояния (если ещё не существуют)
for k, v in {
    "custom_tags": [],    # Пользовательские слои
    "results": None,      # Результаты анализа (GeoDataFrame)
    "bbox": None          # Выбранная область [west, south, east, north]
}.items():
    # setdefault добавляет значение только если ключ отсутствует
    st.session_state.setdefault(k, v)

# Загрузка предустановленных слоёв из конфигурации
# Это происходит при каждом запуске, но файл маленький
presets = load_presets()

# Флаги для условной отрисовки элементов
has_results = st.session_state.results is not None

# Подготовка результатов для карты (если есть)
# Карта Folium работает в EPSG:4326, поэтому перепроецируем
results_geo = (
    st.session_state.results.to_crs("EPSG:4326")
    if has_results
    else None
)

# ---------------------------------------------------------------------------
# СОЗДАНИЕ МАКЕТА СТРАНИЦЫ
# ---------------------------------------------------------------------------
#
# Двухколоночный макет:
# - Левая колонка (5 частей): карта
# - Правая колонка (2 части): панель управления

map_col, control_col = st.columns([5, 2])

# ═══════════════════════════════════════════════════════════════════════════
#                          ПАНЕЛЬ УПРАВЛЕНИЯ (ПРАВАЯ КОЛОНКА)
# ═══════════════════════════════════════════════════════════════════════════

with control_col:
    # ------------------------------------
    # Заголовок и описание
    # ------------------------------------
    st.markdown("### 🌍 Геоаналитический сервис")
    st.caption("Буферный анализ инфраструктуры на H3‑сетке по данным OpenStreetMap")
    
    # Контейнер для динамических сообщений
    # empty() создаёт placeholder, который можно заполнить позже
    status_placeholder = st.empty()
    
    # ------------------------------------
    # Индикатор выбора области
    # ------------------------------------
    if st.session_state.bbox:
        st.success("Область на карте выбрана ✅")
    else:
        st.warning("На карте слева нарисуйте прямоугольник или полигон для анализа")
    
    # ------------------------------------
    # Кнопки управления
    # ------------------------------------
    btn_run_col, btn_clear_col = st.columns(2)
    
    # Кнопка запуска анализа
    run_btn = btn_run_col.button(
        "Запустить анализ",
        type="primary",              # Выделенный стиль (синяя кнопка)
        use_container_width=True,    # Растянуть на всю ширину
    )
    
    # Кнопка очистки результатов
    clear_btn = btn_clear_col.button(
        "Очистить результат",
        use_container_width=True,
        disabled=not has_results,    # Неактивна, если нет результатов
    )
    
    # ------------------------------------
    # Кнопка экспорта результатов
    # ------------------------------------
    if results_geo is not None:
        st.download_button(
            "🗺️ Экспорт результата (GeoJSON)",
            results_geo.to_json(),        # Данные для скачивания
            "results.geojson",            # Имя файла
            "application/json",           # MIME-тип
            use_container_width=True,
        )
    
    st.markdown("---")  # Горизонтальный разделитель
    
    # ------------------------------------
    # Выбор разрешения H3
    # ------------------------------------
    h3_res = st.select_slider(
        "Разрешение H3‑сетки",
        options=[7, 8, 9, 10],    # Допустимые значения
        value=9                   # По умолчанию
    )
    
    st.markdown("---")
    
    # ------------------------------------
    # Выбор предустановленных слоёв
    # ------------------------------------
    st.markdown("**Предустановленные слои**")
    
    # Извлекаем названия для виджета multiselect
    preset_names = [p["name"] for p in presets]
    
    # Виджет множественного выбора
    selected_names = st.multiselect(
        "Выберите слои (тэги):",
        options=preset_names,
        default=preset_names[:2],    # По умолчанию первые два
    )
    
    # Фильтрация полных конфигураций по выбранным названиям
    # .copy() предотвращает мутацию исходных данных
    selected_tags = [p.copy() for p in presets if p["name"] in selected_names]
    
    # ------------------------------------
    # Добавление пользовательских слоёв
    # ------------------------------------
    with st.expander("Добавить свой слой (тэг)"):
        # Поля ввода для параметров нового слоя
        c_name = st.text_input("Название слоя", key="c_name")
        c_key = st.text_input("OSM key", key="c_key", placeholder="amenity")
        c_value = st.text_input("OSM value", key="c_value", placeholder="pharmacy")
        c_buffer = st.number_input(
            "Буфер (м)",
            min_value=100,
            max_value=3000,
            value=800,
            step=100,
            key="c_buffer"
        )
        
        if st.button("Добавить слой (тэг)"):
            # Валидация: все поля должны быть заполнены
            if c_name and c_key and c_value:
                # Добавляем в session state
                st.session_state.custom_tags.append({
                    "name": c_name,
                    "key": c_key,
                    "value": c_value,
                    "buffer": c_buffer,
                    "default_weight": 0.2,
                })
                # Перезапуск для обновления интерфейса
                st.rerun()
    
    # Отображение добавленных пользовательских слоёв
    for i, t in enumerate(st.session_state.custom_tags):
        cc1, cc2 = st.columns([4, 1])
        cc1.write(f"• {t['name']}")
        # Кнопка удаления
        if cc2.button("✖", key=f"del_{i}"):
            st.session_state.custom_tags.pop(i)
            st.rerun()
    
    # Объединение предустановленных и пользовательских слоёв
    all_tags = selected_tags + st.session_state.custom_tags
    
    st.markdown("---")
    
    # ------------------------------------
    # Настройка буферов и весов
    # ------------------------------------
    weights = {}
    
    if all_tags:
        st.markdown("**Буферы и веса признаков**")
        
        for tag in all_tags:
            col_buf, col_w = st.columns([2, 1])
            
            with col_buf:
                # Поле для настройки радиуса буфера
                tag["buffer"] = st.number_input(
                    f"{tag['name']} (м)",
                    min_value=100,
                    max_value=3000,
                    value=int(tag.get("buffer", 800)),
                    step=100,
                    key=f"buf_{tag['name']}",
                )
            
            with col_w:
                # Слайдер для веса признака
                # Диапазон [-1, 1] позволяет задать негативный фактор
                weights[tag["name"]] = st.slider(
                    "Вес",
                    min_value=-1.0,
                    max_value=1.0,
                    value=0.0,         # По умолчанию нейтральный
                    step=0.05,
                    key=f"w_{tag['name']}",
                )
    else:
        st.info("Добавьте хотя бы один слой (тэг) для анализа.")

# ═══════════════════════════════════════════════════════════════════════════
#                          КАРТА (ЛЕВАЯ КОЛОНКА)
# ═══════════════════════════════════════════════════════════════════════════

with map_col:
    # ------------------------------------
    # Создание базовой карты Folium
    # ------------------------------------
    m = folium.Map(
        location=[55.75, 37.62],      # Центр карты (Москва)
        zoom_start=11,                 # Начальный масштаб
        attributionControl=False,      # Скрыть атрибуцию
    )
    
    # ------------------------------------
    # Добавление инструментов рисования
    # ------------------------------------
    # Draw plugin позволяет пользователю рисовать фигуры на карте
    Draw(
        draw_options={
            "polyline": False,         # Отключить рисование линий
            "polygon": True,           # Разрешить полигоны
            "circle": False,           # Отключить круги
            "marker": False,           # Отключить маркеры
            "circlemarker": False,     # Отключить круглые маркеры
            "rectangle": True,         # Разрешить прямоугольники
        },
        edit_options={"edit": False},  # Запретить редактирование
    ).add_to(m)
    
    # ------------------------------------
    # Визуализация результатов анализа
    # ------------------------------------
    if results_geo is not None:
        # Определение диапазона значений для цветовой шкалы
        min_val = float(results_geo["index_score"].min())
        max_val = float(results_geo["index_score"].max())
        
        # Создание ступенчатой цветовой шкалы
        # Палитра: красный → жёлтый → зелёный (плохо → хорошо)
        colormap = cm.StepColormap(
            colors=["#d73027", "#fc8d59", "#fee08b", "#d9ef8b", "#1a9850"],
            vmin=min_val,
            vmax=max_val,
            caption="Индекс обеспеченности",
        )
        
        # Функция стилизации для каждого гексагона
        def style_function(feature):
            score = feature["properties"]["index_score"]
            return {
                "fillColor": colormap(score),    # Цвет заливки
                "color": "black",                 # Цвет границы
                "weight": 0.5,                    # Толщина границы
                "fillOpacity": 0.6,               # Прозрачность
            }
        
        # Подготовка полей для всплывающих подсказок
        feature_names = [
            c for c in results_geo.columns
            if c not in ("geometry", "index_score", "h3_index")
        ]
        tooltip_fields = ["index_score"] + feature_names
        tooltip_aliases = ["Индекс (общий):"] + [f"{name}:" for name in feature_names]
        
        # Добавление слоя GeoJSON с результатами
        folium.GeoJson(
            results_geo.to_json(),
            name="Результаты (общий индекс)",
            style_function=style_function,
            tooltip=GeoJsonTooltip(
                fields=tooltip_fields,
                aliases=tooltip_aliases,
                localize=True,           # Локализация чисел
                sticky=True,             # Подсказка следует за курсором
            ),
            show=True,
        ).add_to(m)
        
        # Добавление легенды
        colormap.add_to(m)
        
        # Панель управления слоями
        folium.LayerControl().add_to(m)
        
        # Автоматическое масштабирование к результатам
        b = results_geo.total_bounds  # [minx, miny, maxx, maxy]
        m.fit_bounds([[b[1], b[0]], [b[3], b[2]]])
    
    # ------------------------------------
    # Отображение карты в Streamlit
    # ------------------------------------
    output = st_folium(
        m,
        use_container_width=True,
        height=1000,
        key="map",
    )
    
    # ------------------------------------
    # Обработка нарисованных фигур
    # ------------------------------------
    if output and output.get("all_drawings"):
        # Извлечение последней нарисованной фигуры
        geom = output["all_drawings"][-1].get("geometry", {})
        gtype = geom.get("type")
        coords = None
        
        # Извлечение координат в зависимости от типа
        if gtype == "Polygon":
            coords = geom["coordinates"][0]
        elif gtype == "MultiPolygon":
            coords = geom["coordinates"][0][0]
        
        if coords:
            # Вычисление bounding box
            lons, lats = zip(*coords)
            st.session_state.bbox = [
                min(lons), min(lats),    # west, south
                max(lons), max(lats)     # east, north
            ]

# ═══════════════════════════════════════════════════════════════════════════
#                          ЛОГИКА КНОПОК
# ═══════════════════════════════════════════════════════════════════════════

with control_col:
    # ------------------------------------
    # Обработка кнопки "Очистить"
    # ------------------------------------
    if clear_btn and has_results:
        st.session_state.results = None
        st.rerun()
    
    # ------------------------------------
    # Обработка кнопки "Запустить анализ"
    # ------------------------------------
    if run_btn:
        # Валидация входных данных
        if not st.session_state.bbox:
            st.error("Сначала выберите область на карте!")
        elif not all_tags:
            st.error("Добавьте хотя бы один слой (тэг)!")
        else:
            # Фильтрация нулевых весов
            effective_weights = {
                n: w for n, w in weights.items()
                if abs(w) > 1e-6
            } or None
            
            # Показываем индикатор загрузки
            with status_placeholder.container():
                with st.spinner("Выполняется анализ..."):
                    try:
                        # ═══════════════════════════════════
                        # ВЫЗОВ БЭКЕНДА
                        # ═══════════════════════════════════
                        # Это единственное место, где фронтенд
                        # взаимодействует с бэкендом
                        res = run_analysis(
                            bbox=st.session_state.bbox,
                            tags_config=all_tags,
                            weights=effective_weights,
                            h3_resolution=h3_res,
                        )
                        
                        # Сохраняем результаты в session state
                        st.session_state.results = (
                            res[0] if isinstance(res, tuple) else res
                        )
                        
                        # Перезапуск для отображения результатов
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"Ошибка: {e}")