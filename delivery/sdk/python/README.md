# SDK پایتون UniqueMemory

## نصب
```bash
pip install uniquememory-sdk==1.0.0
```

## نمونه استفاده
```python
from uniquememory import Client

client = Client(client_id="<CLIENT_ID>", client_secret="<CLIENT_SECRET>")

results = client.search(company_id="alpha-tech", query="chargeback investigation")
print(results.latency_ms, len(results.hits))
```

## نکات نسخه GA
- پشتیبانی از احراز هویت OAuth2 Client Credentials.
- ارسال خودکار متریک‌های latency و دقت به Grafana Agent.
