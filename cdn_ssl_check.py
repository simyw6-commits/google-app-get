import base64
import hashlib
import time
import json
import requests
import hmac
import ssl
import socket
import urllib.parse
import os
from datetime import datetime, timezone
from hashlib import sha256
from xml.etree import ElementTree as ET

# ===================== 配置區 (從環境變數讀取) =====================
ACCESS_KEY = os.environ.get("CDN_ACCESS_KEY")
SECRET_KEY = os.environ.get("CDN_SECRET_KEY")
HOST = "api.cdnetworks.com"
URI = "/api/domain"
HTTP_METHOD = "GET"

# 第二個機器人的配置
TG_BOT_TOKEN = os.environ.get("CDN_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("CDN_CHAT_ID")
# 使用者要求：5 天內通知
SSL_WARNING_DAYS = int(os.environ.get("SSL_WARNING_DAYS", 5)) 
# =====================================================================

def canonical_request_method(method, request_uri, request_payload, host):
    signed_headers = 'content-type;host'
    canonical_headers = f'content-type:application/json\nhost:{host}\n'
    if method in ["GET", "DELETE"]:
        request_payload = ''
    uri = request_uri.split('?')[0]
    query_string = urllib.parse.unquote(request_uri.split('?')[1]) if "?" in request_uri else ""
    hashed_payload = hashlib.sha256(request_payload.encode('utf-8')).hexdigest()
    canonical_request = f"{method}\n{uri}\n{query_string}\n{canonical_headers}\n{signed_headers}\n{hashed_payload}"
    return hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()

def get_authorization_header(access_key, secret_key, timestamp, canonical_request):
    string_to_sign = f"CNC-HMAC-SHA256\n{timestamp}\n{canonical_request}"
    signature = base64.b16encode(hmac.new(secret_key.encode('utf-8'), string_to_sign.encode('utf-8'), digestmod=sha256).digest()).decode()
    return f"CNC-HMAC-SHA256 Credential={access_key}, SignedHeaders=content-type;host, Signature={signature}"

def send_request(uri, method="GET", body=None):
    timestamp = int(time.time())
    payload_json = json.dumps(body) if body else "{}"
    canonical_req_hash = canonical_request_method(method, uri, payload_json, HOST)
    auth_header = get_authorization_header(ACCESS_KEY, SECRET_KEY, timestamp, canonical_req_hash)
    headers = {
        'x-cnc-auth-method': 'AKSK',
        'x-cnc-accessKey': ACCESS_KEY,
        'x-cnc-timestamp': str(timestamp),
        'Authorization': auth_header,
        'Content-Type': 'application/json'
    }
    url = f'https://{HOST}{uri}'
    try:
        response = requests.request(method, url, headers=headers, data=payload_json if method != "GET" else None, timeout=15)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"CDNetworks API 請求失敗: {e}")
        return None

def get_cdn_domains():
    resp = send_request(URI, HTTP_METHOD)
    if not resp: return []
    domains = []
    try: # 嘗試解析 JSON
        data = json.loads(resp)
        if isinstance(data, list):
            domains = [item.get("domain-name") for item in data if item.get("domain-name")]
        elif isinstance(data, dict) and "domain-name" in data:
            domains = [data["domain-name"]]
    except json.JSONDecodeError: # 嘗試解析 XML
        try:
            root = ET.fromstring(resp)
            domains = [elem.text for elem in root.iter('domain-name') if elem.text]
        except ET.ParseError:
            print("無法解析 API 響應內容")
    return list(set(domains))

def get_ssl_remaining_days(domain):
    try:
        context = ssl.create_default_context()
        with socket.create_connection((domain, 443), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()
                expiry_date = datetime.strptime(cert['notAfter'], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
                remaining = (expiry_date - datetime.now(timezone.utc)).days
                return remaining
    except Exception:
        return -999

def send_tg_alert(msg):
    if not TG_BOT_TOKEN or not TG_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    requests.post(url, json=payload, timeout=10)

def main():
    print(f"[{datetime.now()}] 啟動 CDN SSL 監控任務 (閾值: {SSL_WARNING_DAYS}天)")
    domains = get_cdn_domains()
    if not domains:
        send_tg_alert("❌ *CDN SSL 檢查錯誤*\n無法取得域名列表，請檢查 API 金鑰。")
        return
    
    alerts = []
    for domain in domains:
        days = get_ssl_remaining_days(domain)
        if days == -999:
            alerts.append(f"❌ `{domain}`: 無法連線/抓取證書")
        elif days <= SSL_WARNING_DAYS:
            status_emoji = "🚨" if days <= 0 else "⚠️"
            alerts.append(f"{status_emoji} `{domain}`: 剩餘 *{days}* 天")

    if alerts:
        msg = f"🔔 *CDN SSL 過期預警 (5天內)*\n\n" + "\n".join(alerts)
        send_tg_alert(msg)
        print("已發送報警訊息。")
    else:
        print("所有域名狀態良好。")

if __name__ == "__main__":
    main()
