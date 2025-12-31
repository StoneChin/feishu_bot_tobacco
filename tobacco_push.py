import os
import re
import time
import base64
import hmac
import hashlib
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

LIST_URL = "http://www.tobacco.gov.cn/gjyc/zpxx/list.shtml"

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def fetch_top15(url: str, limit: int = 15):
    """
    尽量稳健地从列表页抓取前 limit 条（标题、链接）。
    规则：抓取所有 <a href>，筛选出指向 zpxx 的详情页（*.shtml），去重后取前 limit 条。
    """
    resp = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    resp.raise_for_status()
    # 自动处理中文编码
    resp.encoding = resp.apparent_encoding

    soup = BeautifulSoup(resp.text, "html.parser")

    items = []
    seen = set()

    for a in soup.find_all("a", href=True):
        title = (a.get_text(strip=True) or "").strip()
        href = a["href"].strip()

        # 过滤无效链接
        if not title or href.startswith("javascript:") or href.startswith("#"):
            continue

        # 过滤出“详情页”链接（通常为 .shtml，且路径含 /gjyc/zpxx/，排除 list.shtml）
        if "gjyc/zpxx" not in href.replace("\\", "/"):
            continue
        if not re.search(r"\.s?html?$", href, flags=re.I):
            continue
        if "list.shtml" in href:
            continue

        full_url = urljoin(url, href)
        if full_url in seen:
            continue
        seen.add(full_url)

        items.append((title, full_url))
        if len(items) >= limit:
            break

    return items


def gen_feishu_sign(secret: str, timestamp: str) -> str:
    """
    飞书自定义机器人“签名校验”：
    stringToSign = timestamp + "\n" + secret
    sign = Base64( HmacSHA256(key=stringToSign, msg="") )
    :contentReference[oaicite:2]{index=2}
    """
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    h = hmac.new(string_to_sign, b"", hashlib.sha256).digest()
    return base64.b64encode(h).decode("utf-8")


def post_to_feishu(webhook: str, text: str, secret: str | None = None):
    payload = {
        "msg_type": "text",
        "content": {"text": text},
    }

    # 如果配置了签名密钥，则附加 timestamp + sign
    if secret:
        ts = str(int(time.time()))
        payload["timestamp"] = ts
        payload["sign"] = gen_feishu_sign(secret, ts)

    r = requests.post(webhook, json=payload, timeout=30)
    r.raise_for_status()
    return r.text


def main():
    webhook = os.environ.get("FEISHU_WEBHOOK", "").strip()
    secret = os.environ.get("FEISHU_SECRET", "").strip() or None

    if not webhook:
        raise RuntimeError("Missing env FEISHU_WEBHOOK")

    items = fetch_top15(LIST_URL, 15)

    if not items:
        msg = f"【国家烟草｜人才招聘】抓取失败：未解析到公告条目。\n列表页：{LIST_URL}"
        print(post_to_feishu(webhook, msg, secret))
        return

    lines = ["【国家烟草｜人才招聘】最新公告前15条", f"来源：{LIST_URL}", ""]
    for i, (title, link) in enumerate(items, 1):
        lines.append(f"{i}. {title}")
        lines.append(f"   {link}")

    msg = "\n".join(lines)
    print(post_to_feishu(webhook, msg, secret))


if __name__ == "__main__":
    main()
