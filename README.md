# uniquememory

در ادامه «رودمپ کاملاً دقیق، مرحله‌به‌مرحله و بدون ابهام» برای ساخت «حافظهٔ جهانی کاربر برای ایران» ارائه می‌شود؛ مبتنی بر معماری چند‌لایه با MCP API برای اتصال ایجنت‌ها، Vector Retrieval برای RAG و Graph برای دانشِ رابطه‌ای. تمام بندها عملیاتی هستند و می‌توانید مستقیم وارد اجرا شوید.

هدف و دامنه
	•	هدف: یک سرویس «حافظهٔ یکتای کاربر» که همهٔ ایجنت‌ها/شرکت‌ها با رضایت کاربر به آن خواندن/نوشتن داشته باشند.
	•	دامنهٔ MVP:
	1.	CRUD ورودی‌های حافظه، 2) مکانیزم رضایت (Consent) قابل بازپس‌گیری، 3) بازیابی معنایی (Vector + Hybrid)، 4) سرور MCP برای اتصال ایجنت‌ها، 5) گراف دانش (روابط کاربر←موضوع←ورودی←ایجنت/شرکت)، 6) حسابرسی کامل و قابل گزارش‌گیری.

⸻

الزامات غیرعملکردی (NFR)
	•	Latency هدف: p95 زیر 300ms برای خواندن‌های گرم، زیر 800ms برای Query برداری.
	•	SLA: 99.5٪ MVP، 99.9٪ پس از GA.
	•	مقیاس‌پذیری: حداقل ۱۰۰ شرکت، ۱M کاربر، ۵۰M ورودی.
	•	اقامت داده: دیتاسنتر داخل ایران + گزینهٔ چند-منطقه‌ای.
	•	امنیت: TLS1.3، AES-256 at-rest، KMS/Vault، RBAC+ABAC، لاگ‌برداری ممیزی سطح رویداد.
	•	بومی‌سازی: پشتیبانی کامل فارسی/RTL، تقویم شمسی در UI ادمین (اختیاری).

⸻

معماری کلان (اجزا و مسئولیت‌ها)
	1.	API Gateway/Auth: OAuth2/OIDC (PKCE برای کاربر، Client Credentials برای سرور-به-سرور)، صدور و اعتبارسنجی JWT با Scope و Claimهای user_id, client_id, company_id.
	2.	Memory Core (Django + DRF):
	•	CRUD ورودی‌ها + نسخه‌گذاری optimistic + Merge Policy
	•	سیاست‌های دسترسی (Consent/Scopes/ABAC)
	•	خلاصه‌سازی و تقطیع (Chunking)
	3.	Embeddings & Retrieval Service:
	•	Pipeline برش/Embedding/Index
	•	Hybrid Retrieval (BM25 + Vector) + Re-rank
	4.	Vector DB: pgvector (ساده‌سازی زیرساخت) یا Qdrant/Milvus برای مقیاس بالا.
	5.	Graph DB: Neo4j (روابط User–Entry–Topic–Agent–Company–Consent).
	6.	Object Store: MinIO/S3 برای پیوست‌ها (تصویر/صوت/سند).
	7.	Event Bus/Workers: Redis Streams/Celery یا Kafka برای کارهای پس‌زمینه (embedding, summarization, redaction).
	8.	MCP Server: ابزارهای memory.search, memory.get, memory.upsert, memory.delete, consent.grant/revoke.
	9.	Admin & Consent Portal (Flutter Web/React): مدیریت شرکت‌ها، کلیدها، سطوح دسترسی، گزارش‌ها.
	10.	Observability: OpenTelemetry, Loki/ELK, Prometheus/Grafana، Audit Trail جزیی.

⸻

مدل داده (Postgres) — جداول و کلیدها

users(id, phone_hash, …)
companies(id, name, status, …)
agents(id, company_id→companies.id, name, mcp_manifest_url, status)
clients(id, company_id, type, public_key, scopes[])
consents(id, user_id→users, agent_id→agents, scopes[], sensitivity_levels[], status, issued_at, revoked_at, version)
memory_entries(id UUID pk, user_id, type, title, content, structured JSONB, sensitivity ENUM[low|medium|high], provenance, version INT, created_at, updated_at, deleted_at NULL)
entry_chunks(id, entry_id→memory_entries, idx INT, text, tokens INT)
embeddings(id, chunk_id→entry_chunks, dim INT, vec VECTOR, model, created_at)
access_policies(id, entry_id, read_acl JSONB, write_acl JSONB)
audit_logs(id, ts, actor_type ENUM[user|agent|admin|system], actor_id, action, target_type, target_id, reason, ip, user_agent, request_id)
api_keys(id, company_id, name, hash, scopes[], rate_limit, created_at, revoked_at)
webhooks(id, company_id, url, secret, events[], status)

ایندکس‌های حیاتی:
	•	(user_id, updated_at desc) روی memory_entries
	•	GIN روی structured، Trigram/BTree روی title/content (برای Hybrid)
	•	HNSW/IVF (در Qdrant/Milvus) یا ivfflat در pgvector برای vec
	•	یکتا: (user_id, agent_id, version) در consents

⸻

مدل گراف (Neo4j)

گره‌ها: User, Company, Agent, MemoryEntry, Topic, Consent
روابط:
	•	(:User)-[:HAS_CONSENT]->(:Consent)-[:GRANTS_TO]->(:Agent)
	•	(:MemoryEntry)-[:BELONGS_TO]->(:User)
	•	(:MemoryEntry)-[:ABOUT]->(:Topic)
	•	(:Agent)-[:OWNED_BY]->(:Company)
	•	(:Agent)-[:WROTE]->(:MemoryEntry) / (:Agent)-[:READ]->(:MemoryEntry) (با properties: ts, scope)

کاربرد: توصیه‌گر موضوعی، استنتاج سیاق (context) فراتر از شباهت صرفاً برداری، کشف تضادها.

⸻

سیاست‌های دسترسی و حساسیت
	•	Scopes: memory.read, memory.write, memory.search, consent.read, consent.manage, audit.read
	•	ABAC: قاعده‌های مبتنی بر ویژگی‌ها (e.g., sensitivity=high فقط برای agents با role=medical + consent صریح).
	•	Consent Artifact: سند امضاشده شامل: user_id، agent_id، scopes، سطوح حساسیت مجاز، مدت اعتبار، نسخهٔ شرایط.
	•	Right to Revoke/Forget: API‌ روشن + propagation به Vector/Graph/Objects + ثبت در Audit.
	•	Redaction: پالایش خودکار قبل از ارسال به LLM (حذف شناسه‌های حساس/کاهش جزئیات).

⸻

API طراحی (REST, نسخه‌گذاری /v1)

احراز هویت
	•	End-user: OAuth2/OIDC با PKCE (ورود با موبایل/OTP داخلی کشور قابل اضافه).
	•	Server-to-Server: Client Credentials + JWT از Gateway.
	•	Claims ضروری: sub=user_id، client_id، company_id، scopes[]، consent_id?.

مسیرها (نمونهٔ حداقل)
	•	POST /v1/consents
ورودی: { user_id, agent_id, scopes, sensitivity_levels, ttl_days } → خروجی: consent_id, status, version.
	•	POST /v1/consents/{id}/revoke
	•	GET /v1/memory/{user_id}/entries?type=&since=&limit=
	•	POST /v1/memory/{user_id}/entries
بدنه: { type, title?, content, structured?, sensitivity, provenance?, suggested_access? }
	•	PATCH /v1/memory/{user_id}/entries/{entry_id} (Optimistic: If-Match: version)
	•	DELETE /v1/memory/{user_id}/entries/{entry_id}?soft=true
	•	POST /v1/memory/{user_id}/query
{ q, k=8, filters:{type?, sensitivity?}, hybrid:true, rerank:true } → [ {entry_id, score, chunk, snippet} ]
	•	GET /v1/audit?user_id=&agent_id=&since=&action=read|write
	•	Webhooks: POST company_url با رویدادهایی مثل memory.entry.created/updated/deleted, consent.revoked

قرارداد خطاها
	•	JSON با code, message, request_id, hint؛ استفاده از 409 برای تضاد نسخه، 403 برای عدم احراز/مجوز.

⸻

MCP Server (تعریف ابزارها برای ایجنت‌ها)

Manifest مفهومی:

{
  "server_label": "user-memory-iran",
  "tools": [
    {"name": "memory.search", "input_schema": {"q":"string","k":"int","filters":"object"}, "output_schema": {"results":"array"}},
    {"name": "memory.get", "input_schema": {"entry_id":"string"}, "output_schema": {"entry":"object"}},
    {"name": "memory.upsert", "input_schema": {"user_id":"string","entry":"object"}, "output_schema": {"entry_id":"string","version":"int"}},
    {"name": "memory.delete", "input_schema": {"entry_id":"string","soft":"boolean"}, "output_schema": {"ok":"boolean"}},
    {"name": "consent.grant", "input_schema": {"user_id":"string","agent_id":"string","scopes":"array","sensitivity":"array","ttl_days":"int"}, "output_schema": {"consent_id":"string"}},
    {"name": "consent.revoke", "input_schema": {"consent_id":"string"}, "output_schema": {"ok":"boolean"}}
  ],
  "auth": {"type":"oauth2-bearer"}
}

رفتار الزامی ابزارها:
	•	هر فراخوانی باید وجود consent معتبر را بررسی کند و Scope را enforce نماید.
	•	رویدادها به Webhook شرکت (در صورت ثبت) ارسال شوند.

⸻

بازیابی معنایی و رتبه‌بندی
	•	Chunking: 400–800 توکن با overlap 20٪؛ متادیتا: نوع، حساسیت، زمان، منبع.
	•	Embedding: مدل چندزبانه با پشتیبانی قوی از فارسی (می‌توانید از سرویس‌های ابری یا مدل‌های محلی استفاده کنید).
	•	Hybrid Retrieval: نمره نهایی = 0.5*Vector + 0.3*BM25 + 0.2*GraphProximity (پارامترها قابل تنظیم).
	•	Re-rank: با سیگنال‌های متادیتا (تازگی، حساسیت، trust_score).
	•	Condensation: ادغام دوره‌ای ورودی‌های تکراری/نزدیک + آرشیو ورودی‌های کم‌اهمیت قدیمی.
	•	Filters: پیش‌فرض، sensitivity<=consent.sensitivity_max و type in consent.allowed_types.

⸻

امنیت، حریم خصوصی، انطباق
	•	رمزنگاری: TLS1.3؛ AES-256 در DB/Objects؛ مدیریت کلید با KMS/Vault؛ چرخش کلید دوره‌ای.
	•	DLP/Redaction: حذف شماره تماس/کدملی/آدرس پیش از خروجی به مدل‌ها (قابل تنظیم).
	•	Rate Limit & Quotas: per-company, per-agent, per-user.
	•	Threat Model:
	•	Token Leakage → کوتاه‌عمر بودن JWT، Pinned audience، mTLS اختیاری.
	•	Over-permission → حداقل دسترسی، مرور دوره‌ای consentها.
	•	Prompt Injection → فیلتر حافظهٔ حساس پیش از ارسال به LLM + Instruction Guard.
	•	Data Residency → بکاپ رمزگذاری‌شده در ایران + DR پلان.
	•	حقوق کاربر: Export JSON/ZIP، حذف کامل (Hard Delete)، تاریخچهٔ همهٔ خواندن/نوشتن‌ها.

⸻

DevOps و محیط اجرا
	•	محیط‌ها: dev, staging, prod (+ Sandbox شرکت‌ها).
	•	زیرساخت پیشنهاد‌شده:
	•	K8s (یا Docker Compose در MVP)، Nginx Ingress، Postgres 15 + pgvector، Redis، MinIO، Neo4j، (اختیاری Qdrant/Milvus).
	•	CI/CD:
	•	Lint/TypeCheck/Test/Coverage Gate (90٪)، SCA/Dependabot، Scan اسرار، SBOM.
	•	مهاجرت DB با alembic/migrations (برای Django: makemigrations/migrate).
	•	نسخه‌گذاری SemVer و auto-tag/release.
	•	Observability: OpenTelemetry Trace/Metric/Log، داشبورد SLA & Error Budget.
	•	Backup & DR: snapshot روزانه Postgres/Neo4j/Objects، تست بازگردانی ماهانه.

⸻

برنامهٔ زمانی و تحویل‌ها (12 هفتهٔ نمونهٔ اجرایی)

فاز 0 — تحلیل و طرح‌ریزی (هفته 1)
	•	سند Vision, Use-Cases, Threat Model, Data Classification.
	•	تعریف دقیق Scope/Scopes و ماتریس حساسیت.
	•	خروجی: SRS، ADRهای کلیدی، دیاگرام‌ها و Backlog.

فاز 1 — اسکلت بک‌اند و احراز هویت (هفته 2–3)
	•	راه‌اندازی Django+DRF، API Gateway، OAuth2/OIDC، مدل‌های پایه: users/companies/agents/clients.
	•	پیاده‌سازی صدور/اعتبارسنجی JWT، مدیریت کلیدها، Rate Limit ابتدایی.
	•	خروجی: OpenAPI /auth, /companies, /agents.

فاز 2 — هستهٔ حافظه و ممیزی (هفته 4–5)
	•	جداول memory_entries, entry_chunks, audit_logs, access_policies.
	•	CRUD کامل با Optimistic Concurrency و Soft/Hard Delete.
	•	Audit Trail سطح رویداد + سرچ پایه.
	•	خروجی: تست‌های واحد و یکپارچه + اسناد Swagger.

فاز 3 — برداری‌سازی و بازیابی (هفته 6)
	•	سرویس Embedding + Indexing، Hybrid Retrieval (BM25 + Vector).
	•	API /v1/memory/{user}/query با Re-rank اولیه.
	•	خروجی: بنچمارک اولیه p95 Latency و دقت.

فاز 4 — Consent & Policy (هفته 7)
	•	مدل و API consents + ABAC پیاده‌سازی، اجرای حساسیت‌ها در Query/CRUD.
	•	پرتال کاربر برای مدیریت دسترسی‌ها (Flutter Web ساده).
	•	خروجی: Flow اعطای مجوز، لینک اشتراک‌گذاری امن.

فاز 5 — گراف دانش (هفته 8)
	•	راه‌اندازی Neo4j، سنکرون روابط (User/Entry/Topic/Agent/Company).
	•	API کمکی /v1/graph/related?entry_id=.
	•	خروجی: بهبود کیفیت پاسخ با GraphProximity.

فاز 6 — MCP Server (هفته 9)
	•	پیاده‌سازی ابزارهای memory.search|get|upsert|delete و consent.grant|revoke با OAuth2 Bearer.
	•	تست اتصال با چند ایجنت نمونه (Python/Node).
	•	خروجی: Manifest MCP و نمونهٔ کد اتصال.

فاز 7 — Webhooks و Summarization (هفته 10)
	•	رخدادهای memory.entry.* و consent.* برای شرکت‌ها.
	•	Worker خلاصه‌ساز و چگالش حافظه (Condensation/Archive).
	•	خروجی: کاهش حجم حافظه با حفظ دقت.

فاز 8 — امنیت پیشرفته و DR (هفته 11)
	•	DLP/Redaction، WAF/IDS، mTLS اختیاری، تست نفوذ.
	•	بکاپ رمزگذاری‌شده، تمرین DR.
	•	خروجی: گزارش امنیت/انطباق داخلی.

فاز 9 — Pilot و GA (هفته 12)
	•	پایلوت با ۳ شرکت، KPI: Latency، دقت بازیابی، نرخ خطای مجوز.
	•	بهینه‌سازی نهایی + اسناد SDK.
	•	خروجی: GA و برنامهٔ مقیاس‌پذیری.

⸻

KPI و معیارهای پذیرش
	•	دقت Top-k@5 در کوئری‌های واقعی ≥ 0.75 (اندازه‌گیری با برچسب‌گذاری داخلی).
	•	p95 Latency جستجو ≤ 800ms در بار اسمی.
	•	صفر دسترسی غیرمجاز در تست‌های یکپارچه.
	•	پوشش تست ≥ 90٪ سرویس حافظه.
	•	زمان لغو مجوز تا بی‌اعتبار شدن Cache ≤ 30s.

⸻

بستهٔ مستندسازی و تحویل
	•	OpenAPI کامل /v1/** + مثال‌های Postman.
	•	MCP Manifest و راهنمای ادغام برای شرکت‌ها.
	•	SDKها: Python/Node/Flutter (Dart) با متدهای High-level.
	•	Security & Privacy Whitepaper + رویه‌های DLP/Consent.
	•	Runbook (Monitoring/Alert/On-call) + Playbook رخداد امنیتی.

⸻

پیوست A — نمونه JSON ورودی حافظه

{
  "type": "preference",
  "title": "ترجیحات تغذیه",
  "content": "کم‌نمک، پروتئین بالا؛ مرغ/ماهی",
  "structured": {"likes": ["مرغ", "ماهی"], "dislikes": ["فست‌فود"]},
  "sensitivity": "low",
  "provenance": {"agent_id": "agt_123", "method": "stated"},
  "suggested_access": {"read": ["agent:all"], "write": ["agent:self"]}
}

پیوست B — نمونه پاسخ memory.query

{
  "results": [
    {
      "entry_id": "e1",
      "score": 0.87,
      "chunk": 0,
      "snippet": "کم‌نمک و پروتئین بالا..."
    }
  ],
  "used_filters": {"sensitivity": ["low","medium"], "type": ["preference"]},
  "request_id": "req_abc"
}

پیوست C — نمونه رویداد Webhook (HMAC-SHA256)

{
  "event": "memory.entry.created",
  "ts": "2025-10-10T12:00:00Z",
  "user_id": "u_1",
  "entry_id": "e1",
  "signature": "hex(hmac(secret, payload))"
}

پیوست D — نمونه سیاست ABAC
	•	قانون: if entry.sensitivity == 'high' then require role in ['medical'] AND scope 'memory.read' AND consent.sensitivity_levels includes 'high'.

پیوست E — تست‌های کلیدی (BDD سطح API)
	•	ایجاد Consent، تلاش خواندن بدون Consent (403)، اعطای Consent (200)، خواندن موفق (200).
	•	نوشتن با تعارض نسخه (409).
	•	جست‌وجو با فیلتر حساسیت (نتایج محدود).
	•	Revoke فوری و رد دسترسی کش‌شده (≤30s).

⸻

نکات اجرا برای بازار ایران
	•	درگاه OTP/SMS داخلی (Kavenegar/…) برای ورود کاربر (اختیاری و توصیه‌شده).
	•	هاستینگ داخل کشور + CDN داخلی برای UI.
	•	طراحی «Data Processing Agreement» برای شرکت‌ها (قابل امضا) و لاگ شفاف دسترسی.

⸻
