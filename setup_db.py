"""Creates a small sample SQLite database (customers, products, orders)."""
import random
import sqlite3
from datetime import date, timedelta

DB_PATH = "sample.db"
random.seed(42)

CITIES = ["Delhi", "Mumbai", "Bengaluru", "Chennai", "Kolkata", "Pune", "Hyderabad"]
FIRST = ["Aarav", "Diya", "Rohan", "Isha", "Kabir", "Meera", "Vivaan", "Anaya",
         "Arjun", "Sara", "Reyansh", "Tara", "Neil", "Riya", "Dev", "Kiara"]
LAST = ["Sharma", "Verma", "Iyer", "Patel", "Reddy", "Gupta", "Nair", "Singh"]
PRODUCTS = [
    ("Laptop", "Electronics", 55000), ("Smartphone", "Electronics", 25000),
    ("Headphones", "Electronics", 3000), ("Desk Chair", "Furniture", 7500),
    ("Study Table", "Furniture", 6500), ("Notebook Pack", "Stationery", 250),
    ("Pen Set", "Stationery", 150), ("Backpack", "Accessories", 1800),
    ("Water Bottle", "Accessories", 600), ("Monitor", "Electronics", 12000),
]


def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.executescript("""
        DROP TABLE IF EXISTS orders;
        DROP TABLE IF EXISTS products;
        DROP TABLE IF EXISTS customers;
        CREATE TABLE customers (
            id INTEGER PRIMARY KEY, name TEXT, city TEXT, signup_date TEXT);
        CREATE TABLE products (
            id INTEGER PRIMARY KEY, name TEXT, category TEXT, price REAL);
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER REFERENCES customers(id),
            product_id INTEGER REFERENCES products(id),
            quantity INTEGER, order_date TEXT);
    """)
    start = date(2024, 1, 1)
    for i in range(1, 41):
        name = f"{random.choice(FIRST)} {random.choice(LAST)}"
        signup = start + timedelta(days=random.randint(0, 300))
        cur.execute("INSERT INTO customers VALUES (?,?,?,?)",
                    (i, name, random.choice(CITIES), signup.isoformat()))
    cur.executemany("INSERT INTO products (name, category, price) VALUES (?,?,?)", PRODUCTS)
    for i in range(1, 301):
        d = start + timedelta(days=random.randint(0, 600))
        cur.execute("INSERT INTO orders VALUES (?,?,?,?,?)",
                    (i, random.randint(1, 40), random.randint(1, len(PRODUCTS)),
                     random.randint(1, 5), d.isoformat()))
    con.commit()
    con.close()
    print(f"Created {DB_PATH}")


if __name__ == "__main__":
    main()
