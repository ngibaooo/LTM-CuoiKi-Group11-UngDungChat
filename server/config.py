import os
from dotenv import load_dotenv

# Load file .env
load_dotenv()

# Lấy thông tin DB từ biến môi trường .env
DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", 3306)) #nếu không có port mặc định sẽ là 3306
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
