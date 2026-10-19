## Overview

This repository contains the solution for **Task 1: Python Code Correction & Debugging**. 

The goal was to diagnose and fix critical bugs in an initial product search function, extend it to return both the product name and price, and build a modular validation pipeline capable of safely handling corrupt, negative, or missing data.

---

## Repository Structure

```text
├── task1_direct_correction.py          # Direct fix for the assessment sample data
├── task1_modular_solution.py           # Modular validation script reading from JSON
├── sample_products_all_cases.json      # Dataset containing valid items and edge cases
├── Task_1_Code_Correction_and_Analysis.pdf  # Technical analysis report
└── README.md                           # Documentation and setup instructions
```

---

## Issues Identified in the Original Code

The initial code contained two runtime errors and several missing edge-case checks:

```python
# Original Buggy Code
def highest_priced_product(products):
    highest = 0
    for product in products:
        if product["price"] > highest:
            highest = product["name"]      # Bug 1: Overwrites numeric baseline with string
    return highest["name"]                 # Bug 2: String subscript error (TypeError)
```

1. **Type Mutation Error**: On the first iteration where a product price exceeds `0`, `highest` is assigned the product's string name (e.g., `'Keyboard'`). On the next iteration, `product["price"] > highest` compares an `int` to a `str`, raising a `TypeError`.
2. **Subscript Error on String**: The return statement attempts `highest["name"]`. Since `highest` is a string (or `0` if the list is empty), indexing with a string key raises a `TypeError`.
3. **Incomplete Output**: The specification requires returning both the product name and its price as a tuple, whereas the original function only attempted to return the name.
4. **Missing Validation**: The original implementation lacked guards for empty lists, missing dictionary keys, non-numeric values, boolean flags (`True`/`False`), and negative prices.

---

## Solutions

### 1. Direct Correction (`task1_direct_correction.py`)
This script directly resolves the bugs by tracking the highest price and product name in separate variables:
- Initializes `highest_price = -1` and `highest_product_name = None`.
- Iterates through the list, comparing numeric prices directly.
- Safely returns `(None, None)` if the list is empty.
- Returns a clean tuple: `(highest_product_name, highest_price)`.

### 2. Modular Validation Pipeline (`task1_modular_solution.py`)
This script separates concerns into focused helper functions:
- `is_list_empty(product_list)`: Validates that the input is a non-empty list.
- `is_valid_price(price)`: Confirms the price is present, strictly numeric (`int` or `float`), excludes booleans, and is non-negative (`>= 0`).
- `is_valid_product_entry(item)`: Validates that each item is a valid dictionary with a non-empty string name.
- `find_highest_priced_product(products)`: Coordinates the loop and returns the highest valid product.
- `load_products_from_json(filename)`: Loads external JSON datasets.

When executed, it loads `sample_products_all_cases.json` and outputs only the highest valid product.

---

## Edge Cases Handled

The test dataset (`sample_products_all_cases.json`) verifies handling of the following scenarios:

| Scenario | Input Example | Action Taken |
| :--- | :--- | :--- |
| **Standard Valid Product** | `{"name": "Mouse", "price": 800}` | Processed normally |
| **Highest Valid Product** | `{"name": "4K Ultra-Wide Monitor", "price": 45000}` | Selected as highest |
| **Negative Price** | `{"name": "Defective Cable", "price": -250}` | Filtered out |
| **Missing Price Key** | `{"name": "Promo Sticker"}` | Filtered out |
| **Non-Numeric Price (String)** | `{"name": "Gaming Chair", "price": "Free"}` | Filtered out |
| **Missing Value (`null`)** | `{"name": "Headphones", "price": null}` | Filtered out |
| **Boolean Price (`True`)** | `{"name": "Mousepad", "price": true}` | Filtered out (rejects boolean int subtype) |
| **Zero Price** | `{"name": "Complimentary Badge", "price": 0}` | Accepted as valid |
| **Missing Name Key** | `{"price": 99999}` | Filtered out |
| **Whitespace/Empty Name** | `{"name": "   ", "price": 75000}` | Filtered out |
| **Corrupted Records** | `null`, `"Corrupted String Entry"` | Filtered out |

---

## Getting Started

### Prerequisites
- Python 3.8 or higher.
- Standard library modules only (`json`, `os`). No external dependencies required.

### Running the Scripts

1. **Run the Direct Correction**:
   ```bash
   python3 task1_direct_correction.py
   ```
   **Output**:
   ```text
   ============================================================
    ORNET Technologies - Task 1: Direct Code Correction
   ============================================================

   Input Products List:
    - Keyboard: Rs. 1500
    - Mouse: Rs. 800
    - Monitor: Rs. 12000

   Result:
    Highest Priced Product Name  : Monitor
    Highest Priced Product Price : 12000
   ============================================================
   ```

2. **Run the Modular Solution with JSON Dataset**:
   ```bash
   python3 task1_modular_solution.py
   ```
   **Output**:
   ```text
   Name  : 4K Ultra-Wide Monitor
   Price : 45000
   ```

---
