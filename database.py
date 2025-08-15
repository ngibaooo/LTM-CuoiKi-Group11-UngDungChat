from mysql.connector import Error
import os
import mysql.connector
from config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME

def get_connection():
    try:
        connection = mysql.connector.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        if connection.is_connected():
            return connection
    except Error as e:
        print(f"Lỗi kết nối MySQL: {e}")
        return None

# Test kết nối
if __name__ == "__main__":
    conn = get_connection()
    if conn:
        print("Kết nối MySQL thành công!")
        conn.close()
    else:
        print("Kết nối MySQL thất bại!")
