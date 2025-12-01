import time
import requests
from datetime import datetime
import pytz

# URL bạn muốn ping
PING_URL = "https://factory-assets-manager.onrender.com"

# múi giờ VN
tz = pytz.timezone("Asia/Ho_Chi_Minh")

while True:
    now = datetime.now(tz)
    hour = now.hour

    # Chỉ ping từ 08:00 đến 17:00
    if 8 <= hour < 17:
        print(f"[{now}] Sending ping to {PING_URL}...")
        try:
            res = requests.get(PING_URL, timeout=15)
            print("Status:", res.status_code)
        except Exception as e:
            print("Error:", e)

        # chờ 5 phút giữa các ping
        time.sleep(300)  # 300s = 5 phút

    else:
        # Không trong giờ làm → ngủ dài
        print(f"[{now}] Ngoài giờ 08–17 → không ping. Ngủ 30 phút.")
        time.sleep(1800)  # 30 phút
