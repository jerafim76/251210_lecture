import pandas as pd

# 1. 태그까지 들어 있는 최종 파일 로드
input_file = "2.NTIS_PAPER_with_topic_tags.xlsx"   # ← 네가 만든 결과 파일 이름
output_file = "NTIS_year_topic_summary.xlsx"       # ← 새로 만들 요약 엑셀

df = pd.read_excel(input_file)

# 혹시라도 공백/NaN 방지
df["기준년도"] = df["기준년도"].astype(int)
df["연구주제태그"] = df["연구주제태그"].fillna("미분류")

# 2. 연도별 × 연구주제별 건수 피벗테이블 생성
#   index: 기준년도
#   columns: 연구주제태그
#   values: 아무 컬럼이나 count (여기선 NO 사용)
pivot = pd.pivot_table(
    df,
    index="기준년도",
    columns="연구주제태그",
    values="NO",
    aggfunc="count",
    fill_value=0,
    margins=True,        # 합계 행/열 추가 (All)
    margins_name="합계",
)

# 인덱스를 컬럼으로 빼서 보기 좋게
pivot = pivot.reset_index()

# 3. (선택) 전체 건수 요약 테이블도 같이 만들고 싶다면
summary_by_topic = (
    df.groupby("연구주제태그")["NO"]
    .count()
    .reset_index()
    .rename(columns={"NO": "건수"})
    .sort_values("건수", ascending=False)
)

summary_by_year = (
    df.groupby("기준년도")["NO"]
    .count()
    .reset_index()
    .rename(columns={"NO": "건수"})
    .sort_values("기준년도")
)

# 4. 여러 시트로 엑셀 저장
with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
    pivot.to_excel(writer, sheet_name="연도별_주제별_건수", index=False)
    summary_by_topic.to_excel(writer, sheet_name="주제별_총건수", index=False)
    summary_by_year.to_excel(writer, sheet_name="연도별_총건수", index=False)

print(f"완료: {output_file} 생성")
