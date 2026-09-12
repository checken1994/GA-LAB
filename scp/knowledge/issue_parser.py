import json
import re
import urllib.error
import urllib.parse
import urllib.request

from scp.security.url_safety import safe_urlopen

import logging
logger = logging.getLogger(__name__)


# [S6b security sweep] GitHub repo identifier must be a strict owner/name
# pair — anything else (path segments, scheme, whitespace, control chars)
# is rejected BEFORE the URL is built, so no request can leave the process
# with an attacker-shaped URL.
_GITHUB_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def parse_top_1_percent_issues(repo="pallets/flask"):
    # Cào Issue/PR từ các repo top 1% về làm bài test thực chiến
    # [S6b security sweep] Boundary: repo được regex-validate trước, URL cuối
    # được check scheme https + host api.github.com, rồi fetch qua
    # safe_urlopen (scheme + host + resolved-IP boundary trong
    # scp/security/url_safety.py). Repo lạ -> ValueError, không request nào.
    if not _GITHUB_REPO_RE.match(repo or ""):
        raise ValueError(f"invalid GitHub repo identifier: {repo!r}")
    url = f"https://api.github.com/repos/{repo}/issues?state=closed&labels=bug&per_page=5"
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "api.github.com":
        raise ValueError("Unexpected GitHub issues endpoint")
    headers = {"User-Agent": "SCP-Crawler"}
    # Token bucket rate limiting is applied in scheduled_crawler.py

    req = urllib.request.Request(url, headers=headers)
    try:
        with safe_urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                return 0
            issues = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError:
        logger.debug('parse_top_1_percent_issues: urllib.error.HTTPError ignored', exc_info=True)
        return 0
    with open("data/top1_issues.jsonl", "a", encoding="utf-8") as f:
        for issue in issues:
            f.write(json.dumps({"title": issue["title"], "body": issue.get("body", "")}) + "\n")
    return len(issues)
