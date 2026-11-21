"""The application works in one currency: the Philippine peso (PHP, symbol ₱).

All amounts (rates, the cost estimate, the budget) are pesos. There is no conversion and no second currency;
the database refuses any other currency code (migration 0007). Change it here and in `frontend/src/money.ts`
if the company ever needs a different one.
"""

CURRENCY = "PHP"
SYMBOL = "₱"
NAME = "Philippine peso"
EXCEL_FORMAT = '"₱"#,##0'  # how Excel shows a peso amount
