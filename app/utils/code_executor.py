import re
import pandas as pd
from typing import Any, Dict


FORBIDDEN_PATTERNS = [
    r"\bimport\b",
    r"\bos\b",
    r"\bsys\b",
    r"\bsubprocess\b",
    r"\beval\b",
    r"\bexec\b",
    r"\bopen\b",
    r"\b__\b",
]


class UnsafeCodeError(Exception):
    pass


class CodeExecutor:

    @staticmethod
    def validate_code(code: str):
        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, code):
                raise UnsafeCodeError(f"Forbidden operation detected: {pattern}")

    @staticmethod
    def execute(code: str, df: pd.DataFrame) -> Dict[str, Any]:

        # Auto-fix missing assignment BEFORE validation
        if "result" not in code:
            code = f"result = {code.strip()}"

        # Validate after fixing
        CodeExecutor.validate_code(code)

        safe_globals = {
            "__builtins__": {},
        }

        safe_locals = {
            "df": df,
            "pd": pd,
        }

        exec(code, safe_globals, safe_locals)

        if "result" not in safe_locals:
            raise UnsafeCodeError("Code must assign output to variable 'result'")

        result = safe_locals["result"]

        if isinstance(result, pd.Series):
            result = result.to_frame().reset_index()

        if isinstance(result, pd.DataFrame):
            return {
                "columns": list(result.columns),
                "data": result.to_dict(orient="records"),
            }

        return {
            "columns": ["value"],
            "data": [{"value": result}],
        }