# Week 3: Duka Electronics and Mobile Money Agent Network

Two analytics engagements in one repository.

## Engagement 2: Mobile money agent network
Audit, clean, merge and summarise a deliberately unreliable transaction extract.

- `cleaning_pipeline.py` holds `audit_agent_data()` and `clean_agent_data(txns, agents)` which returns `(clean_df, log)`.
- `agent_cleanup.ipynb` calls the pipeline and shows the audit table, post-merge validation, county summary, weekly pivot and the Data Quality Report.
- `outputs/agent_transactions_clean.csv` is the cleaned, merged data.

**Before and after row count:** 612 raw rows, 600 clean rows (12 duplicate `txn_id`s removed). 20 amounts imputed and flagged, 40 IQR outliers flagged (5 are KES 250,000 placeholders), 7 transactions with unknown agent `AG099` kept as county `Unknown`.

## Engagement 1: Duka Electronics
Explore H1 2026 sales (1,000 orders, seed 2026) and answer the Head of Sales' questions.

- `duka_sales_exploration.ipynb`: inspection, derived columns, Tasks 3-7, spreadsheet check and the Executive Summary.
- `excel/duka_branch_summary.xlsx`: SUMIFS branch ranking, XLOOKUP region column and a PivotTable of revenue by branch and channel. Totals match pandas (KES 71,792,500).
- `outputs/premium_online_coast_capital.csv`: 83 Premium online orders from Nairobi and Mombasa (KES 10,218,000).

### Executive Summary
- Duka Electronics booked **KES 71.8 million** from **1,000 orders** between 1 January and 29 June 2026, an average of **KES 71,793** per order.
- Nairobi is the strongest branch with **KES 26.1 million (36.4%)** of revenue from **376 orders**, almost three times the smallest branch, Eldoret, at KES 8.8 million (12.3%).
- Laptops earn **KES 41.5 million (57.9%)** of revenue, yet tablets sell the most units (**691 versus 639** for laptops) because they cost less than half as much.
- Monthly revenue peaked in April at **KES 13.52 million** and was lowest in June at **KES 10.90 million**, a gap of **24.0%**, so the half-year ended on a weak note.
- Online orders (**320 orders, KES 22.8 million, 31.7%** of revenue) are worth as much per order as in-store sales (**KES 71,207 versus 70,759**), and Premium online orders in Nairobi and Mombasa alone delivered **83 orders and KES 10.2 million**, which supports investing in the channel.

## How to run
```bash
pip install -r requirements.txt
python generate_data.py          # writes the raw CSVs (not committed)
jupyter nbconvert --to notebook --execute --inplace duka_sales_exploration.ipynb
jupyter nbconvert --to notebook --execute --inplace agent_cleanup.ipynb
```
Restart the kernel and run top to bottom before committing so all outputs are visible.
