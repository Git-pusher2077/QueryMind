from sql_validator import validate_sql


safe_sql = """
SELECT
    REGION,
    SUM(QUANTITY * UNIT_PRICE) AS REVENUE
FROM QUERYMIND.ORDERS
GROUP BY REGION
ORDER BY REVENUE DESC
"""


dangerous_sql = """
DROP TABLE QUERYMIND.ORDERS
"""


valid, result = validate_sql(safe_sql)

print("Safe query:")
print(valid)
print(result)

print("\nDangerous query:")
valid, result = validate_sql(dangerous_sql)

print(valid)
print(result)