import os
from openai import OpenAI\

api_key = os.environ.get("OPENAI_API_KEY_KIT")

if not api_key:
    raise RuntimeError(
        "환경변수 OPENAI_API_KEY_KIT가 설정되지 않았습니다.\n"
        "OS 환경변수 설정 후 다시 실행하세요."
    )

client = OpenAI(api_key = api_key)


def question(system_content, prompt):
        
    try:
        message = [{"role":"system", "content":" ".join(system_content)}, 
                   {"role":"user","content":f"{prompt}"}]
            
        completion = client.chat.completions.create(
                model="gpt-4o",
                messages=message,
                temperature=0.2
            )

        result = completion.choices[0].message.content

        return result

    except Exception as e:
        print(f"Error : {e}")
        
if __name__ == "__main__":
    system_content = [
        "user의 질문에 최대한 친절하게 대답하세요",
        "답변은 100자를 넘기지 마세요.",
        ]
    prompt = "헤밍웨이는 1차 대전에 이탈리아군으로 참전한거 아냐?"
    answer = question(system_content, prompt)
    print(answer)