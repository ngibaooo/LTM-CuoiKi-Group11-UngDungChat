import mysql.connector
from mysql.connector import Error
from config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME

# Function to initialize the database
def init_db():
    try:
        # Establish the connection to MySQL
        conn = mysql.connector.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        cursor = conn.cursor()

        # Create USERS table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS USERS (
            Id INT AUTO_INCREMENT PRIMARY KEY,
            Username VARCHAR(50) NOT NULL UNIQUE,
            Password VARCHAR(255) NOT NULL,
            Display_name VARCHAR(100) NOT NULL UNIQUE,
            Status ENUM('online', 'offline') DEFAULT 'offline',
            Created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            Email VARCHAR(100) UNIQUE,
            Avatar VARCHAR(255)
        );
        """)
        print("USERS table created or already exists.")

        # Create MESSAGES table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS MESSAGES (
            Id INT AUTO_INCREMENT PRIMARY KEY,
            Sender_id INT NOT NULL,
            Receive_id INT,
            Room_id INT NOT NULL,
            Content TEXT NOT NULL,
            Send_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            Status ENUM('sent', 'delivered', 'read') DEFAULT 'sent',
            FOREIGN KEY (Sender_id) REFERENCES USERS(Id),
            FOREIGN KEY (Receive_id) REFERENCES USERS(Id),
            FOREIGN KEY (Room_id) REFERENCES CHAT_ROOM(Id)
        );
        """)
        print("MESSAGES table created or already exists.")

        # Create CHAT_ROOM table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS CHAT_ROOM (
            Id INT AUTO_INCREMENT PRIMARY KEY,
            Room_name VARCHAR(100) NOT NULL,
            Created_by INT NOT NULL,
            Created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (Created_by) REFERENCES USERS(Id)
        );
        """)
        print("CHAT_ROOM table created or already exists.")

        # Create ROOM_MEMBER table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS ROOM_MEMBER (
            Room_id INT NOT NULL,
            User_id INT NOT NULL,
            Joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            Role ENUM('admin', 'member') DEFAULT 'member',
            PRIMARY KEY (Room_id, User_id),
            FOREIGN KEY (Room_id) REFERENCES CHAT_ROOM(Id),
            FOREIGN KEY (User_id) REFERENCES USERS(Id)
        );
        """)
        print("ROOM_MEMBER table created or already exists.")

        # Commit the changes
        conn.commit()
        cursor.close()
        conn.close()

    except Error as e:
        print(f"Error initializing database: {e}")
    else:
        print("Database initialized successfully.")

if __name__ == "__main__":
    init_db()
