# Hapag-Lloyd Freight Quote Scraper

Automates freight quote retrieval from [hapag-lloyd.com](https://www.hapag-lloyd.com) using Playwright. Logs in, fills the quote form, captures results, and saves them to JSON.

---

## Requirements

- Python 3.9+
- pip

---

## Setup

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Install Playwright browsers

```bash
playwright install chromium
```

### 3. Configure credentials

Copy or edit the `.env` file in the project root:

```env
HL_EMAIL=your-email@example.com
HL_PASSWORD=your-password
```

> **Never commit `.env` to version control.** It is already in `.gitignore`.

---

## Configuration

Quote parameters are set via **three methods** (higher in the list = higher priority):

| Priority | Method |
|----------|--------|
| 1 (highest) | CLI flags |
| 2 | `config.json` file |
| 3 | `.env` / environment variables |

### config.json

Edit `config.json` to set default search parameters:

```json
{
  "email": "your-email@example.com",
  "password": "your-password",
  "start_location": "NHAVA SHEVA",
  "end_location": "SINGAPORE",
  "received_at": "terminal",
  "delivered_to": "terminal",
  "valid_from": "2026-06-25",
  "container_type": "40HC",
  "container_quantity": "1",
  "weight_per_container": "20000",
  "weight_unit": "kg",
  "commodity": "FAK",
  "headless": false,
  "output_file": "hapag_lloyd_quotes.json",
  "slow_mo": 120
}
```

| Field | Description | Example values |
|-------|-------------|----------------|
| `start_location` | Origin port | `"NHAVA SHEVA"`, `"SHANGHAI"` |
| `end_location` | Destination port | `"SINGAPORE"`, `"ROTTERDAM"` |
| `received_at` | Cargo pickup mode | `"terminal"` or `"door"` |
| `delivered_to` | Cargo delivery mode | `"terminal"` or `"door"` |
| `valid_from` | Quote date | `"YYYY-MM-DD"` (empty = today) |
| `container_type` | Container size/type | `"20GP"`, `"40HC"`, `"40GP"` |
| `container_quantity` | Number of containers | `"1"` |
| `weight_per_container` | Weight per container | `"20000"` |
| `weight_unit` | Weight unit | `"kg"` or `"lb"` |
| `commodity` | Commodity code | `"FAK"` (Freight All Kinds) |
| `headless` | Run browser invisibly | `true` or `false` |
| `output_file` | Output JSON path | `"quotes.json"` |
| `slow_mo` | Delay between actions (ms) | `120` |

---

## Running

### Basic run (uses `.env` + `config.json`)

```bash
python main.py
```

### With a specific config file

```bash
python main.py --config config.json
```

### With CLI overrides

```bash
python main.py --origin "SHANGHAI" --destination "ROTTERDAM" --headless
```

### All CLI options

```
--config       Path to JSON config file
--origin       Origin port name
--destination  Destination port name
--email        Hapag-Lloyd account email
--password     Hapag-Lloyd account password
--output       Output JSON file path
--headless     Run browser in headless (invisible) mode
```

---

## Output

Results are saved to `hapag_lloyd_quotes.json` (or the path set in config/CLI).

The file contains:
- Search parameters used
- Visual data extracted from the results page
- Raw API responses captured during the session

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError: playwright` | Run `pip install -r requirements.txt` |
| Browser not found | Run `playwright install chromium` |
| Login fails | Check credentials in `.env` or `config.json` |
| No results returned | Try with `"headless": false` to watch the browser and debug form filling |
| Slow / timing errors | Increase `slow_mo` in `config.json` (e.g. `200`) |
