from pathlib import Path

HOST = "127.0.0.1"   # đổi theo server
PORT = 8888

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "client_data.db"
MAX_IMAGE_EDGE = 900  # px, resize để gửi nhanh