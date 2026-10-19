"""
Task 1: Python Code Correction & Debugging (Direct Fix)
Company: ORNET Technologies Pvt. Ltd.
Assessment: AI Developer - Practical Assessment

This script directly corrects the errors in the original function provided in the
assessment using clear, beginner-friendly manual coding techniques.

Original Function with Bugs:
---------------------------
def highest_priced_product(products):
    highest = 0
    for product in products:
        if product["price"] > highest:
            highest = product["name"]      # Bug 1: Overwrites number with string
    return highest["name"]                 # Bug 2: String subscript error; only returns name

Corrected Function:
-------------------
Tracks both the highest price (numeric) and the product name (string) separately,
and returns both the name and the price of the highest-priced product.
"""


def highest_priced_product(products):
    """
    Finds and returns the name and price of the highest-priced product.
    
    Parameters:
        products (list): A list of product dictionaries, e.g. [{"name": "...", "price": ...}]
        
    Returns:
        tuple: (highest_product_name, highest_price)
               Returns (None, None) if the list is empty.
    """
    if not products:
        return None, None

    
    highest_price = -1
    highest_product_name = None

    for product in products:
        current_price = product["price"]
        current_name = product["name"]

        if current_price > highest_price:
            highest_price = current_price
            highest_product_name = current_name

    return highest_product_name, highest_price

if __name__ == "__main__":
    products = [
        {"name": "Keyboard", "price": 1500},
        {"name": "Mouse", "price": 800},
        {"name": "Monitor", "price": 12000}
    ]

    print("=" * 60)
    print(" ORNET Technologies - Task 1: Direct Code Correction")
    print("=" * 60)
    print("\nInput Products List:")
    for item in products:
        print(f" - {item['name']}: Rs. {item['price']}")

    name, price = highest_priced_product(products)

    print("\nResult:")
    print(f" Highest Priced Product Name  : {name}")
    print(f" Highest Priced Product Price : {price}")
    print("=" * 60)