import pandas as pd
import time
from typing import List, Optional
import my_openai  # 네가 이미 사용 중인 래퍼 모듈


# 1. 카테고리 정의 (번호 + 라벨)
TOPIC_MAP = {
    "1": "1. 동물대체시험기술 개발",
    "2": "2. 생활환경화학물질 독성연구",
    "3": "3. 신약 등에 대한 동물실험 관련",
    "4": "4. 환경 및 생태독성 관련 연구",
    "5": "5. 분석기술 관련 연구",
    "6": "6. 기타",
}


def build_system_content() -> List[str]:
    """
    OpenAI 분류용 system 메시지.
    반드시 1~6 중 하나의 번호만 선택해서 답하게 강제.
    """
    return [
        "당신은 독성학 및 독성관련 연구 논문을 분류하는 전문가입니다.",
        "사용자가 제공하는 논문 정보를 보고 아래 6개 연구주제 중 가장 적합한 하나를 선택하세요.",
        "연구주제는 다음과 같습니다.",
        "1. 동물대체시험기술 개발: in vitro, in silico, 오가노이드, 오가노온어칩, 3D 세포배양, 동물대체시험, NAMs 등 동물 대신/축소를 목표로 한 시험법·모델·플랫폼 개발 연구",
        "2. 생활환경화학물질 독성연구: 생활용품, 식품·포장재, 미세플라스틱, 중금속, 산업화학물질 등 사람이 일상생활에서 노출되는 화학물질의 인체독성·건강영향을 다루는 연구",
        "3. 신약 등에 대한 동물실험 관련: 신약·제제·바이오의약품·백신·치료제 등에 대한 효능·안전성·약동/약력학 평가를 위해 동물모델을 사용하는 전임상·독성시험 연구",
        "4. 환경 및 생태독성 관련 연구: 수생생물, 토양생물, 야생생물, 생태계 수준의 독성, 환경노출, 생태영향(예: 물벼룩·어류·토양무척추동물 독성, 생태위해성 평가 등)을 다루는 연구",
        "5. 분석기술 관련 연구: 화학물질, 대사체, 바이오마커 등을 정량/정성 분석하기 위한 분석법·기기·센서·전처리기술 개발 및 성능평가 연구(LC-MS/MS, GC-MS, 센서, 이미징 등)",
        "6. 기타: 위 1~5 어느 쪽에도 뚜렷이 속하지 않는 경우",
        "항상 다음 지침을 지키세요:",
        "- 가장 적합한 하나의 번호만 선택합니다. 복수 선택 금지.",
        "- 애매하면 가장 근접한 번호 하나를 고르고, 정말 애매하면 6번 기타를 선택합니다.",
        "- 최종 답변은 반드시 숫자 1~6 중 하나만 출력합니다. 그 외 설명/문장은 절대 쓰지 마세요.",
    ]


def build_prompt(title: str, abstract: str, project_title: str) -> str:
    """
    한 논문에 대해 OpenAI에 던질 프롬프트 구성.
    제목, 초록, 과제명(국문)을 함께 넣어 맥락 확보.
    """
    parts = []
    if title:
        parts.append(f"[논문 제목]\n{title}")
    if abstract:
        parts.append(f"[초록]\n{abstract}")
    if project_title:
        parts.append(f"[관련 과제명(국문)]\n{project_title}")

    content = "\n\n".join(parts)

    prompt = (
        "아래 논문의 내용을 바탕으로, 미리 정의된 6개 연구주제 중 가장 잘 맞는 하나를 선택하세요.\n"
        "출력 형식은 숫자 하나(1,2,3,4,5,6)만 사용하세요.\n\n"
        f"{content}\n\n"
        "이 논문에 가장 적합한 연구주제 번호는 무엇입니까? 숫자만 답변하세요."
    )
    return prompt


def classify_topic_for_row(title: str, abstract: str, project_title: str) -> Optional[str]:
    """
    한 논문(row)에 대해 OpenAI API를 호출하여 1~6 중 하나의 번호를 받은 뒤,
    TOPIC_MAP에서 라벨 문자열로 변환해 반환.
    """
    system_content = build_system_content()
    prompt = build_prompt(title, abstract, project_title)

    try:
        raw_answer = my_openai.question(system_content, prompt)
    except Exception as e:
        print(f"[ERROR] OpenAI 호출 실패: {e}")
        return None

    if not isinstance(raw_answer, str):
        return None

    answer = raw_answer.strip()

    # 숫자만 남기도록 정리 (혹시 "1." 처럼 찍어도 방어)
    answer = answer.replace(".", "").strip()

    if answer in TOPIC_MAP:
        return TOPIC_MAP[answer]

    # 예측 불가능한 응답일 때 보호차원에서 기타로 처리
    return TOPIC_MAP["6"]


def tag_papers_by_topic(
    input_path: str,
    output_path: str,
    title_col: str = "논문명",
    abstract_col: str = "초록",
    project_title_col: str = "과제명(국문)",
    tag_col: str = "연구주제태그",
    sleep_sec: float = 0.5,
):
    """
    1) 엑셀 로드
    2) 각 논문(행)별로 OpenAI 분류
    3) tag_col 컬럼에 태그(예: '1. 동물대체시험기술 개발') 기록
    4) 결과를 새로운 엑셀로 저장
    """
    df = pd.read_excel(input_path)

    # 기존 태그 컬럼이 있으면 덮어쓰기
    df[tag_col] = ""

    for idx, row in df.iterrows():
        title = str(row.get(title_col, "") or "").strip()
        abstract = str(row.get(abstract_col, "") or "").strip()
        project_title = str(row.get(project_title_col, "") or "").strip()

        print(f"[{idx+1}/{len(df)}] 분류 중: {title[:60]}...")

        tag = classify_topic_for_row(title, abstract, project_title)

        if tag is None:
            tag = TOPIC_MAP["6"]  # 실패 시 기타

        df.at[idx, tag_col] = tag

        # 호출 간 간격 (rate limit 대비)
        time.sleep(sleep_sec)

    df.to_excel(output_path, index=False)
    print(f"[DONE] 저장 완료 → {output_path}")


if __name__ == "__main__":
    # 실제 실행 예시
    input_file = "2.NTIS_PAPER_with_abstract(DOI_only).xlsx"
    output_file = "2.NTIS_PAPER_with_topic_tags.xlsx"

    tag_papers_by_topic(
        input_path=input_file,
        output_path=output_file,
        title_col="논문명",
        abstract_col="초록",
        project_title_col="과제명(국문)",
        tag_col="연구주제태그",
        sleep_sec=0.6,
    )
