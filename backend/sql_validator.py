import re


FORBIDDEN_KEYWORDS = [
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "TRUNCATE",
    "CREATE",
    "GRANT",
    "REVOKE",
]


def validate_sql(sql: str):
    sql = sql.strip()

    # Remove markdown code fences if the LLM returns them
    sql = re.sub(r"```sql", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"```", "", sql)
    sql = sql.strip()

    # Must start with SELECT
    if not sql.upper().startswith("SELECT"):
        return False, "Only SELECT queries are allowed."

    # Block dangerous SQL keywords
    for keyword in FORBIDDEN_KEYWORDS:
        pattern = rf"\b{keyword}\b"

        if re.search(pattern, sql, re.IGNORECASE):
            return False, f"Forbidden SQL keyword: {keyword}"

    # Must use our QueryMind table
    if "QUERYMIND.ORDERS" not in sql.upper():
        return False, "Query must use QUERYMIND.ORDERS."

    return True, sql