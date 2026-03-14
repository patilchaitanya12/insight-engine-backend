import pandas as pd

def build_schema_context(df: pd.DataFrame) -> str:
    """
    Build a concise schema context string from a DataFrame.
    Example output: "Columns: age (int), name (str), salary (float)"
    """
    schema_lines = []
    
    for col in df.columns:
        dtype = str(df[col].dtype)
        
        example = (df[col].dropna().astype(str).unique()[:3])
        
        example_str = ", ".join(str(x) for x in example)
        
        schema_lines.append(f"{col} ({dtype}): {example_str}")
    
    return "\n".join(schema_lines)
