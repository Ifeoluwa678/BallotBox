from app import app, db
from sqlalchemy import inspect

with app.app_context():
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    print("Tables:", tables)

    for table in tables:
        print(f"\nTable: {table}")
        columns = inspector.get_columns(table)
        for col in columns:
            print(f" - {col['name']} ({col['type']})")
