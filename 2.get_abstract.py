import pandas as pd
import time, os
import requests
from typing import Optional, Dict, Any
from urllib.parse import urlparse

API_KEY = os.environ.get("ELSEVIER_API_KEY")
INST_TOKEN = None                      # 기관 토큰 있으면 입력, 없으면 None

ABSTRACT_BASE_URL = "https://api.elsevier.com/content/abstract"

def normalize_doi(raw: str) -> str:
    """
    엑셀에서 읽은 DOI 문자열을
    - 순수 DOI만 남기도록 정규화.
    예) 'https://doi.org/10.1016/j.cej.2023.145834'
        → '10.1016/j.cej.2023.145834'
    """
    if not isinstance(raw, str):
        return ""

    doi = raw.strip()

    # URL 형식인 경우 처리
    if doi.lower().startswith("http"):
        parsed = urlparse(doi)
        # path 부분 (/10.1016/...) 에서 / 제거
        doi = parsed.path.lstrip("/")

    # 앞뒤 공백/따옴표 같은 거 제거
    return doi.strip()

def extract_abstract_from_response(data: Dict[str, Any]) -> str:
    resp = data.get("abstracts-retrieval-response", {})
    
    # 가장 일반적인 abstract 위치
    try:
        item = resp.get("item", {})
        bib = item.get("bibrecord", {})
        head = bib.get("head", {})
        abstracts = head.get("abstracts", [])

        if isinstance(abstracts, dict):
            abstracts = [abstracts]

        for ab in abstracts:
            txt = ab.get("abstract")
            if isinstance(txt, dict) and "$" in txt:
                return txt["$"]
            elif isinstance(txt, list):
                for t in txt:
                    if isinstance(t, dict) and "$" in t:
                        return t["$"]
    except:
        pass

    # fallback
    coredata = resp.get("coredata", {})
    if "dc:description" in coredata:
        return coredata["dc:description"]

    return ""

def get_abstract_by_doi(doi: str) -> Optional[str]:
    doi = normalize_doi(doi)

    if not doi or doi.lower() == "nan":
        return None

    url = f"{ABSTRACT_BASE_URL}/doi/{doi}"

    headers = {
        "X-ELS-APIKey": API_KEY,
        "Accept": "application/json",
    }
    if INST_TOKEN:
        headers["X-ELS-Insttoken"] = INST_TOKEN

    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        print(f"[ERROR] DOI={doi} / {r.status_code}")
        return None

    data = r.json()
    abstract = extract_abstract_from_response(data)
    return abstract or None


def enrich_excel_abstracts_doi_only(
    input_path: str,
    output_path: str,
    sleep_sec: float = 0.4,
):
    print("[INFO] Loading Excel...")
    raw = pd.read_excel(input_path)

    # 첫 행이 컬럼이므로 정리
    header = raw.iloc[0]
    df = raw.rename(columns=header).iloc[1:].reset_index(drop=True)

    # 결측 대비
    df["초록"] = df["초록"].astype(str).where(df["초록"].notna(), "")

    for idx, row in df.iterrows():
        raw_doi = str(row["DOI"]).strip()
        norm_doi = normalize_doi(raw_doi)
        title = str(row["논문명"])[:50]

        if not norm_doi or norm_doi.lower() == "nan":
            df.at[idx, "초록"] = ""
            print(f"[{idx+1}] DOI 없음 → 초록 결측 처리 ({raw_doi})")
            continue

        print(f"[{idx+1}] DOI 찾는 중 → {raw_doi}  (norm: {norm_doi}) | {title}...")
        abstract = get_abstract_by_doi(norm_doi)

        if abstract:
            df.at[idx, "초록"] = abstract
            print(f"   → abstract 수집 성공 ({len(abstract)} chars)")
        else:
            df.at[idx, "초록"] = ""
            print(f"   → abstract 없음 / 접근 불가")

        time.sleep(sleep_sec)  # rate limit 대비

    df.to_excel(output_path, index=False)
    print(f"\n[DONE] Save Complete → {output_path}")


if __name__ == "__main__":
    enrich_excel_abstracts_doi_only(
        input_path="2.NTIS_PI_0021912_PAPER_2025-11-18.xlsx",
        output_path="NTIS_PAPER_with_abstract(DOI_only)_re.xlsx",
        sleep_sec=0.5,
    )
