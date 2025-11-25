import os
import json
from pypdf import PdfReader
from typing import List, Dict
import pandas as pd

from my_openai import question  # 사용자가 만든 함수: question(system_content, prompt)


FOLDER_PATH = "agenda"
OUTPUT_EXCEL = "agenda_summary.xlsx"


def extract_text_from_pdf(pdf_path: str) -> str:
    """PDF 전체 텍스트 추출."""
    reader = PdfReader(pdf_path)
    text_parts = []
    for i, page in enumerate(reader.pages):
        page_text = page.extract_text() or ""
        text_parts.append(page_text)

    return "\n".join(text_parts)


def call_openai_for_agenda(text: str, filename: str) -> List[Dict]:
    """
    회의 안건 텍스트(text)를 OpenAI에 보내서
    [ {date, type, title, summary}, ... ] 형태의 리스트를 받는다.
    """
    system_content = [
        "당신은 정부·공공기관 회의 안건 문서를 구조화하는 보조자입니다.",
        "항상 JSON 배열만 출력해야 합니다.",
        "JSON 배열의 각 요소는 하나의 안건이며, 키는 date, location, directors, type, number, title, result 일곱 개만 사용합니다.",
        "마크다운 코드 블록(``` 등)이나 기타 설명 문장은 절대 출력하지 마세요.",
    ]

    # type: 보고안건 / 의결안건 강제
    prompt = f"""
다음 텍스트는 회의 안건 PDF에서 추출한 전체 내용입니다.
파일명: {filename}

---BEGIN---
{text}
---END---

이 텍스트에서 '안건'별로 다음 정보를 추출하여 JSON 배열로 만드세요.

필드 규칙:
- "date": 해당 안건이 속한 날짜를 "YYYY-MM-DD" 형식으로 적습니다.
          명확하지 않으면 문서에 나타난 날짜 형식(예: "2025. 11. 24.")을 그대로 사용해도 됩니다.
          전혀 추론이 안 되면 null을 넣습니다.
- "location": 회의 장소
- "directors" : 회의 참석이사들을 열거해서 적습니다. 대참한 경우에는 대참자 이름을 적습니다.
- "type": 안건 구분으로, 반드시 "보고안건" 또는 "의결안건" 둘 중 하나로만 작성합니다.
- "number" : 안건의 번호로 몇호 안건인지 적습니다.
- "title": 안건 제목을 간략하게 적습니다.
- "result": 안건의 결과를 1~2문장 개조식으로 요약해서 적습니다. "원안접수", "원안의결", "수정의결" 등
            안건 처리 결과가 반드시 포함되어야 합니다.

출력 형식 예시 (형식만 참고, 실제 내용은 텍스트 기준으로 작성):

[
  {{
    "date": "2025-11-24",
    "location" : "세종국책연구단지 연구지원동 1층 대회의실1"
    "directors" : "김영식, 이은영, 김재현, 민병주..."
    "type": "보고안건",
    "number": "1호",
    "title": "2024년도 소관연구기관 감사결과 보고",
    "result": "감사위원회가 직접 감사 총 9회 실시, 기타 복무감사 21개 기관 52회 실시 등 (별도의견 없이 원안접수)"
  }}
]

위와 같은 JSON 배열 하나만 출력하고, 그 밖의 텍스트는 절대로 포함하지 마세요.
"""

    raw_answer = question(system_content, prompt)

    # 응답에서 JSON 배열만 뽑아서 파싱 (혹시 모를 잡텍스트 방지용)
    agendas = None
    try:
        agendas = json.loads(raw_answer)
    except json.JSONDecodeError:
        # 혹시 모델이 앞뒤에 뭔가를 붙였을 경우를 대비해 [ ... ]만 잘라보기
        start = raw_answer.find("[")
        end = raw_answer.rfind("]")
        if start != -1 and end != -1 and end > start:
            json_str = raw_answer[start : end + 1]
            agendas = json.loads(json_str)
        else:
            raise ValueError(f"OpenAI 응답을 JSON으로 파싱할 수 없습니다.\n응답 일부: {raw_answer[:500]}")

    if not isinstance(agendas, list):
        raise ValueError("OpenAI 응답 JSON의 최상위 구조가 리스트가 아닙니다.")

    return agendas


def main():
    all_rows: List[Dict] = []

    for filename in os.listdir(FOLDER_PATH):
        if not filename.lower().endswith(".pdf"):
            continue

        pdf_path = os.path.join(FOLDER_PATH, filename)
        print(f"처리 중: {pdf_path}")

        # 1) PDF 텍스트 추출
        text = extract_text_from_pdf(pdf_path)
        
        if not text.strip():
            print(f"  -> 텍스트가 추출되지 않음, 건너뜀: {filename}")
            continue

        # 2) OpenAI로 안건 구조화
        try:
            agendas = call_openai_for_agenda(text, filename)
        except Exception as e:
            print(f"  -> OpenAI 호출/파싱 실패, 건너뜀: {filename}")
            print(f"     에러: {e}")
            continue

        # 3) 각 안건에 source(파일명) 붙여서 누적
        for item in agendas:
            row = {
                "source": filename,
                "date": item.get("date"),
                "location": item.get("location"),
                "directors": item.get("directors"),
                "type": item.get("type"),
                "number": item.get("number"),
                "title": item.get("title"),
                "result": item.get("result"),
            }
            all_rows.append(row)
        
    if not all_rows:
        print("추출된 안건이 없습니다.")
        return

    # 4) DataFrame → 엑셀
    df = pd.DataFrame(all_rows, columns=["source", "date", "location", "directors", "type", "number", "title", "result"])
    df.to_excel(OUTPUT_EXCEL, index=False)
    print(f"총 {len(all_rows)}개 안건을 '{OUTPUT_EXCEL}' 파일로 저장했습니다.")


if __name__ == "__main__":
    main()
