# TikTok Impersonation Scout

Internal automation workflow for monitoring TikTok impersonation and counterfeit activity. The system automates daily discovery by querying TikTok search surfaces (hashtag, video, user), filtering results deterministically, and exporting structured Excel reports for investigators. It also supports iterative keyword refinement using Azure OpenAI.

---
## Quickstart

### 1. Clone the repository

```bash
git clone https://github.com/Mon-maker/tiktok_impersonation_scout.git
cd tiktok_impersonation_scout
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Set environment variables

Create a `.env` file based on `.env.example` and set:

- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_API_ENDPOINT`
- `AZURE_OPENAI_DEPLOYMENT_NAME`
- `AZURE_OPENAI_API_VERSION`

### 4. Prepare configuration

Edit `configs/target2detect.example.json` with your target keywords and rename it if needed.

### 5. Run a single scan

```bash
python tiktok_impersonation_scout.py --target brand_a
```

Reports will be generated in the output directory as structured Excel files.
## What This Does

### Collects TikTok results from:
- Hashtag search
- Video search
- User search (then profile crawling)

### Applies deterministic filters:
- Keyword-group **AND matching** for “risk estimation” phrases
- Ignore phrases list
- Language exclusion rules (regex-based detection)

### Outputs:
- Daily Excel report with user + video metadata
- Optional iterative keyword refinement loop
- Snapshot-based configuration tracking between runs

---

## Core Entry Points

- `run_full_pipeline.py`  
  Runs multi-iteration scan + optimize + snapshot comparisons.

- `tiktok_impersonation_scout.py`  
  Runs the scraping + report generation.

---

## Repo Structure

### `run_full_pipeline.py`
Orchestrates N iterations:
1. Run scraper  
2. Run keyword optimizer (if more iterations)  
3. Save snapshot configs and Excel reports  
4. Compute overlap ratio between iteration reports  

---

### `tiktok_impersonation_scout.py`
- Loads configs and cookies  
- Runs searches and profile scraping  
- Builds report dataframe and writes Excel output  

---

### `tiktok_scraper.py`
- Selenium-based session  
- Extracts internal API requests from Chrome performance logs  
- Calls TikTok endpoints via `requests` using captured headers + cookies  
- Includes blocker removal and slider CAPTCHA handler  

---

### `web_scraper.py`
- Selenium driver wrapper utilities  
- HTML fetching helpers  
- Image download utilities  

---

### `optimizer.py`
- Azure OpenAI-driven keyword-group optimizer  
- Proposes refined keyword groups  
- Suggests ignore phrases and excluded languages  

---

## Output

### Reports

Excel reports are saved per run (or per iteration). Fields include:

- `user_id`, `user_nickname`, `user_signature`
- `video_id`, `video_created_time`, `video_url`, `video_desc`
- Additional columns for OCR / ASR / logo detection and risk-level logic

---

### Snapshots

`run_full_pipeline.py` creates a timestamped folder:

```
snapshots/snapshot_YYYYMMDD_HHMM/
    reports/report1.xlsx
    reports/report2.xlsx
    snapshot1.json
    snapshot2.json
    comparison_summary.json
```

`comparison_summary.json` contains overlap ratio between iterations.

---

## How It Works

### 1. Search + Collection
- Uses Selenium to navigate TikTok  
- Captures internal API URLs from Chrome performance logs  
- Replays API requests via `requests` with captured headers + cookies  

---

### 2. Deterministic Filtering
- Keyword groups require **all terms (AND logic)** in video description  
- Filters out:
  - General ignore phrases
  - Excluded languages via Unicode regex patterns  

---

### 3. Reporting
- Concatenates results into a dataframe  
- Exports structured Excel reports  

---

### 4. Iterative Keyword Refinement (Optional)
- `optimizer.py` sends sampled detections to Azure OpenAI  
- Proposes tighter keyword groups  
- Suggests updated ignore signals  
- Saves updated config per iteration  

---

## Setup

### Prerequisites
- Python 3.10+
- Google Chrome
- Compatible ChromeDriver on PATH
- Valid TikTok session cookies JSON

---

### Python Dependencies

Required packages include:

```
pandas
numpy
selenium
requests
cloudscraper
fake-useragent
tqdm
pillow
opencv-python
openai
```

---

## Configuration

The system loads:

- `configs/main_config.json` for general settings
- Target definition JSON (via `target_info_filepath`)
- Cookies JSON (via `cookies_filepath`)

---

### Target Config Fields

Each target (brand/client) contains:

- `keywords2search`
- `keywords4risk_estimation`
- `general_keywords2ignore`
- `language2ignore` or `languages2ignore`

---

⚠️ **Note**

`run_full_pipeline.py` references:

```
CONFIG_PATH = "target2detect.json"
```

While `optimizer.py` references:

```
configs/target2detect.json
```

Unify these paths before publishing.

---

## Usage

### Run a Single Scan

```bash
python tiktok_impersonation_scout.py \
    --target <TARGET_NAME> \
    --iteration 1 \
    --snapshot-dir snapshots/manual_run \
    --report-path snapshots/manual_run/report1.xlsx
```

---

### Run Full Iterative Pipeline

```bash
python run_full_pipeline.py \
    --target <TARGET_NAME> \
    --guideline "<WHAT_COUNTS_AS_RELEVANT>" \
    --iterations 3
```

This will:
- Create timestamped snapshot directory
- Run scraper each iteration
- Run optimizer between iterations
- Generate comparison summary

---

### Skip Scraping (Debug Mode)

```bash
python run_full_pipeline.py \
    --target <TARGET_NAME> \
    --guideline "<...>" \
    --iterations 3 \
    --skip-scraper
```

Reuses previous reports for iteration continuity.

---
