# config.py - আগের কোড
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "8215167485:AAEdSM9LtEii_tHx1roxW7Wg7ZvUiuj8oJI")
ADMIN_IDS = [int(id) for id in os.getenv("ADMIN_IDS", "5851334722").split(",")]

USDT_TO_BDT_RATE = int(os.getenv("USDT_TO_BDT_RATE", 127))
MIN_DEPOSIT_USDT = int(os.getenv("MIN_DEPOSIT_USDT", 5))
MIN_WITHDRAW_USDT = int(os.getenv("MIN_WITHDRAW_USDT", 5))
WITHDRAW_FEE_USDT = float(os.getenv("WITHDRAW_FEE_USDT", 0.1))

BKASH_NUMBER = os.getenv("BKASH_NUMBER", "01600170756")
NAGAD_NUMBER = os.getenv("NAGAD_NUMBER", "01727332914")
ROCKET_NUMBER = os.getenv("ROCKET_NUMBER", "017XXXXXXXX")

BOT_NAME = "Promotion Bot"
BOT_USERNAME = os.getenv("BOT_USERNAME", "@Lawra10bot")
