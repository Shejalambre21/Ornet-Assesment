"""
Task 1: Python Code Correction & Modular Error Handling
Company: ORNET Technologies Pvt. Ltd.
Assessment: AI Developer - Practical Assessment

This script reads all product records from 'sample_products_all_cases.json'
(which contains all edge cases and correct data), validates each record using
modular helper functions, and returns/prints ONLY the highest-priced valid product.
"""

import json
import os



# Modular Helper Functions (Requirement Handling)


def is_list_empty(product_list):
    """Requirement 3: Checks whether the product list is empty or invalid."""
    if product_list is None or not isinstance(product_list, list) or len(product_list) == 0:
        return True
    return False


def is_valid_price(price):
    """
    Requirement 4: Validates the product price.
    Must be present (not None), numeric (int or float, not bool), and non-negative (>= 0).
    """
    if price is None:
        return False
    if isinstance(price, bool):
        return False
    if not isinstance(price, (int, float)):
        return False
    if price < 0:
        return False
    return True


def is_valid_product_entry(item):
    """Validates that a product item is a proper dictionary with a non-empty name."""
    if item is None or not isinstance(item, dict):
        return False
    if "name" not in item:
        return False
    name_value = item["name"]
    if not isinstance(name_value, str) or len(name_value.strip()) == 0:
        return False
    return True


def find_highest_priced_product(products):
    """
    Requirements 1 & 2: Finds and returns the name and price of the highest-priced valid product.
    Returns: (name, price) tuple or (None, None) if no valid product is found.
    """
    if is_list_empty(products):
        return None, None

    highest_price = -1.0
    highest_product_name = None

    for item in products:
        # Validate structure and name
        if not is_valid_product_entry(item):
            continue

        # Validate price existence
        if "price" not in item:
            continue

        item_price = item["price"]

        # Validate price validity (numeric & non-negative)
        if not is_valid_price(item_price):
            continue

        # Compare manually to find the highest
        if item_price > highest_price:
            highest_price = item_price
            highest_product_name = item["name"]

    if highest_product_name is None:
        return None, None

    return highest_product_name, highest_price


def load_products_from_json(filename="sample_products_all_cases.json"):
    """Reads all product records from the JSON file."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(script_dir, filename)

    if not os.path.exists(file_path):
        # Fallback path if run from different working directory
        file_path = filename

    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


# Main Execution: Reads JSON and Outputs ONLY the Highest Price Product
if __name__ == "__main__":
    # 1. Read all records from the JSON file
    products_data = load_products_from_json("sample_products_all_cases.json")

    # 2. Find the highest-priced valid product
    name, price = find_highest_priced_product(products_data)

    # 3. Output ONLY the highest price product
    print(f"Name  : {name}")
    print(f"Price : {price}")