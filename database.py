import sqlite3

def create_database():
    connection = sqlite3.connect("reuseloop.db")

    connection.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device TEXT NOT NULL,
            condition TEXT NOT NULL,
            age TEXT NOT NULL,
            recommendation TEXT NOT NULL
        )
    """)

    connection.commit()
    connection.close()

if __name__ == "__main__":
    create_database()
    print("Database created successfully!")