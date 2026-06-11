import pandas as pd


def filter_to_work_trips(df: pd.DataFrame) -> pd.DataFrame:
    """Scale trip counts to work-purpose trips only."""
    if "purpose_Work" not in df.columns:
        raise ValueError("DataFrame must include a purpose_Work column")

    filtered = df.copy()
    work_fraction = filtered["purpose_Work"].fillna(0) / 100.0
    filtered["total_trips"] = filtered["total_trips"] * work_fraction
    return filtered
