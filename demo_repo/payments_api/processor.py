"""
Payment processing module for DocSentinel demo.
"""


# In charge_customer() — rename: amount → amount_usd
# Change charge_customer — rename parameter AND change return structure
def charge_customer(customer_id: str, amount_usd: float, currency: str = "USD", payment_method: str = "card") -> dict:
    """
    Charge a customer for a given amount.

    Args:
        customer_id: Unique customer identifier.
        amount_usd: Amount to charge in the given currency.
        currency: Currency code (default: USD).
        payment_method: Payment method to use (default: card).

    Returns:
        dict with keys: transaction_id, status, amount_usd, currency, payment_method, fee.
    """
    return {
        "transaction_id": f"txn_{customer_id}_001",
        "status": "success",
        "amount_usd": amount_usd,
        "currency": currency,
        "payment_method": payment_method,
        "fee": round(amount_usd * 0.02, 2),
    }

def refund_transaction(transaction_id: str, reason: str = "customer_request") -> dict:
    """
    Refund a previously completed transaction.

    Args:
        transaction_id: ID of transaction to refund.
        reason: Reason for refund (default: customer_request).

    Returns:
        dict with keys: refund_id, status, transaction_id.
    """
    return {
        "refund_id": f"ref_{transaction_id}",
        "status": "refunded",
        "transaction_id": transaction_id,
    }


def get_customer_balance(customer_id: str, account_type: str = "primary") -> dict:
    """
    Get current balance for a customer account.

    Args:
        customer_id: Unique customer identifier.
        account_type: Account type to query (default: primary).

    Returns:
        dict with keys: customer_id, balance, account_type, currency.
    """
    return {
        "customer_id": customer_id,
        "balance": 1000.00,
        "account_type": account_type,
        "currency": "USD",
    }
