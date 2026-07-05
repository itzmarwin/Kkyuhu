import os
from dotenv import load_dotenv

load_dotenv()

class Config(object):
    LOGGER = True

    OWNER_ID = int(os.getenv("OWNER_ID", "6765826972"))
    sudo_users = tuple(os.getenv("SUDO_USERS", "6845325416,6765826972").split(','))
    GROUP_ID = int(os.getenv("GROUP_ID", "-1002133191051"))
    TOKEN = os.getenv("TOKEN", "8498390059:AAGRQHEE9ThF2ms2klXdniJBEvUEZWV25NA")
    mongo_url = os.getenv("MONGO_URL", "mongodb+srv://HaremDBBot:ThisIsPasswordForHaremDB@haremdb.swzjngj.mongodb.net/?retryWrites=true&w=majority")
    PHOTO_URL = os.getenv("PHOTO_URL", "https://telegra.ph/file/b925c3985f0f325e62e17.jpg,https://telegra.ph/file/4211fb191383d895dab9d.jpg").split(',')
    SUPPORT_CHAT = os.getenv("SUPPORT_CHAT", "Collect_em_support")
    UPDATE_CHAT = os.getenv("UPDATE_CHAT", "Collect_em_support")
    BOT_USERNAME = os.getenv("BOT_USERNAME", "Collect_Em_AllBot")
    CHARA_CHANNEL_ID = os.getenv("CHARA_CHANNEL_ID", "-1002133191051")
    api_id = int(os.getenv("API_ID", "26626068"))
    api_hash = os.getenv("API_HASH", "bf423698bcbe33cfd58b11c78c42caa2")

    
class Production(Config):
    LOGGER = True


class Development(Config):
    LOGGER = True
