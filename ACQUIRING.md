# BookRAG Corpus Acquisition

Automated, **legal**, API-driven acquisition of a multimodal finance/business/wealth
corpus. Fills `./corpus/<source>/` and records every doc in `./manifest.json`
(idempotent + resumable — rerun any time to top up).

## Quick start

```bash
pip install -r requirements-acquire.txt
export CONTACT_EMAIL="royalekiller786@gmail.com"   # required by SEC etiquette
python3 acquire.py                 # pull toward default quotas (~200 docs)
python3 acquire.py --list          # show current tallies
python3 acquire.py --only sec_edgar
python3 acquire.py --quota arxiv_qfin=60 --quota worldbank=60
```

## Sources (all free / open / official APIs)

| Source           | What                                   | Format | Multimodal value                       |
|------------------|----------------------------------------|--------|----------------------------------------|
| `sec_edgar`      | 10-K / 20-F annual filings             | HTML   | Dense financial statement **tables**   |
| `worldbank`      | World Bank open economic reports       | PDF    | Charts, data tables, infographics      |
| `arxiv_qfin`     | Quant-finance / economics papers       | PDF    | Equations, plots, results tables       |
| `public_domain`  | Internet Archive finance/econ texts    | PDF    | **Scanned** image pages (OCR path)     |
| `annual_reports` | annualreports.com investor reports     | PDF    | Glossy charts, photos, multi-column    |
| `open_books`     | Open-license / rights-cleared books    | PDF    | Long-form prose (seed-file driven)     |

Default quotas sum to 200 (`DEFAULT_QUOTAS` in `acquire.py`). The four API sources
(edgar/worldbank/arxiv/public_domain) are the reliable backbone; `annual_reports`
scrapes and `open_books` is seed-driven.

### Seed files (things you add yourself)
- `downloaders/annual_reports_seed.txt` — direct annual-report PDF URLs.
- `downloaders/open_books_seed.txt` — open-license textbooks or **book PDFs you hold
  rights to**. This is the lawful replacement for scraping copyrighted ebooks —
  keeping the corpus sellable and CV-safe.

## Design notes
- Dedup by URL **and** by SHA-256 content hash (no dup files even across sources).
- Per-source rate limiting; honest `User-Agent` with contact email.
- One bad document never kills a run; one bad source never kills the batch.
- Manifest writes are atomic (temp file + rename).

## Next phase — multimodal ingestion (currently paused)
The existing `ingest.py` assumes clean copyable text (`pypdf`). To use this corpus it
needs upgrading:
- **HTML** (SEC filings): an HTML/table-aware loader (e.g. `unstructured`, `trafilatura`).
- **Scanned PDFs** (public_domain): OCR (e.g. `ocrmypdf`, `pytesseract`, or a vision model).
- **Layout/tables/charts** (reports): a layout-aware parser (e.g. `docling`, `unstructured`,
  or PyMuPDF + table extraction). Store richer chunk metadata (page, element type).
