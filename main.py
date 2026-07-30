import csv
import gzip
import io
import json
import urllib.request
import plotly.express as px
import streamlit as st

# ==========================================
# 1. 페이지 설정
# ==========================================
st.set_page_config(
    page_title="대한민국 시군구별 미래 연령대별 인구 예측 지도",
    page_icon="📉",
    layout="wide",
)

st.title("📉 대한민국 시군구별 10년 후 연령대별 인구 & 고령화 예측 지도")
st.markdown(
    "현재 연령별 인구 구조를 바탕으로 10년 뒤 각 연령대별(0~10세, 11~20세 등) 인구 감소와 고령화 심화를 예측합니다. (Pandas/Numpy 미사용)"
)


# ==========================================
# 2. 데이터 불러오기 및 10년 후 예측 전처리
# ==========================================
@st.cache_data
def load_and_forecast_data():
    pop_url = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
    geojson_url = (
        "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"
    )

    # 1. GeoJSON 지도 데이터 다운로드
    with urllib.request.urlopen(geojson_url) as response:
        geojson_data = json.loads(response.read().decode("utf-8"))

    # 2. 인구 데이터 다운로드 및 압축 해제
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
    target_year = latest_year + 10

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

    processed_list = []

    for code, info in sigungu_raw.items():
        curr_ages = info["ages"]

        curr_total = sum(curr_ages.values())
        curr_elderly = sum(curr_ages[a] for a in range(65, 101))
        curr_rate = (curr_elderly / curr_total * 100) if curr_total > 0 else 0

        # 10년 후 연령별 인구구조 예측 (생존율 98% 반영, 저출생으로 인한 유아 인구 감소 반영)
        future_ages = {i: 0 for i in range(101)}

        # 10살 이상 이동 인구
        for age in range(91):
            f_age = age + 10
            survived_pop = int(curr_ages[age] * 0.98)
            if f_age <= 100:
                future_ages[f_age] += survived_pop
            else:
                future_ages[100] += survived_pop

        old_survived = sum(int(curr_ages[a] * 0.85) for a in range(91, 101))
        future_ages[100] += old_survived

        # 신생아/유아(0~10세 미만): 저출생 추세 심화 반영 (현재 유아 인구의 70% 수준으로 감소 가정)
        recent_child_avg = sum(curr_ages[a] for a in range(10)) / 10
        for age in range(10):
            future_ages[age] = int(recent_child_avg * 0.70)

        future_total = sum(future_ages.values())
        future_elderly = sum(future_ages[a] for a in range(65, 101))
        future_rate = (
            (future_elderly / future_total * 100) if future_total > 0 else 0
        )

        # 연령대별 그룹 합산 함수
        def get_group_sum(ages_dict, start, end):
            return sum(ages_dict[a] for a in range(start, end + 1))

        # 현재 연령대별 인구
        curr_g1 = get_group_sum(curr_ages, 0, 10)
        curr_g2 = get_group_sum(curr_ages, 11, 20)
        curr_g3 = get_group_sum(curr_ages, 21, 64)
        curr_g4 = get_group_sum(curr_ages, 65, 100)

        # 10년 후 연령대별 인구
        fut_g1 = get_group_sum(future_ages, 0, 10)
        fut_g2 = get_group_sum(future_ages, 11, 20)
        fut_g3 = get_group_sum(future_ages, 21, 64)
        fut_g4 = get_group_sum(future_ages, 65, 100)

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

        processed_list.append(
            {
                "시군구코드": code,
                "시도": info["시도"],
                "시군구": info["시군구"],
                "현재총인구": curr_total,
                "미래총인구": future_total,
                "현재고령화율": round(curr_rate, 2),
                "미래고령화율": round(future_rate, 2),
                "고령화구간": category,
                # 연령대별 현재
                "현_0~10세": curr_g1,
                "현_11~20세": curr_g2,
                "현_21~64세": curr_g3,
                "현_65세이상": curr_g4,
                # 연령대별 미래
                "미_0~10세": fut_g1,
                "미_11~20세": fut_g2,
                "미_21~64세": fut_g3,
                "미_65세이상": fut_g4,
            }
        )

    return latest_year, target_year, processed_list, geojson_data


with st.spinner(
    "데이터를 분석하고 10년 후 연령대별 인구 변화를 계산하는 중입니다..."
):
    (
        latest_year,
        target_year,
        grouped_pop,
        sigungu_geojson,
    ) = load_and_forecast_data()


# ==========================================
# 3. Plotly 지도 시각화
# ==========================================
st.subheader(
    f"📌 [{target_year}년 예측] 시군구별 고령화율 지도 및 연령대별 인구 분석"
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
    # 연령대별 상세 (마우스 툴팁용)
    "현_0~10세": [f"{x['현_0~10세']:,}명" for x in grouped_pop],
    "미_0~10세": [f"{x['미_0~10세']:,}명" for x in grouped_pop],
    "현_11~20세": [f"{x['현_11~20세']:,}명" for x in grouped_pop],
    "미_11~20세": [f"{x['미_11~20세']:,}명" for x in grouped_pop],
    "현_65세이상": [f"{x['현_65세이상']:,}명" for x in grouped_pop],
    "미_65세이상": [f"{x['미_65세이상']:,}명" for x in grouped_pop],
}

fig = px.choropleth(
    map_data,
    geojson=sigungu_geojson,
    locations="시군구코드",
    featureidkey="properties.코드",
    color="고령화구간",
    color_discrete_map={
        "19% 미만": "#deebf7",
        "19% ~ 23%": "#9ecae1",
        "23% ~ 28%": "#4292c6",
        "28% ~ 38%": "#2171b5",
        "38% 이상": "#08306b",
    },
    category_orders=category_orders,
    hover_name="시군구",
    hover_data={
        "시도": True,
        "현재총인구": True,
        "미래총인구": True,
        "현재고령화율": True,
        "미래고령화율": True,
        "현_0~10세": True,
        "미_0~10세": True,
        "현_11~20세": True,
        "미_11~20세": True,
        "현_65세이상": True,
        "미_65세이상": True,
        "시군구코드": False,
        "고령화구간": False,
    },
)

fig.update_geos(fitbounds="locations", visible=False)
fig.update_layout(
    margin={"r": 0, "t": 0, "l": 0, "b": 0},
    legend_title=f"{target_year}년 고령화구간",
    height=650,
)

st.plotly_chart(fig, use_container_width=True)


# ==========================================
# 4. 상하위 10개 지역 표 출력
# ==========================================
st.markdown("---")
st.subheader(f"📊 {target_year}년 예측 고령화율 주요 지역 순위")

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
                "현재 총인구": f"{item['현재총인구']:,}명",
                f"{target_year} 예측 인구": f"{item['미래총인구']:,}명",
                f"10년후 0~10세": f"{item['미_0~10세']:,}명",
                f"10년후 11~20세": f"{item['미_11~20세']:,}명",
                f"10년후 65세이상": f"{item['미_65세이상']:,}명",
                f"{target_year} 예측 고령화율": f"{item['미래고령화율']}%",
            }
        )
    return formatted


col1, col2 = st.columns(2)

with col1:
    st.markdown(f"#### 🔴 10년 후 고령화율 높은 곳 TOP 10")
    st.dataframe(format_table_data(top_10_data), use_container_width=True)

with col2:
    st.markdown(f"#### 🔵 10년 후 고령화율 낮은 곳 TOP 10")
    st.dataframe(
        format_table_data(bottom_10_data), use_container_width=True
    )
