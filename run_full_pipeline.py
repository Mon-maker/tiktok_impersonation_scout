import os
import json
import shutil
import copy
from datetime import datetime
import pandas as pd
from optimizer import optimize_keywords
import time
import subprocess   

# === CONFIG ===
CONFIG_PATH    = "target2detect.json"
SNAPSHOT_ROOT  = "snapshots"
SCRAPER_SCRIPT = "tiktok_impersonation_scout.py"

start_time = time.time()

def compare_excel_reports_json(file1, file2, target, iteration):
    def load_video_ids(path):
        df = pd.read_excel(path)
        return set(df["video_id"].astype(str)) if "video_id" in df.columns else set()

    ids1 = load_video_ids(file1)
    ids2 = load_video_ids(file2)

    added = sorted(list(ids2 - ids1))
    removed = sorted(list(ids1 - ids2))
    intersection = sorted(list(ids1 & ids2))

    return {
        "target": target,
        "from": os.path.basename(file1),
        "to": os.path.basename(file2),
        "intersection_count": len(intersection),
        "total_in_previous": len(ids1),
        "total_in_current": len(ids2),
        
        "overlap_ratio_percent": f"{round(len(intersection) / len(ids2) * 100)}%" if ids2 else "0%"
    }

        # "added_video_ids": added,
        # "removed_video_ids": removed,

def make_snapshot_dir():
    timestamp = datetime.now().strftime("snapshot_%Y%m%d_%H%M")
    path = os.path.join(SNAPSHOT_ROOT, timestamp)
    os.makedirs(path, exist_ok=True)
    return path

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
    
def save_json(data, path):
    import json

    # First, write the normally indented JSON
    raw_text = json.dumps(data, ensure_ascii=False, indent=2)

    # Then, collapse single-line list entries like [["a"], ["b", "c"]] into one-liners
    import re
    def collapse_lists(match):
        items = match.group(1)
        # Remove all newlines and extra space inside the matched list
        collapsed = re.sub(r"\s+", " ", items).strip()
        return "[ " + collapsed + " ]"

    collapsed_text = re.sub(r"\[\s*((?:\[[^\[\]]*?\],?\s*)+?)\]", collapse_lists, raw_text)

    # Save to file
    with open(path, "w", encoding="utf-8") as f:
        f.write(collapsed_text)

def run_scraper(target, iteration, snapshot_dir, report_path):
    subprocess.run([
        "python", "tiktok_impersonation_scout.py",
        "--target", target,
        "--iteration", str(iteration),
        "--snapshot-dir", snapshot_dir,
        "--report-path", report_path  # add this
    ], check=True)


def main(target, guideline, iterations, skip_scraper=False):
    snapshot_dir = make_snapshot_dir()
    reports_subdir = os.path.join(snapshot_dir, "reports")
    os.makedirs(reports_subdir, exist_ok=True)

    base_config = load_json(CONFIG_PATH)
    if target not in base_config:
        raise ValueError(f"Target '{target}' not found in configuration file.")

    target_config = copy.deepcopy(base_config[target])
    save_json(target_config, os.path.join(snapshot_dir, "snapshot1.json"))

    comparison_results = []

    for i in range(1, iterations + 1):
        print(f"\n🔁 Iteration {i}/{iterations}")

        excel_dst = os.path.join(reports_subdir, f"report{i}.xlsx")

        if not skip_scraper:
            print("🚀 Running scraper...")
            run_scraper(target, i, snapshot_dir, excel_dst)
        else:
            print("⏭️ Skipping scraper as requested...")
            if i == 1:
                raise FileNotFoundError("❌ No Excel report available to start iteration.")
            else:
                excel_src = os.path.join(reports_subdir, f"report{i - 1}.xlsx")
                if os.path.exists(excel_src):
                    shutil.copy(excel_src, excel_dst)
                    print(f"📄 Reusing previous snapshot: {excel_src}")
                else:
                    raise FileNotFoundError("❌ No Excel report or snapshot to continue iteration.")

        # Run optimizer if more iterations ahead
        if i < iterations:
            print("🧠 Running optimizer...")
            df = pd.read_excel(excel_dst)
            target_config = optimize_keywords(
                target=target,
                guideline=guideline,
                df=df,
                target_config=target_config,
                iterations=1
            )

            next_config_path = os.path.join(snapshot_dir, f"snapshot{i + 1}.json")
            save_json(target_config, next_config_path)

        # Compare with previous Excel snapshot
        if i > 1:
            file1 = os.path.join(reports_subdir, f"report{i - 1}.xlsx")
            file2 = os.path.join(reports_subdir, f"report{i}.xlsx")
            result = compare_excel_reports_json(file1, file2, target, i)
            comparison_results.append(result)

    print("\n✅ All iterations completed. Final snapshot folder:", snapshot_dir)\
    
    if comparison_results:
        print("\n📊 Comparison Summary:")
    for res in comparison_results:
        print(json.dumps(res, ensure_ascii=False, indent=2))

    # Save to file
    summary_path = os.path.join(snapshot_dir, "comparison_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(comparison_results, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Comparison results saved to: {summary_path}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--guideline", required=True)
    parser.add_argument("--iterations", type=int, default=2)
    parser.add_argument("--skip-scraper", action="store_true", help="Skip the scraper step")
    args = parser.parse_args()

    main(args.target, args.guideline, args.iterations, skip_scraper=args.skip_scraper)
