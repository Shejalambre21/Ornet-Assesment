# Task 2: SQL Database + Python Data Analysis

## Overview

This project connects Python to a MySQL database and analyzes an `orders` table using SQL and Pandas. It is implemented in the Jupyter notebook `task2_mysql_analysis.ipynb`.

The notebook covers completed sales, top customers, order-status counts, data-quality issues, monthly sales trends, and methods for avoiding double-counting in SQL joins.

## Features

1. **MySQL connection** using `mysql-connector-python`.
2. **Reusable query helper** that runs SQL and returns results as Pandas DataFrames.
3. **Sample data setup** to create the `orders` table and optionally populate sample records.
4. **Completed sales report** with a count of completed orders and total valid sales.
5. **Top 3 customers** ranked by completed order value.
6. **Order status summary** with order counts and total amount by status.
7. **Data quality audit** identifying `NULL`, zero, and negative order amounts.
8. **Monthly completed sales analysis** using Pandas, with an export to `monthly_completed_sales.csv`.
9. **SQL join guidance** explaining how to avoid inflated totals from one-to-many joins.
10. **Optional order preview** and connection cleanup.

## Requirements

- Python 3.9 or newer is recommended.
- MySQL Server running locally or on a reachable host.
- A MySQL account with permission to access the selected database and create/insert into the `orders` table if using sample-data population.
- Jupyter Notebook or JupyterLab.

## Installation

Open Command Prompt or a terminal in your project folder and install the dependencies:

```bash
python -m pip install pandas mysql-connector-python python-dotenv jupyter
```

If you are using Jupyter Notebook, start it with:

```bash
jupyter notebook
```

Then open `task2_mysql_analysis.ipynb`.

## Database configuration

The notebook reads these environment variables when available:

| Variable | Default | Description |
|---|---|---|
| `MYSQL_HOST` | `localhost` | MySQL server host |
| `MYSQL_PORT` | `3306` | MySQL server port |
| `MYSQL_USER` | `root` | MySQL username |
| `MYSQL_PASSWORD` | No secure default recommended | Password for the MySQL account |
| `MYSQL_DATABASE` | `sales_db` | Database to connect to |

### Recommended: use a `.env` file

Create a file named `.env` in the same folder as the notebook:

```dotenv
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_actual_mysql_password
MYSQL_DATABASE=sales_db
```

Replace `your_actual_mysql_password` with your own MySQL password. Do not include angle brackets. Keep `.env` private and do not commit it to a public repository.

Make sure the configured database exists before connecting. For example, from a MySQL client, you can create it with:

```sql
CREATE DATABASE sales_db;
```

If your MySQL account uses a different username, password, host, port, or database name, update the `.env` values accordingly. Avoid putting real credentials directly in the notebook.

## Run the notebook

1. Start MySQL Server.
2. Confirm that the database named in `MYSQL_DATABASE` exists.
3. Create the `.env` file or set the environment variables.
4. Open `task2_mysql_analysis.ipynb` in Jupyter.
5. Run the cells from top to bottom.
6. Check the connection message before running the analysis cells.
7. Review the query outputs and the generated monthly sales CSV file.

The notebook's optional sample-data cell is controlled by `POPULATE_SAMPLE_DATA`. Set it to `True` to create the `orders` table and insert the notebook's sample records, or `False` to skip that step. Review the cell before running it against a database containing important data.

## Database schema

The notebook expects an `orders` table with this structure:

```sql
CREATE TABLE orders (
    order_id INT PRIMARY KEY,
    customer_id INT,
    order_date DATE,
    amount DECIMAL(10,2),
    status VARCHAR(20)
);
```

Example status values include `Completed`, `Pending`, and `Cancelled`.

## Analysis questions

### Q1. Total completed sales
Calculates the count of completed orders and the sum of positive amounts for orders with status `Completed`.

### Q2. Top 3 customers by completed order value
Groups valid completed orders by `customer_id`, calculates total order value and order count, then returns the three highest-value customers.

### Q3. Order counts by status
Groups orders by status and reports the order count and total amount for each status.

### Q4. Data quality audit
Finds orders where `amount` is `NULL`, zero, or negative and labels each issue with a SQL `CASE` expression.

### Q5. Monthly completed sales
Fetches completed orders, converts `order_date` to a Pandas datetime, excludes missing or non-positive amounts, groups by month, and writes the summary to `monthly_completed_sales.csv`.

### Q6. Avoiding double-counting in joins
Explains how one-to-many joins can duplicate order rows and inflate sums. The recommended approach is to aggregate data at the correct level before joining. `SUM(DISTINCT amount)` is not a reliable fix because different orders can have the same amount.

## Troubleshooting

### `1045 (28000): Access denied for user 'root'@'localhost'`
MySQL rejected the username/password combination or authentication attempt.

1. Test login from Command Prompt:

   ```bash
   mysql -u root -p
   ```

2. Enter the actual MySQL password when prompted.
3. If login fails, verify or reset the MySQL account credentials using your MySQL administration tool.
4. Update `MYSQL_USER` and `MYSQL_PASSWORD` in `.env`.
5. Restart the notebook kernel and rerun the connection cell.

Do not assume the password shown as a code fallback is correct; use the password configured for your own MySQL installation.

### `Unknown database 'sales_db'`
Create the database in MySQL or change `MYSQL_DATABASE` to an existing database name.

### `ModuleNotFoundError`
Install the missing dependency in the same Python environment used by Jupyter:

```bash
python -m pip install pandas mysql-connector-python python-dotenv
```

If the notebook uses another Python environment, install the packages in that environment.

### `Table '...orders' doesn't exist`
Run the optional table/sample-data setup cell, or create and populate the `orders` table yourself. Ensure the selected database is the one containing the table.

### Connection refused / cannot connect
Confirm that MySQL Server is installed, running, and listening on the configured host and port (normally `localhost:3306`).

## Output

The main output is displayed in notebook DataFrames. The monthly completed-sales analysis also saves:

```text
monthly_completed_sales.csv
```

The CSV is written to the notebook's current working directory.

## Security and data notes

- Never publish your `.env` file or commit passwords to version control.
- Use a dedicated MySQL user with only the permissions the project needs when possible.
- Sample-data population may insert records into the selected database; review the setup cell before enabling it on a database containing real data.
- The notebook excludes `NULL`, zero, and negative amounts from gross completed-sales calculations. Negative values may represent returns or corrections and should be reviewed separately.

## Project files

```text
project-folder/
├── task2_mysql_analysis.ipynb
├── README.md
├── .env                  # Local credentials; do not publish
└── monthly_completed_sales.csv  # Generated by the notebook
```

## Author

Task 2 — SQL Database + Python Data Analysis
