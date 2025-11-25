import requests, my_openai, time, html, os
from bs4 import BeautifulSoup
from typing import Optional, List
from datetime import datetime
import pandas as pd

# 네이버 오픈 API 클라이언트 정보
client_id = os.environ.get("NAVER_API_CLIENT_ID")
client_secret = os.environ.get("NAVER_API_CLIENT_SECRET")

if not client_id or not client_secret:
    raise RuntimeError(
        "환경변수 OPENAI_API_KEY_KIT가 설정되지 않았습니다.\n"
        "OS 환경변수 설정 후 다시 실행하세요."
    )

def news_crawling_to_excel(query):

    # 검색어와 요청 파라미터

    url = 'https://openapi.naver.com/v1/search/news.json'
    params = {
        'query': query,
        'display': 100,
        'start': 1,
        'sort': 'sim'  # 또는 'date' (정확도순)
    }

    # 헤더에 인증 정보 추가
    headers = {
        'X-Naver-Client-Id': client_id,
        'X-Naver-Client-Secret': client_secret
    }

    # 본문 크롤링
    def get_article_body(article_url: str) -> Optional[str]:
        """
        네이버 뉴스 원문 페이지에서
        <article id="dic_area" class="go_trans _article_content"> 안의 텍스트만 추출.
        구조가 다르면 None 반환.
        """
        try:
            res = requests.get(
                article_url,
                headers={
                    # UA 없으면 일부 언론사에서 차단하는 경우가 있어서 추가
                    'User-Agent': (
                        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                        'AppleWebKit/537.36 (KHTML, like Gecko) '
                        'Chrome/129.0.0.0 Safari/537.36'
                    )
                },
                timeout=10,
            )
        except requests.RequestException as e:
            print(f'[ERROR] 기사 요청 실패: {article_url} / {e}')
            return None

        if res.status_code != 200:
            print(f'[ERROR] 기사 응답 코드: {article_url} / {res.status_code}')
            return None

        soup = BeautifulSoup(res.text, 'html.parser')

        # 네이버 뉴스 기사 본문 영역
        contents_div = soup.find('div', id='contents', class_='newsct_body')
        if not contents_div:
            # 구조가 다르면 스킵
            return None

        article_tag = contents_div.find('article', id='dic_area', class_='go_trans _article_content')
        if not article_tag:
            # 원하는 구조의 문서가 아니면 스킵
            return None

        # 줄바꿈 처리: <br> -> \n
        for br in article_tag.find_all('br'):
            br.replace_with('\n')

        # 사진 캡션, 스크립트 등 불필요 태그 제거 (필요시 더 추가)
        for tag in article_tag.find_all(['script', 'style']):
            tag.decompose()

        # 텍스트 추출
        text = article_tag.get_text(separator=' ', strip=True)

        # 개행 기준으로 한번 정리
        # (원문 예시처럼 문단 사이에 <br> 두 개씩 있을 때 어느 정도 복원)
        lines = [line.strip() for line in text.split('\n')]
        lines = [line for line in lines if line]  # 빈 줄 제거
        cleaned_text = '\n'.join(lines)

        return cleaned_text


    # API 요청
    response = requests.get(url, headers=headers, params=params)

    result = []

    # 결과 출력
    if response.status_code == 200:
        data = response.json()
        for item in data['items']:
            title = item['title']
            link = item['link']
            pubDate = item['pubDate']

            print('=' * 80)
            print(f'제목: {title}')
            print(f'링크: {link}')
            print(f'시간: {pubDate}')

            if 'naver' in link:

                body = get_article_body(link)

                if body:
                    print('\n[기사 본문]')
                    print(body[:1000])  # 너무 길면 일부만 출력 (테스트용)
                else:
                    body = "none"
                    print('\n[기사 본문] 해당 구조(div#contents > article#dic_area)를 찾지 못했음 (스킵)')
                print('=' * 80)
                
                result.append([title, link, pubDate, body])
            
            if len(result) > 10: break

    if len(result) > 0:
        df = pd.DataFrame(result, columns  = ["제목", "링크", "제공시간", "뉴스본문"])
        df.to_excel("news_data.xlsx")

    else:
        print(f"오류 발생: {response.status_code}")

def clean_title(raw_title: str) -> str:
    """
    HTML 태그(<b></b>) 제거 + HTML 엔티티(&quot;, &amp;) 디코딩
    """
    if not isinstance(raw_title, str):
        return ""

    # 태그 제거
    cleaned = BeautifulSoup(raw_title, "html.parser").get_text()

    # HTML 엔티티 복원
    cleaned = html.unescape(cleaned)

    return cleaned.strip()

def convert_date(raw_date: str) -> str:
    """
    'Fri, 07 Nov 2025 14:17:00 +0900' → '2025-11-07'
    """
    if not isinstance(raw_date, str):
        return ""

    try:
        dt = datetime.strptime(raw_date, "%a, %d %b %Y %H:%M:%S %z")
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return raw_date  # 변환 실패 시 원문 유지


def summarize_article(body_text: str, max_len: int = 150) -> str:
    """
    뉴스 본문을 OpenAI API로 요약.
    """
    if not isinstance(body_text, str) or not body_text.strip():
        return ""

    system_content: List[str] = [
        "당신은 한국어 뉴스를 요약하는 보조자입니다.",
        f"요약은 {max_len}자 이내로 핵심 내용만 정리하세요.",
        "숫자, 기관명, 날짜는 가능한 그대로 보존하세요."
    ]

    prompt = (
        "다음은 한국어 뉴스 기사 본문입니다. 핵심 내용을 요약해 주세요.\n\n"
        f"{body_text}"
    )

    try:
        return my_openai.question(system_content, prompt)
    except Exception as e:
        print(f"[ERROR] 요약 실패: {e}")
        return ""

def summarize_news_excel(
    input_path: str,
    output_path: str,
    text_column: str = "뉴스본문",
    summary_column: str = "요약",
    title_column: str = "제목",
    time_column: str = "제공시간",
    max_len: int = 150,
    sleep_sec: float = 0.5,
):
    """
    전체 파이프라인:
    - 제목 태그 제거
    - HTML 엔티티 디코딩
    - 제공시간 → YYYY-MM-DD
    - 본문 요약 생성
    - 엑셀로 저장
    """
    df = pd.read_excel(input_path)

    # 제목 정리
    if title_column in df.columns:
        df[title_column] = df[title_column].astype(str).apply(clean_title)

    # 제공시간 정리
    if time_column in df.columns:
        df[time_column] = df[time_column].astype(str).apply(convert_date)

    # 본문 요약
    summaries = []
    for i, body in enumerate(df[text_column]):
        print(f"[INFO] {i+1}/{len(df)} 기사 요약 중…")

        summary = summarize_article(str(body), max_len=max_len)
        summaries.append(summary)

        time.sleep(sleep_sec)

    df[summary_column] = summaries

    df.to_excel(output_path, index=False)
    print(f"[DONE] 처리된 엑셀 저장 완료 → {output_path}")

def test():
    system_content = [
        "user의 질문에 최대한 친절하게 대답하세요",
        "답변은 100자를 넘기지 마세요.",
        ]
    prompt = "훈민정음은 몇년도에 창제되었나요?"

    print(my_openai.question(system_content, prompt))

if __name__ == "__main__":
    
    # 뉴스 크롤링 실행 (news_data.xlsx 생성)
    news_crawling_to_excel("PBS 폐지")

    # 요약 실행
    summarize_news_excel(
        input_path="news_data.xlsx",
        output_path="news_data_final.xlsx",
        text_column="뉴스본문",
        summary_column="요약",
        title_column="제목",
        time_column="제공시간",
        max_len=150,
        sleep_sec=0.4,
    )
    