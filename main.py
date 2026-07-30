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
    page_title="전국 고령화 지도",
    page_icon="🗺️",
    layout="wide",
)

st.title("🗺️ 대한민국 시군구별 고령화 지도")
st.markdown(
    "최신 인구 데이터를 바탕으로 시군구별 65세 이상 인구 비율을 시각화한 앱입니다. (Pandas/Numpy 미사용)"
)


# ==========================================
# 2. 데이터 불러오기 및 전처리 (캐싱 적용)
# ==========================================
@st.cache_data
def load_and_process_data():
    pop_url = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
    geojson_url = (
        "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"
    )

    # 1. GeoJSON 지도 데이터 다운로드 및 읽기
    with urllib.request.urlopen(geojson_url) as response:
        geojson_data = json.loads(response.read().decode("utf-8"))

    # 2. 인구 데이터(.csv.gz) 다운로드 및 압축 해제
    with urllib.request.urlopen(pop_url) as response:
        compressed_data = response.read()

    with gzip.GzipFile(fileobj=io.BytesIO(compressed_data)) as gz:
        file_content = gz.read().decode("utf-8")

    # CSV 파싱
    reader = csv.DictReader(io.StringIO(file_content))
    rows = list(reader)

    # 컬럼 이름 공백 제거 (안전 장치)
    if rows:
        cleaned_keys = {k: k.strip() for k in rows[0].keys()}
        rows = [{cleaned_keys.get(k, k): v for k, v in row.items()} for row in rows]

    # 가장 최신 연도 찾기
    years = [int(row["연도"]) for row in rows if row.get("연도")]
    latest_year = max(years)

    # 최신 연도 데이터만 필터링하고 시군구(코드 앞 5자리)별로 집계
    sigungu_data = {}  # { 시군구코드: { '시도': ..., '시군구': ..., '전체인구': ..., '65세이상인구': ... } }

    # 나이별 컬럼 찾기 ('계_'로 시작하고 '계_계'가 아닌 컬럼)
    sample_row = rows[0]
    age_columns = [
        col
        for col in sample_row.keys()
        if col and col.startswith("계_") and col != "계_계"
    ]

    for row in rows:
        # 연도 확인 (공백 포함 키 대응)
        year_val = row.get("연도") or row.get(" 연도")
        if not year_val or int(year_val) != latest_year:
            continue

        code = row.get("코드", "").strip()
        if len(code) < 5:
            continue

        sigungu_code = code[:5]
        sido = row.get("시도", "").strip()
        sigungu_name = row.get("시군구", "").strip()

        if sigungu_code not in sigungu_data:
            sigungu_data[sigungu_code] = {
                "시군구코드": sigungu_code,
                "시도": sido,
                "시군구": sigungu_name,
                "전체인구": 0,
                "65세이상인구": 0,
            }

        # 인구 합산
        for col in age_columns:
            val_str = row.get(col, "0").replace(",", "").strip()
            if not val_str:
                continue
            try:
                val = int(val_str)
            except ValueError:
                continue

            sigungu_data[sigungu_code]["전체인구"] += val

            # 65세 이상 판단
            # 예: '계_65세', '계_100세 이상'
            age_part = (
                col.replace("계_", "").replace("세", "").replace(" 이상", "")
            )
            if age_part.isdigit() and int(age_part) >= 65:
                sigungu_data[sigungu_code]["65세이상인구"] += val

    # 리스트 형태로 변환 및 고령화율 계산
    processed_list = []
    for code, info in sigungu_data.items():
        total = info["전체인구"]
        elderly = info["65세이상인구"]
        rate = (elderly / total * 100) if total > 0 else 0.0

        # 5단계 구간 나누기 (기준: 19%, 23%, 28%, 38%)
        if rate < 19:
            category = "19% 미만"
        elif rate < 23:
            category = "19% ~ 23%"
        elif rate < 28:
            category = "23% ~ 28%"
        elif rate < 38:
            category = "28% ~ 38%"
        else:
            category = "38% 이상"

        info["고령화율"] = round(rate, 2)
        info["고령화구간"] = category
        processed_list.append(info)

    return latest_year, processed_list, geojson_data


# 데이터 로딩 표시
with st.spinner("데이터를 불러오는 중입니다. 잠시만 기다려주세요..."):
    latest_year, grouped_pop, sigungu_geojson = load_and_process_data()


# ==========================================
# 3. Plotly 지도 시각화
# ==========================================
st.subheader(f"📌 {latest_year}년 기준 시군구별 고령화율 지도")

# 지도 그리기용 데이터 정렬 순서 정의
category_orders = {
    "고령화구간": [
        "19% 미만",
        "19% ~ 23%",
        "23% ~ 28%",
        "28% ~ 38%",
        "38% 이상",
    ]
}

# 딕셔너리 리스트를 Plotly가 읽기 쉽도록 키별 리스트로 변환
map_data = {
    "시군구코드": [x["시군구코드"] for x in grouped_pop],
    "시도": [x["시도"] for x in grouped_pop],
    "시군구": [x["시군구"] for x in grouped_pop],
    "고령화율": [x["고령화율"] for x in grouped_pop],
    "고령화구간": [x["고령화구간"] for x in grouped_pop],
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
        "고령화율": ":.2f",
        "시군구코드": False,
        "고령화구간": False,
    },
)

fig.update_geos(fitbounds="locations", visible=False)
fig.update_layout(
    margin={"r": 0, "t": 0, "l": 0, "b": 0},
    legend_title="고령화율 구간",
    height=600,
)

st.plotly_chart(fig, use_container_width=True)


# ==========================================
# 4. 상하위 10개 지역 표 출력
# ==========================================
st.markdown("---")
st.subheader("📊 고령화율 주요 지역 순위")

# 고령화율 기준으로 정렬 (내림차순)
sorted_pop = sorted(grouped_pop, key=lambda x: x["고령화율"], reverse=True)

top_10_data = sorted_pop[:10]
bottom_10_data = sorted(
    sorted_pop[-10:], key=lambda x: x["고령화율"], reverse=False
)


# 표 출력을 위한 데이터 정제 함수
def format_table_data(data_list):
    formatted = []
    for item in data_list:
        formatted.append(
            {
                "시도": item["시도"],
                "시군구": item["시군구"],
                "전체 인구": f"{item['전체인구']:,}명",
                "65세 이상 인구": f"{item['65세이상인구']:,}명",
                "고령화율": f"{item['고령화율']}%",
            }
        )
    return formatted


col1, col2 = st.columns(2)

with col1:
    st.markdown("#### 🔴 고령화율 높은 곳 TOP 10")
    st.dataframe(format_table_data(top_10_data), use_container_width=True)

with col2:
    st.markdown("#### 🔵 고령화율 낮은 곳 TOP 10")
    st.dataframe(
        format_table_data(bottom_10_data), use_container_width=True
    )
