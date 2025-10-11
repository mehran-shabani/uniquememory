# SDK جاوااسکریپت UniqueMemory

## نصب
```bash
npm install @uniquememory/sdk@1.0.0
```

## نمونه استفاده
```javascript
import { UniqueMemoryClient } from '@uniquememory/sdk';

const client = new UniqueMemoryClient({
  clientId: process.env.CLIENT_ID,
  clientSecret: process.env.CLIENT_SECRET,
});

const response = await client.search({
  companyId: 'alpha-tech',
  query: 'chargeback investigation'
});

console.log(response.latencyMs, response.hits.length);
```

## نکات نسخه GA
- پشتیبانی از Token Rotation خودکار.
- سازگاری با محیط‌های Node.js 20 و مرورگر با bundler.
