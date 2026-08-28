import re

with open(r"c:\Users\check\Downloads\scp\scp\core\api_utils.py", "r", encoding="utf-8") as f:
    text = f.read()

# Add tenacity import if not present
if "from tenacity import" not in text:
    text = text.replace("import urllib.request", "import urllib.request\nfrom tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type\n")

# Replace fetch_with_retry completely
# I need to match everything from def fetch_with_retry to the end or to the next class/def
fetch_with_retry_code = """
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((urllib.error.URLError, ConnectionError, TimeoutError)),
    reraise=False
)
def fetch_with_retry(url, headers=None, timeout=10, max_retries=3):
    # --- SCP V3 ENTERPRISE: TENACITY RETRY & CIRCUIT BREAKER ---
    from scp.core.url_fetcher import _safe_fetch_url
    try:
        raw_bytes = _safe_fetch_url(url)
        return json.loads(raw_bytes.decode("utf-8"))
    except ValueError as e:
        # SSRF / Policy violation. Do not retry.
        logger.warning(f"Policy violation fetching {url}: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.warning(f"JSON decode failed for {url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Transient error fetching {url}: {e}")
        raise  # Reraise to trigger Tenacity retry
"""

# We'll use a regex to replace `def fetch_with_retry(url, headers, timeout=10, max_retries=3):` and everything following it up to the next top-level def/class, but wait, it might be the last function.
# Let's just find where `def fetch_with_retry` starts, and replace to EOF if it's the last one, or to the next def/class.

start_idx = text.find("def fetch_with_retry")
if start_idx != -1:
    end_idx = text.find("\ndef ", start_idx + 10)
    if end_idx == -1:
        end_idx = text.find("\nclass ", start_idx + 10)
    
    if end_idx != -1:
        text = text[:start_idx] + fetch_with_retry_code + text[end_idx:]
    else:
        text = text[:start_idx] + fetch_with_retry_code

with open(r"c:\Users\check\Downloads\scp\scp\core\api_utils.py", "w", encoding="utf-8") as f:
    f.write(text)
