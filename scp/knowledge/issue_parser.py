import json

import requests


def parse_top_1_percent_issues(repo="pallets/flask"):
    # Cào Issue/PR từ các repo top 1% về làm bài test thực chiến.
    url = f"https://api.github.com/repos/{repo}/issues?state=closed&labels=bug&per_page=5"
    headers = {"User-Agent": "SCP-Crawler"}
    # Bound the network call. Rate limiting alone does not protect against a
    # stalled peer/connection, and this crawler must never hang indefinitely.
    response = requests.get(url, headers=headers, timeout=15)
    if response.status_code == 200:
        issues = response.json()
        with open("data/top1_issues.jsonl", "a", encoding="utf-8") as f:
            for issue in issues:
                f.write(json.dumps({"title": issue["title"], "body": issue.get("body", "")}) + "\n")
        return len(issues)
    return 0
