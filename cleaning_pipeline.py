"""Reusable cleaning pipeline for the mobile-money agent network extract.

Usage
-----
    import pandas as pd
    from cleaning_pipeline import audit_agent_data, clean_agent_data

    txns = pd.read_csv("agent_transactions.csv", dtype=str, keep_default_na=False)
    agents = pd.read_csv("agents.csv")
    clean, log = clean_agent_data(txns, agents)
"""
import numpy as np
import pandas as pd

VALID_TYPES = {"deposit": "Deposit", "withdrawal": "Withdrawal"}
MISSING_TOKENS = {"", "n/a", "na", "nan", "null", "none", "-"}
UNKNOWN_COUNTY = "Unknown"


def _to_amount(series):
    """Strip text, treat missing tokens as NaN, convert to numeric (invalid -> NaN)."""
    s = series.astype("string").str.strip().str.replace(",", "", regex=False)
    s = s.mask(s.str.lower().isin(MISSING_TOKENS))
    return pd.to_numeric(s, errors="coerce")


def _to_date(series):
    """Parse ISO dates and the YYYY/MM/DD variant into datetimes (invalid -> NaT)."""
    s = series.astype("string").str.strip().str.replace("/", "-", regex=False)
    return pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")


def _iqr_fences(values, k=1.5):
    q1, q3 = values.quantile([0.25, 0.75])
    iqr = q3 - q1
    return q1 - k * iqr, q3 + k * iqr


def audit_agent_data(txns, agents):
    """Return a data-quality audit table (issue, dimension, column, rows_affected).

    The audit works on the RAW frames and changes nothing.
    """
    t = txns.copy()
    rows = []

    def add(issue, dimension, column, n):
        rows.append({"issue": issue, "dimension": dimension,
                     "column": column, "rows_affected": int(n)})

    # Completeness
    raw_amt = t["amount"].astype("string").str.strip()
    missing_amt = raw_amt.isna() | raw_amt.str.lower().isin(MISSING_TOKENS)
    add("Amount missing (blank/NaN) or literal 'N/A'", "Completeness", "amount", missing_amt.sum())

    # Validity: non-numeric text that is not a recognised missing token
    parsed = _to_amount(t["amount"])
    add("Amount present but not numeric", "Validity", "amount",
        (parsed.isna() & ~missing_amt).sum())
    add("Amount zero or negative", "Validity", "amount", (parsed <= 0).sum())
    dates = _to_date(t["txn_date"])
    add("txn_date not parseable as a date", "Validity", "txn_date", dates.isna().sum())

    # Consistency
    add("Non-ISO date format (YYYY/MM/DD)", "Consistency", "txn_date",
        t["txn_date"].astype("string").str.contains("/", na=False).sum())
    tt = t["txn_type"].astype("string")
    add("txn_type has inconsistent case/whitespace", "Consistency", "txn_type",
        (~tt.isin(["Deposit", "Withdrawal"])).sum())
    add("txn_type not mappable to Deposit/Withdrawal", "Validity", "txn_type",
        (~tt.str.strip().str.lower().isin(VALID_TYPES)).sum())

    # Uniqueness
    add("Fully identical duplicate rows (extra copies)", "Uniqueness", "all columns",
        t.duplicated().sum())
    add("Repeated txn_id (extra copies, incl. conflicting copies)", "Uniqueness", "txn_id",
        t["txn_id"].duplicated().sum())

    # Integrity / accuracy
    add("agent_id not in agent register", "Validity", "agent_id",
        (~t["agent_id"].isin(agents["agent_id"])).sum())
    low, high = _iqr_fences(parsed.dropna())
    add(f"Amount outside IQR fences ({low:,.0f} to {high:,.0f})", "Accuracy", "amount",
        ((parsed < low) | (parsed > high)).sum())
    top = parsed.dropna().mode()
    if len(top):
        add(f"Repeated round-figure amount ({top.iloc[0]:,.0f}) suspected placeholder",
            "Accuracy", "amount", (parsed == top.iloc[0]).sum())

    # Timeliness: transactions before the agent was onboarded
    m = t.assign(_d=dates).merge(agents[["agent_id", "onboarded"]], on="agent_id", how="left")
    add("Transaction dated before agent onboarding", "Timeliness", "txn_date",
        (m["_d"] < pd.to_datetime(m["onboarded"])).sum())

    return pd.DataFrame(rows)


def clean_agent_data(txns, agents):
    """Clean the agent transaction extract and merge it with the agent register.

    Rules (all applied in code; nothing is edited by hand):
      1. Trim whitespace in text columns.
      2. Standardise txn_type to exactly 'Deposit' / 'Withdrawal'.
      3. Convert amount to numeric (text such as 'N/A' and blanks become NaN) and
         txn_date to datetime (handles YYYY-MM-DD and YYYY/MM/DD).
      4. Remove duplicate transactions on txn_id. Where copies conflict, the copy
         whose agent_id exists in the register is kept; otherwise the first copy.
      5. Missing/invalid amounts are imputed with the median valid amount for the
         same txn_type and flagged (amount_imputed). Imputed values are placeholders:
         they are excluded from value totals in the summaries.
      6. Flag outliers with the 1.5 x IQR rule (is_outlier). Outliers are kept.
      7. LEFT-join the agent register (many txns -> one agent); unknown agents are
         kept, labelled county='Unknown' and flagged (unknown_agent).

    Parameters
    ----------
    txns : pd.DataFrame
        Raw transactions (txn_id, agent_id, txn_type, amount, txn_date).
    agents : pd.DataFrame
        Agent register (agent_id, county, onboarded).

    Returns
    -------
    (clean_df, log) : tuple[pd.DataFrame, pd.DataFrame]
        clean_df: cleaned, merged transactions with flag columns.
        log: one row per cleaning step (step, rule, rows_before, rows_after, rows_affected).
    """
    log = []

    def record(step, rule, before, after, affected):
        log.append({"step": step, "rule": rule, "rows_before": int(before),
                    "rows_after": int(after), "rows_affected": int(affected)})

    df = txns.copy()
    agents = agents.copy()
    n0 = len(df)

    # 1. whitespace
    for col in ["txn_id", "agent_id", "txn_type"]:
        df[col] = df[col].astype("string").str.strip()
    agents["agent_id"] = agents["agent_id"].astype("string").str.strip()
    record(1, "Trim whitespace in txn_id, agent_id, txn_type", n0, len(df), 0)

    # 2. txn_type
    mapped = df["txn_type"].str.lower().map(VALID_TYPES)
    changed = (mapped != df["txn_type"]).sum()
    df["txn_type"] = mapped
    record(2, "Standardise txn_type to Deposit/Withdrawal (invalid -> NaN)",
           n0, len(df), changed)

    # 3. types
    raw_amount = df["amount"]
    df["amount"] = _to_amount(raw_amount)
    amount_bad = df["amount"].isna() | (df["amount"] <= 0)
    df.loc[df["amount"] <= 0, "amount"] = np.nan
    record(3, "Convert amount to numeric (blank, 'N/A', text, <=0 -> NaN)",
           n0, len(df), amount_bad.sum())
    non_iso = df["txn_date"].astype("string").str.contains("/", na=False).sum()
    df["txn_date"] = _to_date(df["txn_date"])
    record(3, "Parse txn_date to datetime (YYYY/MM/DD and YYYY-MM-DD)",
           n0, len(df), non_iso + df["txn_date"].isna().sum())

    # 4. duplicates (agent-known copies first so a corrupted copy is the one dropped)
    known = df["agent_id"].isin(agents["agent_id"])
    exact_dups = txns.duplicated().sum()
    before = len(df)
    df = (df.assign(_known=known)
            .sort_values("_known", ascending=False, kind="stable")
            .drop_duplicates(subset="txn_id", keep="first")
            .sort_index()
            .drop(columns="_known"))
    record(4, f"Drop duplicate txn_id (of which {exact_dups} were identical rows)",
           before, len(df), before - len(df))

    # 5. imputation with flag
    df["amount_imputed"] = df["amount"].isna()
    lo, hi = _iqr_fences(df["amount"].dropna())
    typical = df["amount"].where(df["amount"].between(lo, hi))
    medians = typical.groupby(df["txn_type"]).median()
    fill = df["txn_type"].map(medians).fillna(typical.median())
    df["amount"] = df["amount"].fillna(fill)
    record(5, "Impute missing/invalid amount with in-range median by txn_type; "
              "flag amount_imputed", len(df), len(df), df["amount_imputed"].sum())

    # 6. outliers (IQR on genuinely observed amounts only)
    observed = df.loc[~df["amount_imputed"], "amount"]
    low, high = _iqr_fences(observed)
    df["is_outlier"] = (~df["amount_imputed"]) & ((df["amount"] < low) | (df["amount"] > high))
    record(6, f"Flag outliers outside IQR fences [{low:,.0f}, {high:,.0f}] (kept, not removed)",
           len(df), len(df), df["is_outlier"].sum())

    # 7. merge
    before = len(df)
    df = df.merge(agents[["agent_id", "county", "onboarded"]],
                  on="agent_id", how="left", validate="m:1", indicator=True)
    df["unknown_agent"] = df["_merge"].eq("left_only")
    df = df.drop(columns="_merge")
    df["county"] = df["county"].fillna(UNKNOWN_COUNTY)
    record(7, "Left-join agent register on agent_id (unknown agents kept as 'Unknown')",
           before, len(df), df["unknown_agent"].sum())

    df["txn_date"] = pd.to_datetime(df["txn_date"])
    df = df.sort_values("txn_id").reset_index(drop=True)
    cols = ["txn_id", "agent_id", "county", "onboarded", "txn_type", "amount",
            "txn_date", "amount_imputed", "is_outlier", "unknown_agent"]
    return df[cols], pd.DataFrame(log)
