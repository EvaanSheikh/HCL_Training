import re
from typing import Any
import pandas as pd


ID_PATTERNS = re.compile(
    r"^(id|uuid|guid|key|index|_id)$|(_id$|_uuid$|_key$|_guid$|id_|^id_)",
    re.IGNORECASE,
)

DATE_PATTERNS = re.compile(
    r"(date|timestamp|time|datetime|created_at|updated_at|recorded_at|order_date|orderdate|invoice_date|invoicedate|transaction_date|transactiondate|year|month|day)",
    re.IGNORECASE,
)

FINANCIAL_PATTERNS = re.compile(
    r"(price|revenue|cost|sales|profit|fee|salary|wage|spend|budget|amount|margin|shipping_cost|shippingcost|unit_price|property_price)",
    re.IGNORECASE,
)

RATE_OR_RATIO_PATTERNS = re.compile(
    r"(percentage|percent|ratio|rate|discount|pct|share)",
    re.IGNORECASE,
)

WEATHER_PATTERNS = re.compile(
    r"(temperature|temp|temp_c|temp_f|humidity|rh|pressure|wind_speed|windspeed|precipitation|rainfall|cloud_cover)",
    re.IGNORECASE,
)

ACADEMIC_PATTERNS = re.compile(
    r"(marks|score|grade|attendance|gpa|credits|exam_score|test_score)",
    re.IGNORECASE,
)

REAL_ESTATE_PATTERNS = re.compile(
    r"(area|sqft|square_feet|bedrooms|bathrooms|rooms|property_price|rent|built_up)",
    re.IGNORECASE,
)

DEMOGRAPHIC_PATTERNS = re.compile(
    r"(population|inhabitants|age|headcount|citizens|residents)",
    re.IGNORECASE,
)


def is_identifier_column(col_name: str, unique_ratio: float | None = None) -> bool:
    """Determine whether a column represents an identifier/key rather than an analytical measure."""
    col_clean = str(col_name).strip().lower()
    if ID_PATTERNS.search(col_clean):
        return True
    if unique_ratio is not None and unique_ratio > 0.99 and not DATE_PATTERNS.search(col_clean):
        # Likely a unique primary key / record ID
        return True
    return False


def is_temporal_column(col_name: str, dtype_str: str = "") -> bool:
    """Determine whether a column represents a date, timestamp, or temporal dimension."""
    dtype_lower = str(dtype_str).lower()
    if any(token in dtype_lower for token in ["datetime", "timestamp", "date", "period"]):
        return True
    return bool(DATE_PATTERNS.search(str(col_name).strip().lower()))


def detect_semantic_category(col_name: str) -> str:
    """Hypothesize semantic domain category for a column without treating it as interchangeable."""
    name_clean = str(col_name).strip().lower()
    if WEATHER_PATTERNS.search(name_clean):
        return "weather"
    if ACADEMIC_PATTERNS.search(name_clean):
        return "academic"
    if REAL_ESTATE_PATTERNS.search(name_clean):
        return "real_estate"
    if FINANCIAL_PATTERNS.search(name_clean):
        return "financial"
    if DEMOGRAPHIC_PATTERNS.search(name_clean):
        return "demographic"
    return "general"


def is_monetary_metric(col_name: str) -> bool:
    """Check if a numeric metric represents a financial/monetary amount conceptually."""
    name_clean = str(col_name).strip().lower()
    if RATE_OR_RATIO_PATTERNS.search(name_clean):
        return False
    return bool(FINANCIAL_PATTERNS.search(name_clean))


# Backward compatibility alias
is_currency_metric = is_monetary_metric


CURRENCY_MAP = {
    "USD": ("USD", "$"),
    "EUR": ("EUR", "€"),
    "GBP": ("GBP", "£"),
    "INR": ("INR", "₹"),
    "JPY": ("JPY", "¥"),
}

# Regex patterns for explicit column prefixes, suffixes, and bracketed symbols
CURRENCY_HEADER_PATTERNS = [
    (re.compile(r"(\b|_|\()(usd|\$|dollar|dollars)(\b|_|\))", re.IGNORECASE), ("USD", "$")),
    (re.compile(r"(\b|_|\()(eur|€|euro|euros)(\b|_|\))", re.IGNORECASE), ("EUR", "€")),
    (re.compile(r"(\b|_|\()(gbp|£|pound|pounds)(\b|_|\))", re.IGNORECASE), ("GBP", "£")),
    (re.compile(r"(\b|_|\()(inr|₹|rs|rupee|rupees)(\b|_|\))", re.IGNORECASE), ("INR", "₹")),
    (re.compile(r"(\b|_|\()(jpy|¥|yen)(\b|_|\))", re.IGNORECASE), ("JPY", "¥")),
]


def detect_currency_symbol(
    col_name: str,
    dataset_metadata: dict[str, Any] | None = None,
) -> tuple[str | None, str | None]:
    """
    Detect explicit currency metadata for a column.
    Returns (currency_code, currency_symbol) or (None, None).
    Never assumes USD simply because a column represents money.
    """
    if not is_monetary_metric(col_name):
        return None, None

    # 1. Explicit dataset-level metadata or profile configuration
    if dataset_metadata:
        cfg_curr = (
            dataset_metadata.get("currency")
            or dataset_metadata.get("currency_code")
            or dataset_metadata.get("default_currency")
        )
        if cfg_curr:
            cfg_upper = str(cfg_curr).strip().upper()
            if cfg_upper in CURRENCY_MAP:
                return CURRENCY_MAP[cfg_upper]

    # 2. Explicit column naming patterns (suffixes, prefixes, or bracketed symbols)
    name_str = str(col_name).strip()
    for pattern, currency_info in CURRENCY_HEADER_PATTERNS:
        if pattern.search(name_str):
            return currency_info

    # 3. Currency is unstated / unknown -> return None, None
    return None, None


def profile_schema_semantics(
    column_names: list[str],
    dtypes: dict[str, str] | None = None,
    numeric_columns: list[str] | None = None,
) -> dict[str, Any]:
    """
    Profile the columns of a dataset to categorize them into:
    - temporal_columns
    - eligible_numeric_metrics (excluding identifiers)
    - eligible_categorical_dimensions (excluding high-cardinality IDs)
    - identifier_columns
    - column_semantics: map of col -> semantic metadata
    """
    dtypes = dtypes or {}
    semantics: dict[str, dict[str, Any]] = {}
    temporal_cols = []
    numeric_metrics = []
    categorical_dims = []
    identifier_cols = []

    for col in column_names:
        col_dtype = str(dtypes.get(col, "")).lower()
        is_num = (
            col in (numeric_columns or [])
            or any(t in col_dtype for t in ["int", "float", "double", "number", "numeric"])
        )
        is_temp = is_temporal_column(col, col_dtype)
        is_id = is_identifier_column(col)
        cat = detect_semantic_category(col)
        is_monetary = is_monetary_metric(col) if is_num else False
        curr_code, curr_sym = detect_currency_symbol(col) if is_num else (None, None)

        semantics[col] = {
            "name": col,
            "dtype": col_dtype,
            "is_numeric": is_num,
            "is_temporal": is_temp,
            "is_identifier": is_id,
            "semantic_category": cat,
            "is_currency": is_monetary,
            "is_monetary": is_monetary,
            "currency_code": curr_code,
            "currency_symbol": curr_sym,
        }

        if is_id:
            identifier_cols.append(col)
        elif is_temp:
            temporal_cols.append(col)
        elif is_num:
            numeric_metrics.append(col)
        else:
            categorical_dims.append(col)

    # In case no numeric_metrics were found because all had generic types,
    # fallback to any non-id column
    return {
        "column_names": column_names,
        "temporal_columns": temporal_cols,
        "eligible_numeric_metrics": numeric_metrics,
        "eligible_categorical_dimensions": categorical_dims,
        "identifier_columns": identifier_cols,
        "column_semantics": semantics,
    }


def find_best_date_column(available_cols: list[str], dtypes: dict[str, str] | None = None) -> str | None:
    """Find the best date/time column among available columns."""
    dtypes = dtypes or {}
    # First check explicit datetime dtypes
    for col in available_cols:
        col_dtype = str(dtypes.get(col, "")).lower()
        if "datetime" in col_dtype or "timestamp" in col_dtype:
            return col

    # Priority list of exact matches
    priority = [
        "timestamp", "date", "orderdate", "order_date", "invoicedate",
        "invoice_date", "transactiondate", "transaction_date", "created_at",
        "recorded_at", "time"
    ]
    col_map = {c.lower(): c for c in available_cols}
    for p in priority:
        if p in col_map:
            return col_map[p]

    # Substring search
    for col in available_cols:
        col_lower = col.lower()
        if "date" in col_lower or "timestamp" in col_lower or "time" in col_lower:
            return col

    return None


def match_query_column(query: str, available_cols: list[str], candidates: list[str] | None = None) -> str | None:
    """
    Match query text to an actual available column.
    Checks exact word matches first, then multi-word, then substring.
    Never returns a column that does not exist in available_cols.
    """
    search_space = candidates if candidates is not None else available_cols
    if not search_space:
        return None

    query_lower = query.lower()
    tokens = set(re.findall(r"\b\w+\b", query_lower))

    # Exact token match
    for col in search_space:
        col_clean = col.lower().replace("_", " ")
        if col.lower() in tokens or col_clean in query_lower:
            return col

    # Check semantic patterns
    for col in search_space:
        col_lower = col.lower()
        # Weather
        if "temp" in query_lower and ("temp" in col_lower or "temperature" in col_lower):
            return col
        if "humid" in query_lower and "humid" in col_lower:
            return col
        # Academic
        if "mark" in query_lower and "mark" in col_lower:
            return col
        if "score" in query_lower and "score" in col_lower:
            return col
        if "grade" in query_lower and "grade" in col_lower:
            return col
        if "attendance" in query_lower and "attend" in col_lower:
            return col
        # Real estate
        if "price" in query_lower and "price" in col_lower:
            return col
        if "area" in query_lower and ("area" in col_lower or "sqft" in col_lower):
            return col
        if "bedroom" in query_lower and "bed" in col_lower:
            return col
        # Retail
        if "revenue" in query_lower and "revenue" in col_lower:
            return col
        if "profit" in query_lower and "profit" in col_lower:
            return col
        if "sales" in query_lower and "sales" in col_lower:
            return col

    return None
