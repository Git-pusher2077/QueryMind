import pyexasol

# Connect to Exasol
connection = pyexasol.connect(
    dsn="localhost/nocertcheck:9563",
    user="sys",
    password="exasol",
    encryption=True
)

# Run an analytical query
query = """
SELECT
    REGION,
    SUM(QUANTITY * UNIT_PRICE) AS REVENUE
FROM QUERYMIND.ORDERS
GROUP BY REGION
ORDER BY REVENUE DESC
"""

result = connection.execute(query).fetchall()

print("\nRevenue by region:")
print("-------------------")

for region, revenue in result:
    print(f"{region}: ₹{float(revenue):,.2f}")

connection.close()