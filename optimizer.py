import os
import json
import pandas as pd
from datetime import datetime, timedelta
from openai import AzureOpenAI

# === Azure OpenAI Configuration ===
import os

# === Azure OpenAI Configuration ===
AOAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AOAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2023-12-01-preview")
AOAI_API_ENDPOINT = os.getenv("AZURE_OPENAI_API_ENDPOINT")
DEPLOY_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")

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
You optimize TikTok search keyword groups.

Target: {target}
Relevance guideline: {guideline}

Definition:
- keywords2search is List[List[str]].
- A group matches only if ALL terms appear in the video description (AND).

Input:
You will receive JSON samples of matched videos. Each sample includes:
- description
- matched_keyword_groups
- (optional) relevance_label (relevant / irrelevant)

Task:
- Improve precision while preserving coverage.
- Prefer minimal changes. If evidence is weak, keep the original groups.
- Do not increase the number of groups.

Return ONLY valid JSON (no markdown, no explanations, double quotes only):
{{
  "merged_keywords2search": [["term1","term2"], ...],
  "new_general_keywords2ignore": ["phrase1","phrase2", ...],
  "new_languages2ignore": ["vi","ar","th", ...]
}}
Constraints:
- merged_keywords2search length <= original length
- Do not invent new product names. Use only terms observed in samples or present in current keywords.
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




