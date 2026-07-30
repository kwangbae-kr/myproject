import csv
import gzip
import io
import json
import urllib.request
import plotly.express as px
import streamlit as st

# ==========================================
# 1. 페이지 설정 및 완벽한 배경 커스텀 CSS 적용
# ==========================================
st.set_page_config(
    page_title="대한민국 시군구별 미래 인구 & 고령화 예측",
    page_icon="🗺️",
    layout="wide",
)

st.markdown(
    """
    <style>
        /* 1. 전체 웹 앱의 배경색과 기본 폰트 색상 지정 */
        .stApp {
            background-color: #f0f4f8;
            color: #1e293b;
        }

        /* 2. 사이드바 배경 및 테두리 꾸미기 */
        [data-testid="stSidebar"] {
            background-color: #ffffff;
            border-right: 1px solid #e2e8f0;
        }

        /* 3. 상단 헤더 배너 카드 디자인 */
        .header-container {
            background: linear-gradient(135deg, #1e293b, #0f172a);
            padding: 35px;
            border-radius: 16px;
            color: white;
            margin-bottom: 25px;
            box-shadow: 0 10px 25px rgba(15, 23, 42, 0.1);
        }
        .header-title {
            font-size: 28px;
            font-weight: 800;
            margin-bottom: 10px;
            letter-spacing: -0.5px;
        }
        .header-subtitle {
            font-size: 15px;
            color: #94a3b8;
            font-weight: 400;
        }

        /* 4. 데이터프레임(표) 주변 배경 카드 효과 */
        .stDataFrame {
            background-color: #ffffff;
            padding: 10px;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.03);
            border: 1px solid #e2e8f0;
        }

        /* 5. 구분선 색상 부드럽게 조정 */
        hr {
            border-color: #cbd5e1;
        }
    </style>
""",
    unsafe_allow_html=True,
)


# ==========================================
# 2. 데이터 불러오기 및 10년 단위 누적 예측 함수
# ==========================================
@st.cache_data
def load_base_data():
    pop_url = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
    geojson_url = (
        "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"
    )

    with urllib.request.urlopen(geojson_url) as response:
        geojson_data = json.loads(response.read().decode("utf-8"))

    with urllib.request.urlopen(pop_url) as response:
        compressed_data = response.read()

    with gzip.GzipFile(fileobj=io.BytesIO(compressed_data)) as gz:
        file_content = gz.read().decode("utf-8")

    reader = csv.DictReader(io.StringIO(file_content))
    rows = list(reader)

    if rows:
        cleaned_keys = {k: k.strip() for k in rows[0].keys()}
        rows = [{cleaned_keys.get(k, k): v for k, v in row.items()} for row in rows]

    years = [int(row["연도"]) for row in rows if row.get("연도")]
    latest_year = max(years)

    sample_row = rows[0]
    age_columns = [
        col
        for col in sample_row.keys()
        if col and col.startswith("계_") and col != "계_계"
    ]

    age_map = {}
    for col in age_columns:
        age_str = col.replace("계_", "").replace("세", "").replace(" 이상", "")
        if age_str.isdigit():
            age_map[col] = int(age_str)

    sigungu_raw = {}

    for row in rows:
        year_val = row.get("연도") or row.get(" 연도")
        if not year_val or int(year_val) != latest_year:
            continue

        code = row.get("코드", "").strip()
        if len(code) < 5:
            continue

        sigungu_code = code[:5]
        sido = row.get("시도", "").strip()
        sigungu_name = row.get("시군구", "").strip()

        if sigungu_code not in sigungu_raw:
            sigungu_raw[sigungu_code] = {
                "시군구코드": sigungu_code,
                "시도": sido,
                "시군구": sigungu_name,
                "ages": {i: 0 for i in range(101)},
            }

        for col, age_val in age_map.items():
            val_str = row.get(col, "0").replace(",", "").strip()
            if not val_str:
                continue
            try:
                val = int(val_str)
            except ValueError:
                val = 0
            target_age = min(age_val, 100)
            sigungu_raw[sigungu_code]["ages"][target_age] += val

    return latest_year, sigungu_raw, geojson_data


with st.spinner("기본 인구 데이터를 불러오는 중입니다..."):
    latest_year, base_sigungu_raw, sigungu_geojson = load_base_data()


# ==========================================
# 3. 사이드바 설정 (미래 예측 연도 선택 기능)
# ==========================================
with st.sidebar:
    st.markdown("### 🧭 대시보드 안내")
    st.markdown(
        "본 앱은 최신 행정안전부 연령별 인구 데이터를 바탕으로 **코호트 이동 방식**을 적용하여 미래 인구 구조 변화와 고령화율을 시각화합니다."
    )
    st.markdown("---")

    st.markdown("### ⏳ 미래 예측 시점 선택")
    forecast_years_choice = st.select_slider(
        "현재 기준 몇 년 후를 예측할까요?",
        options=[10, 20, 30, 40, 50, 100],
        value=10,
        format_func=lambda x: f"{x}년 후 ({latest_year + x}년)",
    )

    target_year = latest_year + forecast_years_choice
    steps = forecast_years_choice // 10

    st.markdown("---")
    st.markdown("🔥 **고령화 단계별 심각도**")
    st.markdown(
        """
    - 🟨 **19% 미만** (안정)
    - 🟧 **19% ~ 23%** (주의)
    - 🟥 **23% ~ 28%** (경계)
    - 🟫 **28% ~ 38%** (심각)
    - ⬛ **38% 이상** (초고위험)
    """
    )
    st.markdown("---")
    st.caption("Informatics Educational Dashboard")


# ==========================================
# 4. 선택한 년도(steps)만큼 시뮬레이션 반복 실행
# ==========================================
def simulate_future(base_data, num_steps):
    processed_list = []

    for code, info in base_data.items():
        curr_ages = info["ages"].copy()

        # 현재 기준 데이터 계산
        curr_total = sum(curr_ages.values())
        curr_elderly = sum(curr_ages[a] for a in range(65, 101))
        curr_rate = (curr_elderly / curr_total * 100) if curr_total > 0 else 0

        # 지정된 10년 단위 횟수(steps)만큼 코호트 시뮬레이션 반복
        future_ages = curr_ages.copy()
        for _ in range(num_steps):
            next_ages = {i: 0 for i in range(101)}

            for age in range(91):
                f_age = age + 10
                survived_pop = int(future_ages[age] * 0.98)
                if f_age <= 100:
                    next_ages[f_age] += survived_pop
                else:
                    next_ages[100] += survived_pop

            old_survived = sum(
                int(future_ages[a] * 0.85) for a in range(91, 101)
            )
            next_ages[100] += old_survived

            recent_child_avg = sum(next_ages[a] for a in range(10)) / 10
            for age in range(10):
                next_ages[age] = int(recent_child_avg * 0.70)

            future_ages = next_ages

        future_total = sum(future_ages.values())
        future_elderly = sum(future_ages[a] for a in range(65, 101))
        future_rate = (
            (future_elderly / future_total * 100) if future_total > 0 else 0
        )

        def get_generations(ages_dict):
            return {
                "0~9세": sum(ages_dict[a] for a in range(0, 10)),
                "10~19세": sum(ages_dict[a] for a in range(10, 20)),
                "20~29세": sum(ages_dict[a] for a in range(20, 30)),
                "30~39세": sum(ages_dict[a] for a in range(30, 40)),
                "40~49세": sum(ages_dict[a] for a in range(40, 50)),
                "50~59세": sum(ages_dict[a] for a in range(50, 60)),
                "60~69세": sum(ages_dict[a] for a in range(60, 70)),
                "70세이상": sum(ages_dict[a] for a in range(70, 101)),
            }

        curr_gen = get_generations(curr_ages)
        fut_gen = get_generations(future_ages)

        if future_rate < 19:
            category = "19% 미만"
        elif future_rate < 23:
            category = "19% ~ 23%"
        elif future_rate < 28:
            category = "23% ~ 28%"
        elif future_rate < 38:
            category = "28% ~ 38%"
        else:
            category = "38% 이상"

        item = {
            "시군구코드": code,
            "시도": info["시도"],
            "시군구": info["시군구"],
            "현재총인구": curr_total,
            "미래총인구": future_total,
            "현재고령화율": round(curr_rate, 2),
            "미래고령화율": round(future_rate, 2),
            "고령화구간": category,
        }

        for k in curr_gen:
            item[f"현재_{k}"] = curr_gen[k]
            item[f"미래_{k}"] = fut_gen[k]

        processed_list.append(item)

    return processed_list


grouped_pop = simulate_future(base_sigungu_raw, steps)


# ==========================================
# 5. 상단 배너 헤더
# ==========================================
st.markdown(
    f"""
    <div class="header-container">
        <div class="header-title">🗺️ 대한민국 시군구별 {forecast_years_choice}년 후 ({target_year}년) 미래 인구 & 고령화 예측 대시보드</div>
        <div class="header-subtitle">사이드바에서 예측 시점을 변경하여 장기적인 지역별 세대 변화와 고령화 단계를 탐색해보세요.</div>
    </div>
""",
    unsafe_allow_html=True,
)


# ==========================================
# 6. Plotly 지도 시각화
# ==========================================
st.markdown(
    f"### 📍 [{target_year}년 예측 ({forecast_years_choice}년 후)] 시군구별 고령화율 단계구분도 & 세대별 인구 분포"
)
st.markdown(
    "지도에 마우스를 올리면 해당 지역의 **현재 vs 선택한 미래 시점의 세대별 인구 상세 비교 정보**가 표시됩니다."
)

category_orders = {
    "고령화구간": [
        "19% 미만",
        "19% ~ 23%",
        "23% ~ 28%",
        "28% ~ 38%",
        "38% 이상",
    ]
}

map_data = {
    "시군구코드": [x["시군구코드"] for x in grouped_pop],
    "시도": [x["시도"] for x in grouped_pop],
    "시군구": [x["시군구"] for x in grouped_pop],
    "현재총인구": [f"{x['현재총인구']:,}명" for x in grouped_pop],
    "미래총인구": [f"{x['미래총인구']:,}명" for x in grouped_pop],
    "현재고령화율": [f"{x['현재고령화율']}%" for x in grouped_pop],
    "미래고령화율": [f"{x['미래고령화율']}%" for x in grouped_pop],
    "고령화구간": [x["고령화구간"] for x in grouped_pop],
}

gen_keys = [
    "0~9세",
    "10~19세",
    "20~29세",
    "30~39세",
    "40~49세",
    "50~59세",
    "60~69세",
    "70세이상",
]
for g in gen_keys:
    map_data[f"현재_{g}"] = [f"{x[f'현재_{g}']:,}명" for x in grouped_pop]
    map_data[f"미래_{g}"] = [f"{x[f'미래_{g}']:,}명" for x in grouped_pop]

hover_dict = {
    "시도": True,
    "현재총인구": True,
    "미래총인구": True,
    "현재고령화율": True,
    "미래고령화율": True,
    "시군구코드": False,
    "고령화구간": False,
}
for g in gen_keys:
    hover_dict[f"현재_{g}"] = True
    hover_dict[f"미래_{g}"] = True

color_discrete_map = {
    "19% 미만": "#fee8c8",
    "19% ~ 23%": "#fdbb84",
    "23% ~ 28%": "#fc8d59",
    "28% ~ 38%": "#e34a33",
    "38% 이상": "#b30000",
}

fig = px.choropleth(
    map_data,
    geojson=sigungu_geojson,
    locations="시군구코드",
    featureidkey="properties.코드",
    color="고령화구간",
    color_discrete_map=color_discrete_map,
    category_orders=category_orders,
    hover_name="시군구",
    hover_data=hover_dict,
)

fig.update_geos(fitbounds="locations", visible=False)
fig.update_layout(
    margin={"r": 0, "t": 10, "l": 0, "b": 0},
    legend_title=f"{target_year}년 고령화 심각도",
    height=650,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
)

st.plotly_chart(fig, use_container_width=True)


# ==========================================
# 7. 상하위 10개 지역 표 출력
# ==========================================
st.markdown("---")
st.markdown(
    f"### 🏆 {target_year}년 예측 ({forecast_years_choice}년 후) 고령화율 주요 지역 순위 및 세대별 인구 분포"
)

sorted_pop = sorted(
    grouped_pop, key=lambda x: x["미래고령화율"], reverse=True
)
top_10_data = sorted_pop[:10]
bottom_10_data = sorted(
    sorted_pop[-10:], key=lambda x: x["미래고령화율"], reverse=False
)


def format_table_data(data_list):
    formatted = []
    for item in data_list:
        formatted.append(
            {
                "시도": item["시도"],
                "시군구": item["시군구"],
                f"{target_year} 예측 인구": item["미래총인구"],
                "0~9세": item["미래_0~9세"],
                "10~19세": item["미래_10~19세"],
                "20~39세": item["미래_20~29세"] + item["미래_30~39세"],
                "40~59세": item["미래_40~49세"] + item["미래_50~59세"],
                "60세 이상": item["미래_60~69세"] + item["미래_70세이상"],
                f"{target_year} 예측 고령화율": f"{item['미래고령화율']}%",
            }
        )
    return formatted


col1, col2 = st.columns(2)

with col1:
    st.markdown(
        f"#### 🚨 {forecast_years_choice}년 후 고령화율이 가장 높은 지역 (상위 10개)"
    )
    st.dataframe(format_table_data(top_10_data), use_container_width=True)

with col2:
    st.markdown(
        f"#### 🛡️ {forecast_years_choice}년 후 고령화율이 가장 낮은 지역 (하위 10개)"
    )
    st.dataframe(
        format_table_data(bottom_10_data), use_container_width=True
    )
