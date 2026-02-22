import os
import json
import pandas as pd
from datetime import datetime, timedelta
from openai import AzureOpenAI

# === Azure OpenAI Configuration ===
AOAI_API_KEY = "4eb6e63960e4482cbe22549890e19efe"
AOAI_API_VERSION = "2023-12-01-preview"
AOAI_API_ENDPOINT = "https://honeypot-test.openai.azure.com/"
DEPLOY_NAME = "Honeypot_test"

# === Paths ===
CONFIG_PATH = "configs/target2detect.json"
REPORTS_DIR = "reports/"

# === LLM Client ===
client = AzureOpenAI(
    api_key=AOAI_API_KEY,
    api_version=AOAI_API_VERSION,
    azure_endpoint=AOAI_API_ENDPOINT
)

def ask_llm_optimize_keywords(samples, target, guideline, current_keywords2search):
    system_prompt = f"""
You are an intelligent keyword optimizer for TikTok search.

The goal is to help find the most relevant video content for a specific client target: {target}.
The guideline for relevance is: \"{guideline}\"

Each keyword group in `keywords2search` is a list of strings. A keyword group matches a video only if **all the terms in the group appear together** in the video description (logical AND). The data provided includes matched video descriptions and their keyword hits.

Your task:
1. Analyze which keyword groups are effective at matching relevant content.
2. Identify noisy or misleading keyword groups that bring in unrelated content.
3. Simplify or merge groups where appropriate, without losing effectiveness.
4. Suggest phrases to ignore that frequently appear in irrelevant content.
5. Suggest languages to exclude if they commonly occur in unrelated content.

Rules:
- You must return the same structure: a list of keyword groups → `List[List[str]]`.
- The number of keyword groups in `merged_keywords2search` must **not exceed** the original count.
- Be compact and high-precision.
- Do NOT include any explanation in your output — only valid JSON.

Output a JSON object with these keys:
- `\"merged_keywords2search\"`: List of List of strings (refined search keywords)
- `\"new_general_keywords2ignore\"`: List of List of strings (phrases to block)
- `\"new_languages2ignore\"`: List of language names in Chinese (e.g. \"越南文\", \"阿拉伯文\")

Only return the JSON result. Nothing else.
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"""Current keywords2search:\n{json.dumps(current_keywords2search, ensure_ascii=False, indent=2)}\n\nHere are 100 sample TikTok posts (with matched keywords):\n\n{json.dumps(samples[:100], ensure_ascii=False, indent=2)}"""}
    ]

    try:
        response = client.chat.completions.create(
            model=DEPLOY_NAME,
            messages=messages,
            temperature=0.2
        )
        content = response.choices[0].message.content
        start = content.find('{')
        end = content.rfind('}') + 1
        return json.loads(content[start:end])

    except Exception as e:
        print("❌ Azure OpenAI call failed:", e)
        return {
            "merged_keywords2search": current_keywords2search,
            "new_general_keywords2ignore": [],
            "new_languages2ignore": []
        }

def load_target_info():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_target_info(target_info):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(target_info, f, indent=2, ensure_ascii=False)

def load_latest_report(target, lookback_days=7):
    for i in range(lookback_days):
        date_str = (datetime.today() - timedelta(days=i)).strftime("%Y%m%d")
        filepath = os.path.join(REPORTS_DIR, f"target2detect_{date_str}.xlsx")
        if os.path.exists(filepath):
            print(f"📄 Found report for {date_str}: {filepath}")
            df = pd.read_excel(filepath)
            return df[df["target"] == target]
    raise FileNotFoundError(f"No report file found in the past {lookback_days} days.")

def prepare_samples(df, max_samples=100):
    rows = df.to_dict(orient="records")

    return [
        {
            "video_id": row["video_id"],
            "description": row["video_desc"],
            "matched_keywords": row["matched_keywords"] if isinstance(row["matched_keywords"], (list, set)) else [],
            "target": row["target"]
        }
        for row in rows
    ]

def optimize_keywords(target: str, guideline: str, df: pd.DataFrame, target_config: dict, iterations: int = 5) -> dict:
    for i in range(iterations):
        print(f"\n=== Optimization Iteration {i+1}/{iterations} ===")

        samples = prepare_samples(df)

        result = ask_llm_optimize_keywords(
            samples=samples,
            target=target,
            guideline=guideline,
            current_keywords2search=target_config["keywords2search"]
        )

        # Update target config
        target_config["keywords2search"] = result.get("merged_keywords2search", target_config["keywords2search"])
        target_config["general_keywords2ignore"].extend(result.get("new_general_keywords2ignore", []))
        target_config["languages2ignore"].extend(result.get("new_languages2ignore", []))  # ✅ fix

        # Deduplicate
        target_config["general_keywords2ignore"] = [list(x) for x in set(tuple(x) for x in target_config["general_keywords2ignore"])]
        target_config["languages2ignore"] = list(set(target_config["languages2ignore"]))  # ✅ fix

    return target_config
