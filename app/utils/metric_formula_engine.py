
def detect_metric_formula(question: str, df):

    q = question.lower()

    # Production efficiency
    if "efficiency" in q:
        if "Actual_Qty" in df.columns and "Planned_Qty" in df.columns:
            df["Efficiency"] = df["Actual_Qty"] / df["Planned_Qty"]
            return "Efficiency"

    # Scrap rate
    if "scrap rate" in q or "scrap %" in q:
        if "Scrap_Qty" in df.columns and "Actual_Qty" in df.columns:
            df["Scrap_Rate"] = df["Scrap_Qty"] / df["Actual_Qty"]
            return "Scrap_Rate"

    # Rework rate
    if "rework rate" in q:
        if "Rework_Qty" in df.columns and "Actual_Qty" in df.columns:
            df["Rework_Rate"] = df["Rework_Qty"] / df["Actual_Qty"]
            return "Rework_Rate"

    # Cost variance
    if "cost variance" in q or "cost difference" in q:
        if "Actual_Cost" in df.columns and "Planned_Cost" in df.columns:
            df["Cost_Variance"] = df["Actual_Cost"] - df["Planned_Cost"]
            return "Cost_Variance"

    # Yield
    if "yield" in q:
        if "Actual_Qty" in df.columns and "Scrap_Qty" in df.columns:
            df["Yield"] = (df["Actual_Qty"] - df["Scrap_Qty"]) / df["Actual_Qty"]
            return "Yield"

    return None
