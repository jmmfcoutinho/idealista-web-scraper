# Bright Data Balance & Usage

## Check Balance via API

```bash
source .env && curl -s -H "Authorization: Bearer $BRIGHTDATA_API_KEY" "https://api.brightdata.com/customer/balance"
```

**Response:**
```json
{"balance":2,"credit":0,"prepayment":0,"pending_costs":0.2}
```

| Field | Description |
|-------|-------------|
| `balance` | Available balance in USD |
| `credit` | Credit balance |
| `prepayment` | Prepaid amount |
| `pending_costs` | Costs not yet billed |

## Required Environment Variable

Add to `.env`:
```
BRIGHTDATA_API_KEY=your_api_key_here
```

Get your API key from: https://brightdata.com/cp/setting/

**Note:** The API key needs "View balance" permission enabled.

## Scraping Browser Pricing

- **~$0.01-0.03 per page** (varies by site complexity and browser time)
- Idealista pages average ~$0.02-0.03 per page

## Usage Tracking

| Operation | Pages | Approx Cost |
|-----------|-------|-------------|
| Initial tests | 2 | ~$0.06 |
| Prescrape | 5 | ~$0.06 |
| **Total** | 7 | ~$0.12-0.20 |
