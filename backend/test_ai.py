from ollama import chat

response = chat(
    model="qwen2.5-coder:7b-instruct",
    messages=[
        {
            "role": "user",
            "content": """
Write ONLY a SQL query.

Table:
QUERYMIND.ORDERS

Columns:
ORDER_ID
ORDER_DATE
REGION
CATEGORY
QUANTITY
UNIT_PRICE

Question:
Which region generated the most revenue?
"""
        }
    ]
)

print(response.message.content)