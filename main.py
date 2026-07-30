import pandas as pd
import numpy as np
import plotly.express as px
import requests
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
st.markdown("최신 인구 데이터를 바탕으로 시군구별 65세 이상 인구 비율을 시각화한 앱입니다.")


# ==========================================
# 2. 데이터 불러오기 및 전처리 (캐싱 적용)
# ==========================================
@st.cache_data
ools
def load_data():
    # 인구 데이터 URL
    pop_url = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
    # 시군구 GeoJSON 지도 URL
    geojson_url = (
        "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"
    )

    # 1. 인구 데이터 읽기 (코드는 반드시 문자열로 읽기)
    df_pop = pd.read_csv(pop_url, dtype={"코드": str})

    # 2. 지도 GeoJSON 데이터 읽기
    response = requests.get(geojson_url)
    geojson_data = response.json()

    return df_pop, geojson_data


# 데이터 로딩 표시
with st.spinner("데이터를 불러오는 중입니다. 잠시만 기다려주세요..."):
    df_pop, sigungu_geojson = load_data()


# ==========================================
# 3. 고령화율 계산 및 데이터 가공
# ==========================================
# 가장 최신 연도 찾기
latest_year = df_pop["연도"].max()

# 최신 연도 데이터만 추출
df_latest = df_pop[df_pop[" 연도"] == latest_year].copy()  # CSV 열 이름에 공백 포함 가능성 대비

# 열 이름 정리 (공백 제거)
df_latest.columns = df_latest.columns.str.strip()

# 시군구 5자리 코드 추출 (읍면동 코드 앞 5자리)
df_latest["시군구코드"] = df_latest["코드"].str.slice(0, 5)


# 65세 이상 인구 계산 함수
def get_elderly_population(row):
    elderly_sum = 0
    # 65세부터 100세 이상까지의 '계_XX세' 열 찾아서 합산
    for col in row.index:
        if col.startswith("계_"):
            age_str = col.replace("계_", "").replace("세", "").replace(" 이상", "")
            if age_str.isdigit() and int(age_str) >= 65:
                elderly_sum += row[col]
    return elderly_sum


# 전체 인구('계_계' 또는 모든 나이 '계_' 합산) 계산
# 보통 '계_계'가 총인구이거나, 모든 나이 '계_'의 합일 수 있음. 여기서는 총인구 컬럼이 없으므로 '계_'로 시작하는 모든 연령 컬럼 합산
age_cols = [
    c for c in df_latest.columns if c.startswith("계_") and c != "계_계"
]


# 행별로 65세 이상 인구와 전체 인구 계산
def calculate_ratios(df):
    total_pop_list = []
    elderly_pop_list = []

    for idx, row in df.iterrows():
        total = 0
        elderly = 0
        for col in age_cols:
            val = row[col]
            if pd.notna(val):
                total += val
                # 나이 추출
                age_str = (
                    col.replace("계_", "")
                    .replace("세", "")
                    .replace(" 이상", "")
                )
                if age_str.isdigit() and int(age_str) >= 65:
                    elderly += val
        total_pop_list.append(total)
        elderly_pop_list.append(elderly)

    df["전체인구"] = total_pop_list
    df["65세이상인구"] = elderly_pop_list
    return df


# 연산 수행 (시간 단축을 위해 벡터화 또는 그룹화 전 처리)
# 읍면동 단위 데이터를 시군구(앞 5자리)별로 합산
grouped_pop = (
    df_latest.groupby("시군구코드")
    .agg(
        {
            "시도": "first",
            "시군구": "first",
            **{col: "sum" for col in age_cols},
        }
    )
    .reset_index()
)

# 시군구별 전체 인구 및 65세 이상 인구 다시 계산
total_pop_sigungu = []
elderly_pop_sigungu = []

for idx, row in grouped_pop.iterrows():
    total = 0
    elderly = 0
    for col in age_cols:
        val = row[col]
        if pd.notna(val):
            total += val
            age_str = (
                col.replace("계_", "").replace("세", "").replace(" 이상", "")
            )
            if age_str.isdigit() and int(age_str) >= 65:
                elderly += val
    total_pop_sigungu.append(total)
    elderly_pop_sigungu.append(elderly)

grouped_pop["전체인구"] = total_pop_sigungu
grouped_pop["65세이상인구"] = elderly_pop_sigungu

# 고령화율(%) 계산
grouped_pop["고령화율"] = (
    grouped_pop["65세이상인구"] / grouped_pop["전체인구"]
) * 100

# ==========================================
# 4. 5단계 구간 나누기 및 색상 매핑
# ==========================================
# 요청된 구간 경계값: 19%, 23%, 28%, 38%
# 5단계 범주 생성
bins = [-np.inf, 19, 23, 28, 38, np.inf]
labels = ["19% 미만", "19% ~ 23%", "23% ~ 28%", "28% ~ 38%", "38% 이상"]

grouped_pop["고령화구간"] = pd.cut(
    grouped_pop["고령화율"], bins=bins, labels=labels
)


# ==========================================
# 5. Plotly 지도 시각화
# ==========================================
st.subheader(f"📌 {latest_year}년 기준 시군구별 고령화율 지도")

# 색상 팔레트 (낮은 쪽 옅게, 높은 쪽 진하게 - Blues 또는 Oranges 계열)
color_sequence = ["#deebf7", "#9ecae1", "#4292c6", "#2171b5", "#08306b"]

fig = px.choropleth(
    grouped_pop,
    geojson=sigungu_geojson,
    locations="시군구코드",  # 지도와 맞출 5자리 코드
    featureidkey="properties.코드",  # GeoJSON의 5자리 코드 속성 경로
    color="고령화구간",
    color_discrete_map={
        "19% 미만": "#deebf7",
        "19% ~ 23%": "#9ecae1",
        "23% ~ 28%": "#4292c6",
        "28% ~ 38%": "#2171b5",
        "38% 이상": "#08306b",
    },
    category_orders={"고령화구간": labels},
    hover_name="시군구",
    hover_data={
        "시도": True,
        "고령화율": ":.2f",
        "시군구코드": False,
        "고령화구간": False,
    },
)

# 지도 레이아웃 설정 (배경 타일 제거 및 대한민국 중심 맞추기)
fig.update_geos(fitbounds="locations", visible=False)
fig.update_layout(
    margin={"r": 0, "t": 0, "l": 0, "b": 0},
    legend_title="고령화율 구간",
    height=600,
)

st.plotly_chart(fig, use_container_width=True)


# ==========================================
# 6. 상하위 10개 지역 표 출력
# ==========================================
st.markdown("---")
st.subheader("📊 고령화율 주요 지역 순위")

# 고령화율 기준으로 정렬
df_sorted = grouped_pop.sort_values(by="고령화율", ascending=False).reset_index(
    drop=True
)

col1, col2 = st.columns(2)

with col1:
    st.markdown("#### 🔴 고령화율 높은 곳 TOP 10")
    top_10 = df_sorted.head(10)[
        ["시도", "시군구", "전체인구", "65세이상인구", "고령화율"]
    ].copy()
    top_10["고령화율"] = top_10["고령화율"].round(2).astype(str) + "%"
    top_10.columns = ["시도", "시군구", "전체 인구", "65세 이상 인구", "고령화율"]
    st.dataframe(top_10, use_container_width=True, hide_index=True)

with col2:
    st.markdown("#### 🔵 고령화율 낮은 곳 TOP 10")
    # 낮은 곳은 오름차순 정렬 후 상위 10개
    bottom_10 = df_sorted.tail(10).sort_values(by="고령화율", ascending=True)[
        ["시도", "시군구", "전체인구", "65세이상인구", "고령화율"]
    ].copy()
    bottom_10["고령화율"] = bottom_10["고령화율"].round(2).astype(str) + "%"
    bottom_10.columns = ["시도", "시군구", "전체 인구", "65세 이상 인구", "고령화율"]
    st.dataframe(bottom_10, use_container_width=True, hide_index=True)
