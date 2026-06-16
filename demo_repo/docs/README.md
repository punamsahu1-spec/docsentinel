# Payments API Documentation

## Overview

The Payments API provides functions for processing customer transactions on the platform.

---

## charge_customer

Charges a customer account for a specified amount.

**Parameters:**
- `customer_id` (str): Unique customer identifier.
- `amount` (float): Amount to charge in USD.
- `currency` (str): Currency code. Default: `USD`.

**Returns:** `dict` with keys: `transaction_id`, `status`, `amount`, `currency`.

**Example:**
```python
result = charge_customer("cust_123", 49.99)
```

---

## refund_transaction

Refunds a previously completed transaction.

**Parameters:**
- `transaction_id` (str): ID of the transaction to refund.
- `reason` (str): Reason for refund. Default: `customer_request`.

**Returns:** `dict` with keys: `refund_id`, `status`, `transaction_id`.

**Example:**
```python
result = refund_transaction("txn_cust_123_001")
```

---

## get_customer_balance

Returns the current balance for a customer account.

**Parameters:**
- `customer_id` (str): Unique customer identifier.
- `account_type` (str): Account type to query. Default: `primary`.

**Returns:** `dict` with keys: `customer_id`, `balance`, `account_type`, `currency`.

**Example:**
```python
result = get_customer_balance("cust_123")
```
