import time
from datetime import datetime
import motor.motor_asyncio
import pytz
from config import Config
from .utils import send_log

# NeX 4GB Rename Bot - Database Architecture
# Developed by @Nex_bots

TIER_NAMES = {
    0: "Free",
    1: "🥈 Level 1 - Silver",
    2: "🥇 Level 2 - Gold",
    3: "💎 Level 3 - Diamond"
}

TIER_LIMITS = {
    0: {"max_file_size": 2 * 1024 * 1024 * 1024, "daily_bytes": 5 * 1024 * 1024 * 1024, "concurrency": 1},
    1: {"max_file_size": 4 * 1024 * 1024 * 1024, "daily_bytes": 25 * 1024 * 1024 * 1024, "concurrency": 2},
    2: {"max_file_size": 4 * 1024 * 1024 * 1024, "daily_bytes": 75 * 1024 * 1024 * 1024, "concurrency": 3},
    3: {"max_file_size": 4 * 1024 * 1024 * 1024, "daily_bytes": 1024 * 1024 * 1024 * 1024 * 100, "concurrency": 5},
}


def format_user_time(dt_or_ts, tz_name: str = "Asia/Kolkata") -> str:
    """Formats a timestamp or datetime object in user's timezone."""
    try:
        user_tz = pytz.timezone(tz_name or "Asia/Kolkata")
    except Exception:
        user_tz = pytz.timezone("Asia/Kolkata")

    if isinstance(dt_or_ts, (int, float)):
        if dt_or_ts <= 0:
            return "Never"
        dt = datetime.fromtimestamp(dt_or_ts, pytz.utc)
    elif isinstance(dt_or_ts, datetime):
        dt = dt_or_ts
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
    else:
        return str(dt_or_ts)

    local_dt = dt.astimezone(user_tz)
    return local_dt.strftime("%d %b %Y, %I:%M %p %Z")


class Database:

    def __init__(self, uri, database_name):
        # serverSelectionTimeoutMS=5000 means MongoDB gives up after 5 s rather
        # than 10 s, keeping the bot responsive even when Atlas is unreachable.
        self._client = motor.motor_asyncio.AsyncIOMotorClient(
            uri,
            tlsAllowInvalidCertificates=True,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            socketTimeoutMS=10000,
        )
        self.db = self._client[database_name]
        self.col = self.db.user
        self.cfg = self.db.bot_config

    def new_user(self, id):
        return dict(
            _id=int(id),                                   
            file_id=None,
            caption=None,
            prefix=None,
            suffix=None,
            user_dump=None,
            dump_channel=None,
            metadata_bool=True,
            metadata_code="Telegram : @Nex_bots",
            clean_words=None,
            replace_words=None,
            sample_duration=0,
            screenshots=0,
            upload_mode="Ask",
            premium_tier=0,
            premium_expiry=0,
            plan_name="Free",
            trial_claimed=False,
            timezone="Asia/Kolkata",
            files_renamed_total=0,
            bytes_used_total=0,
            daily_bytes_used=0,
            daily_files_used=0,
            last_reset_date=""
        )

    async def add_user(self, b, m):
        u = m.from_user
        if not await self.is_user_exist(u.id):
            user = self.new_user(u.id)
            await self.col.insert_one(user)            
            await send_log(b, u)

    async def is_user_exist(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return bool(user)

    async def total_users_count(self):
        count = await self.col.count_documents({})
        return count

    async def get_all_users(self):
        all_users = self.col.find({})
        return all_users

    async def delete_user(self, user_id):
        await self.col.delete_many({'_id': int(user_id)})
    
    # Thumbnail methods
    async def set_thumbnail(self, id, file_id):
        await self.col.update_one({'_id': int(id)}, {'$set': {'file_id': file_id}}, upsert=True)

    async def get_thumbnail(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return user.get('file_id', None) if user else None

    # Caption methods
    async def set_caption(self, id, caption):
        await self.col.update_one({'_id': int(id)}, {'$set': {'caption': caption}}, upsert=True)

    async def get_caption(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return user.get('caption', None) if user else None
        
    # Prefix methods
    async def set_prefix(self, id, prefix):
        await self.col.update_one({'_id': int(id)}, {'$set': {'prefix': prefix}}, upsert=True)  
        
    async def get_prefix(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return user.get('prefix', None) if user else None
        
    # Suffix methods
    async def set_suffix(self, id, suffix):
        await self.col.update_one({'_id': int(id)}, {'$set': {'suffix': suffix}}, upsert=True)  
        
    async def get_suffix(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return user.get('suffix', None) if user else None

    # Metadata methods
    async def set_metadata_bool(self, id, metadata_bool):
        await self.col.update_one({'_id': int(id)}, {'$set': {'metadata_bool': bool(metadata_bool)}}, upsert=True)

    async def get_metadata_bool(self, id):
        user = await self.col.find_one({'_id': int(id)})
        if not user or 'metadata_bool' not in user:
            return True
        return bool(user.get('metadata_bool', True))

    async def set_metadata_code(self, id, metadata_code):
        await self.col.update_one({'_id': int(id)}, {'$set': {'metadata_code': metadata_code}}, upsert=True)

    async def get_metadata_code(self, id):
        user = await self.col.find_one({'_id': int(id)})
        if not user or not user.get('metadata_code'):
            return await self.get_default_metadata()
        return user.get('metadata_code') or await self.get_default_metadata()

    # Word cleaner & replacer methods
    async def set_clean_words(self, id, clean_words):
        await self.col.update_one({'_id': int(id)}, {'$set': {'clean_words': clean_words}}, upsert=True)

    async def get_clean_words(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return user.get('clean_words', None) if user else None

    async def set_replace_words(self, id, replace_words):
        await self.col.update_one({'_id': int(id)}, {'$set': {'replace_words': replace_words}}, upsert=True)

    async def get_replace_words(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return user.get('replace_words', None) if user else None

    # Sample duration methods
    async def set_sample_duration(self, id, sample_duration):
        await self.col.update_one({'_id': int(id)}, {'$set': {'sample_duration': int(sample_duration)}}, upsert=True)

    async def get_sample_duration(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return int(user.get('sample_duration', 0)) if user else 0

    # Screenshot methods
    async def set_screenshots(self, id, screenshots):
        await self.col.update_one({'_id': int(id)}, {'$set': {'screenshots': int(screenshots)}}, upsert=True)

    async def get_screenshots(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return int(user.get('screenshots', 0)) if user else 0

    # Dump channel methods
    async def set_dump_channel(self, id, dump_channel):
        await self.col.update_one({'_id': int(id)}, {'$set': {'dump_channel': dump_channel, 'user_dump': dump_channel}}, upsert=True)

    async def get_dump_channel(self, id):
        user = await self.col.find_one({'_id': int(id)})
        if user:
            return user.get('dump_channel') or user.get('user_dump')
        return None

    # Upload mode methods ("Ask", "Document", "Video", "Audio")
    async def set_upload_mode(self, id, upload_mode):
        await self.col.update_one({'_id': int(id)}, {'$set': {'upload_mode': upload_mode}}, upsert=True)

    async def get_upload_mode(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return user.get('upload_mode', "Ask") if user else "Ask"

    # Full User Settings Aggregator
    async def get_user_settings(self, id):
        user = await self.col.find_one({'_id': int(id)})
        if not user:
            return {
                "thumbnail": None,
                "caption": None,
                "prefix": None,
                "suffix": None,
                "metadata_bool": True,
                "metadata_code": "Telegram : @Nex_bots",
                "clean_words": None,
                "replace_words": None,
                "sample_duration": 0,
                "screenshots": 0,
                "dump_channel": None,
                "upload_mode": "Ask",
                "timezone": "Asia/Kolkata"
            }
        return {
            "thumbnail": user.get('file_id', None),
            "caption": user.get('caption', None),
            "prefix": user.get('prefix', None),
            "suffix": user.get('suffix', None),
            "metadata_bool": bool(user.get('metadata_bool', True)),
            "metadata_code": user.get('metadata_code', "Telegram : @Nex_bots"),
            "clean_words": user.get('clean_words', None),
            "replace_words": user.get('replace_words', None),
            "sample_duration": int(user.get('sample_duration', 0)),
            "screenshots": int(user.get('screenshots', 0)),
            "dump_channel": user.get('dump_channel') or user.get('user_dump'),
            "upload_mode": user.get('upload_mode', "Ask"),
            "timezone": user.get('timezone', "Asia/Kolkata")
        }

    # ==================== BOT CONFIGURATION & OWNER PERSISTENCE ====================

    # Bot Access Mode ("private" or "public")
    async def get_bot_mode(self) -> str:
        cfg = await self.cfg.find_one({'_id': 'bot_settings'})
        if cfg and 'bot_mode' in cfg:
            return cfg.get('bot_mode')
        return "private" if Config.OWNER_ONLY else "public"

    async def set_bot_mode(self, mode: str) -> str:
        mode = "private" if str(mode).strip().lower() == "private" else "public"
        await self.cfg.update_one({'_id': 'bot_settings'}, {'$set': {'bot_mode': mode}}, upsert=True)
        return mode

    # Authorized Users Management (for Private Mode)
    async def add_auth_user(self, user_id: int):
        await self.cfg.update_one({'_id': 'bot_settings'}, {'$addToSet': {'auth_users': int(user_id)}}, upsert=True)

    async def remove_auth_user(self, user_id: int):
        await self.cfg.update_one({'_id': 'bot_settings'}, {'$pull': {'auth_users': int(user_id)}}, upsert=True)

    async def get_auth_users(self) -> list:
        cfg = await self.cfg.find_one({'_id': 'bot_settings'})
        return cfg.get('auth_users', []) if cfg else []

    async def is_auth_user(self, user_id: int) -> bool:
        if int(user_id) in Config.ADMIN:
            return True
        cfg = await self.cfg.find_one({'_id': 'bot_settings'})
        auth_users = cfg.get('auth_users', []) if cfg else []
        return int(user_id) in auth_users

    # ==================== 3-TIER PREMIUM ENGINE ====================

    async def set_user_premium(self, user_id: int, tier: int, days: int, plan_name: str = ""):
        now = time.time()
        user = await self.col.find_one({'_id': int(user_id)})
        current_expiry = float(user.get("premium_expiry", 0) or 0) if user else 0
        current_tier = int(user.get("premium_tier", 0) or 0) if user else 0

        # Extend if currently active and same tier, otherwise start fresh
        if current_expiry > now and current_tier == int(tier):
            new_expiry = current_expiry + (int(days) * 86400)
        else:
            new_expiry = now + (int(days) * 86400)

        plan = plan_name or TIER_NAMES.get(int(tier), f"Level {tier}")
        await self.col.update_one(
            {'_id': int(user_id)},
            {'$set': {
                'premium_tier': int(tier),
                'premium_expiry': new_expiry,
                'plan_name': plan
            }},
            upsert=True
        )
        await self.cfg.update_one({'_id': 'bot_settings'}, {'$addToSet': {'premium_users': int(user_id)}}, upsert=True)
        return new_expiry

    async def remove_premium_user(self, user_id: int):
        await self.col.update_one(
            {'_id': int(user_id)},
            {'$set': {
                'premium_tier': 0,
                'premium_expiry': 0,
                'plan_name': 'Free'
            }},
            upsert=True
        )
        await self.cfg.update_one({'_id': 'bot_settings'}, {'$pull': {'premium_users': int(user_id)}}, upsert=True)

    async def get_premium_info(self, user_id: int) -> dict:
        if int(user_id) in Config.ADMIN:
            return {
                "tier": 3,
                "plan_name": "👑 Owner (Diamond)",
                "expiry": 0,
                "days_left": 9999,
                "hours_left": 0,
                "is_owner": True,
                "active": True
            }
        user = await self.col.find_one({'_id': int(user_id)})
        if not user:
            return {
                "tier": 0,
                "plan_name": "Free",
                "expiry": 0,
                "days_left": 0,
                "hours_left": 0,
                "is_owner": False,
                "active": False
            }

        tier = int(user.get("premium_tier", 0) or 0)
        expiry = float(user.get("premium_expiry", 0) or 0)
        now = time.time()

        # Check expiration
        if tier > 0 and expiry > 0 and now > expiry:
            await self.remove_premium_user(user_id)
            return {
                "tier": 0,
                "plan_name": "Free (Expired)",
                "expiry": 0,
                "days_left": 0,
                "hours_left": 0,
                "is_owner": False,
                "active": False
            }

        if tier > 0 and expiry > now:
            remaining_sec = expiry - now
            days_left = int(remaining_sec // 86400)
            hours_left = int((remaining_sec % 86400) // 3600)
            return {
                "tier": tier,
                "plan_name": user.get("plan_name", TIER_NAMES.get(tier, f"Level {tier}")),
                "expiry": expiry,
                "days_left": days_left,
                "hours_left": hours_left,
                "is_owner": False,
                "active": True
            }

        return {
            "tier": 0,
            "plan_name": "Free",
            "expiry": 0,
            "days_left": 0,
            "hours_left": 0,
            "is_owner": False,
            "active": False
        }

    async def is_premium_user(self, user_id: int) -> bool:
        if int(user_id) in Config.ADMIN:
            return True
        info = await self.get_premium_info(user_id)
        return bool(info.get("active", False))

    async def get_all_premium_users(self) -> list:
        now = time.time()
        cursor = self.col.find({"premium_tier": {"$gt": 0}})
        results = []
        async for doc in cursor:
            expiry = float(doc.get("premium_expiry", 0) or 0)
            if expiry > now:
                results.append({
                    "user_id": doc["_id"],
                    "tier": int(doc.get("premium_tier", 1)),
                    "plan_name": doc.get("plan_name", TIER_NAMES.get(doc.get("premium_tier", 1), "Premium")),
                    "expiry": expiry
                })
        return results

    # ==================== 1-TIME 3-DAY FREE TRIAL ====================

    async def has_claimed_trial(self, user_id: int) -> bool:
        user = await self.col.find_one({'_id': int(user_id)})
        if user and user.get("trial_claimed"):
            return True
        cfg = await self.cfg.find_one({'_id': 'bot_settings'})
        claimed_ids = cfg.get("claimed_trial_ids", []) if cfg else []
        return int(user_id) in claimed_ids

    async def claim_free_trial(self, user_id: int) -> bool:
        if await self.has_claimed_trial(user_id):
            return False
        # Record claimed status permanently on both user doc and global bot_config
        await self.col.update_one({'_id': int(user_id)}, {'$set': {'trial_claimed': True}}, upsert=True)
        await self.cfg.update_one({'_id': 'bot_settings'}, {'$addToSet': {'claimed_trial_ids': int(user_id)}}, upsert=True)
        # Grant 3 days Level 2 Gold (4GB)
        await self.set_user_premium(user_id, tier=2, days=3, plan_name="Gold (3-Day Trial)")
        return True

    # ==================== COUPON CODE SYSTEM ====================

    async def create_coupon(self, code: str, tier: int, days: int, max_uses: int):
        code = str(code).strip().upper()
        coupon_data = {
            "code": code,
            "tier": int(tier),
            "days": int(days),
            "max_uses": int(max_uses),
            "used_count": 0,
            "redeemed_users": [],
            "created_at": time.time()
        }
        await self.cfg.update_one({'_id': 'bot_settings'}, {'$set': {f'coupons.{code}': coupon_data}}, upsert=True)
        return coupon_data

    async def delete_coupon(self, code: str):
        code = str(code).strip().upper()
        await self.cfg.update_one({'_id': 'bot_settings'}, {'$unset': {f'coupons.{code}': ''}}, upsert=True)

    async def get_all_coupons(self) -> dict:
        cfg = await self.cfg.find_one({'_id': 'bot_settings'})
        return cfg.get("coupons", {}) if cfg else {}

    async def redeem_coupon(self, user_id: int, code: str) -> tuple:
        code = str(code).strip().upper()
        cfg = await self.cfg.find_one({'_id': 'bot_settings'})
        coupons = cfg.get("coupons", {}) if cfg else {}
        coupon = coupons.get(code)
        if not coupon:
            return False, "❌ Invalid coupon code! Please check and try again."

        used_count = coupon.get("used_count", 0)
        max_uses = coupon.get("max_uses", 1)
        redeemed_users = coupon.get("redeemed_users", [])

        if int(user_id) in redeemed_users:
            return False, "⚠️ You have already redeemed this coupon code!"

        if used_count >= max_uses:
            return False, "❌ This coupon code has reached its maximum usage limit!"

        tier = int(coupon.get("tier", 1))
        days = int(coupon.get("days", 30))
        await self.cfg.update_one(
            {'_id': 'bot_settings'},
            {
                '$inc': {f'coupons.{code}.used_count': 1},
                '$addToSet': {f'coupons.{code}.redeemed_users': int(user_id)}
            }
        )
        plan_title = f"{TIER_NAMES.get(tier, f'Tier {tier}')} ({code})"
        await self.set_user_premium(user_id, tier=tier, days=days, plan_name=plan_title)
        return True, f"🎉 Coupon applied! Activated {TIER_NAMES.get(tier, 'Premium')} for {days} days."

    # ==================== USER TIMEZONE ====================

    async def get_timezone(self, user_id: int) -> str:
        user = await self.col.find_one({'_id': int(user_id)})
        return user.get("timezone", "Asia/Kolkata") if user else "Asia/Kolkata"

    async def set_timezone(self, user_id: int, tz_name: str) -> bool:
        try:
            pytz.timezone(tz_name)
        except Exception:
            return False
        await self.col.update_one({'_id': int(user_id)}, {'$set': {'timezone': tz_name}}, upsert=True)
        return True

    # ==================== USAGE TRACKING & STATISTICS ====================

    async def add_usage(self, user_id: int, file_size: int):
        tz_name = await self.get_timezone(user_id)
        try:
            user_tz = pytz.timezone(tz_name)
        except Exception:
            user_tz = pytz.timezone("Asia/Kolkata")
        today_str = datetime.now(user_tz).strftime("%Y-%m-%d")

        user = await self.col.find_one({'_id': int(user_id)})
        last_reset = user.get("last_reset_date", "") if user else ""

        if last_reset != today_str:
            await self.col.update_one(
                {'_id': int(user_id)},
                {
                    '$set': {
                        'daily_bytes_used': int(file_size),
                        'daily_files_used': 1,
                        'last_reset_date': today_str
                    },
                    '$inc': {
                        'files_renamed_total': 1,
                        'bytes_used_total': int(file_size)
                    }
                },
                upsert=True
            )
        else:
            await self.col.update_one(
                {'_id': int(user_id)},
                {
                    '$inc': {
                        'daily_bytes_used': int(file_size),
                        'daily_files_used': 1,
                        'files_renamed_total': 1,
                        'bytes_used_total': int(file_size)
                    }
                },
                upsert=True
            )

        # Global totals in bot_config
        await self.cfg.update_one(
            {'_id': 'bot_settings'},
            {
                '$inc': {
                    'global_files_renamed': 1,
                    'global_bytes_used': int(file_size)
                }
            },
            upsert=True
        )

    async def get_user_usage(self, user_id: int) -> dict:
        tz_name = await self.get_timezone(user_id)
        try:
            user_tz = pytz.timezone(tz_name)
        except Exception:
            user_tz = pytz.timezone("Asia/Kolkata")
        today_str = datetime.now(user_tz).strftime("%Y-%m-%d")

        user = await self.col.find_one({'_id': int(user_id)})
        if not user:
            return {
                "daily_bytes": 0,
                "daily_files": 0,
                "total_bytes": 0,
                "total_files": 0,
                "timezone": tz_name
            }

        last_reset = user.get("last_reset_date", "")
        if last_reset != today_str:
            daily_bytes = 0
            daily_files = 0
        else:
            daily_bytes = int(user.get("daily_bytes_used", 0) or 0)
            daily_files = int(user.get("daily_files_used", 0) or 0)

        return {
            "daily_bytes": daily_bytes,
            "daily_files": daily_files,
            "total_bytes": int(user.get("bytes_used_total", 0) or 0),
            "total_files": int(user.get("files_renamed_total", 0) or 0),
            "timezone": tz_name
        }

    async def get_global_usage(self) -> dict:
        cfg = await self.cfg.find_one({'_id': 'bot_settings'})
        now = time.time()
        silver_count = await self.col.count_documents({"premium_tier": 1, "premium_expiry": {"$gt": now}})
        gold_count = await self.col.count_documents({"premium_tier": 2, "premium_expiry": {"$gt": now}})
        diamond_count = await self.col.count_documents({"premium_tier": 3, "premium_expiry": {"$gt": now}})
        total_premium = silver_count + gold_count + diamond_count
        claimed_ids = cfg.get("claimed_trial_ids", []) if cfg else []

        return {
            "global_files": int(cfg.get("global_files_renamed", 0)) if cfg else 0,
            "global_bytes": int(cfg.get("global_bytes_used", 0)) if cfg else 0,
            "silver_users": silver_count,
            "gold_users": gold_count,
            "diamond_users": diamond_count,
            "total_premium": total_premium,
            "trials_claimed": len(claimed_ids)
        }

    # ==================== LIVE UPI CONFIGURATION ====================

    async def get_upi_id(self) -> str:
        cfg = await self.cfg.find_one({'_id': 'bot_settings'})
        if cfg and cfg.get("upi_id"):
            return cfg.get("upi_id")
        return getattr(Config, "UPI_ID", "nexbots@upi")

    async def set_upi_id(self, upi_id: str):
        upi_id = str(upi_id).strip()
        await self.cfg.update_one({'_id': 'bot_settings'}, {'$set': {'upi_id': upi_id}}, upsert=True)
        return upi_id

    # ==================== BANNED USERS ====================

    async def ban_user(self, user_id: int):
        await self.cfg.update_one({'_id': 'bot_settings'}, {'$addToSet': {'banned_users': int(user_id)}}, upsert=True)

    async def unban_user(self, user_id: int):
        await self.cfg.update_one({'_id': 'bot_settings'}, {'$pull': {'banned_users': int(user_id)}}, upsert=True)

    async def get_banned_users(self) -> list:
        cfg = await self.cfg.find_one({'_id': 'bot_settings'})
        return cfg.get('banned_users', []) if cfg else []

    async def is_banned(self, user_id: int) -> bool:
        if int(user_id) in Config.ADMIN:
            return False
        cfg = await self.cfg.find_one({'_id': 'bot_settings'})
        banned = cfg.get('banned_users', []) if cfg else []
        return int(user_id) in banned

    # Global Default Metadata Tag
    async def get_default_metadata(self) -> str:
        cfg = await self.cfg.find_one({'_id': 'bot_settings'})
        if cfg and cfg.get('default_metadata'):
            return cfg.get('default_metadata')
        return "Telegram : @Nex_bots"

    async def set_default_metadata(self, text: str) -> str:
        text = str(text).strip()
        await self.cfg.update_one({'_id': 'bot_settings'}, {'$set': {'default_metadata': text}}, upsert=True)
        return text


db = Database(Config.DB_URL, Config.DB_NAME)
