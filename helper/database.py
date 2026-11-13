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
    0: {"max_file_size": 2 * 1024 * 1024 * 1024, "daily_bytes": 20 * 1024 * 1024 * 1024, "concurrency": 1, "queue_limit": 3, "max_speed": 0},
    1: {"max_file_size": 4 * 1024 * 1024 * 1024, "daily_bytes": 50 * 1024 * 1024 * 1024, "concurrency": 4, "queue_limit": 15, "max_speed": 0},
    2: {"max_file_size": 4 * 1024 * 1024 * 1024, "daily_bytes": 150 * 1024 * 1024 * 1024, "concurrency": 4, "queue_limit": 15, "max_speed": 0},
    3: {"max_file_size": 4 * 1024 * 1024 * 1024, "daily_bytes": 1024 * 1024 * 1024 * 1024 * 100, "concurrency": 4, "queue_limit": 15, "max_speed": 0},
}

PLAN_DURATIONS = {
    30: {"name": "1 Month (30 Days)", "short": "1 Month", "days": 30},
    90: {"name": "3 Months (90 Days)", "short": "3 Months", "days": 90},
    180: {"name": "6 Months (180 Days)", "short": "6 Months", "days": 180},
    365: {"name": "1 Year (365 Days)", "short": "1 Year", "days": 365},
}

PLAN_PRICING = {
    1: {
        "name": "Silver Plan",
        "badge": "🥈",
        "speed": "Turbo (40-80 MB/s)",
        "quota": "50 GB/Day",
        "concurrency": 4,
        "features": "4GB Support • 40-80 MB/s Speed • 50 GB/Day • Watermark & Meta • 4 Tasks",
        30: {"inr": 103, "stars": 103},
        90: {"inr": 259, "stars": 259},
        180: {"inr": 454, "stars": 454},
        365: {"inr": 779, "stars": 779},
    },
    2: {
        "name": "Gold Plan",
        "badge": "🥇",
        "speed": "Turbo (40-80 MB/s)",
        "quota": "150 GB/Day",
        "concurrency": 4,
        "features": "4GB Support • 40-80 MB/s Speed • 150 GB/Day • Watermark, Sample & Priority • 4 Tasks",
        30: {"inr": 168, "stars": 168},
        90: {"inr": 428, "stars": 428},
        180: {"inr": 779, "stars": 779},
        365: {"inr": 1299, "stars": 1299},
    },
    3: {
        "name": "Diamond VIP Plan",
        "badge": "💎",
        "speed": "Unlimited Max Speed",
        "quota": "Unlimited Daily Quota",
        "concurrency": 4,
        "features": "4GB Support • UNLIMITED Speed • UNLIMITED Daily Quota • All Features • 4 Tasks",
        30: {"inr": 259, "stars": 259},
        90: {"inr": 649, "stars": 649},
        180: {"inr": 1169, "stars": 1169},
        365: {"inr": 1949, "stars": 1949},
    }
}


LANG_TZ_MAP = {
    "hi": "Asia/Kolkata", "ta": "Asia/Kolkata", "te": "Asia/Kolkata",
    "kn": "Asia/Kolkata", "ml": "Asia/Kolkata", "bn": "Asia/Kolkata",
    "mr": "Asia/Kolkata", "gu": "Asia/Kolkata", "pa": "Asia/Kolkata",
    "en-in": "Asia/Kolkata", "en-gb": "Europe/London", "en-us": "America/New_York",
    "ru": "Europe/Moscow", "ar": "Asia/Dubai", "id": "Asia/Jakarta"
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


# ==================== FAST IN-MEMORY TTL CACHE (< 100ms UI RESPONSE) ====================
_CACHE = {}
_CACHE_TTL = 30.0  # 30 seconds TTL

def _cache_get(key: str):
    item = _CACHE.get(key)
    if not item:
        return None
    val, expires_at = item
    if time.time() > expires_at:
        _CACHE.pop(key, None)
        return None
    return val

def _cache_set(key: str, val, ttl: float = _CACHE_TTL):
    _CACHE[key] = (val, time.time() + ttl)

def _cache_invalidate(*prefixes):
    for prefix in prefixes:
        matched = [k for k in list(_CACHE.keys()) if k.startswith(prefix)]
        for k in matched:
            _CACHE.pop(k, None)


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
            maxPoolSize=50,
            minPoolSize=5,
            maxIdleTimeMS=30000,
            heartbeatFrequencyMS=10000,
        )
        self.db = self._client[database_name]
        self.col = self.db.user
        self.cfg = self.db.bot_config
        self.logs = self.db.activity_logs
        self.tasks = self.db.active_tasks

    @property
    def client(self):
        """Exposes the underlying Motor client for direct commands like admin ping."""
        return self._client

    async def ping(self):
        """Pings the MongoDB cluster admin command."""
        return await self._client.admin.command("ping")

    def new_user(self, id, first_name="", username="", timezone="Asia/Kolkata"):
        return dict(
            _id=int(id),
            first_name=first_name or "",
            username=username or "",
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
            sample_start_mode="auto",
            screenshots=0,
            upload_mode="Ask",
            wm_enabled=False,
            wm_text="",
            wm_position="top_right",
            wm_size=28,
            wm_color="white",
            premium_tier=0,
            premium_expiry=0,
            plan_name="Free",
            trial_claimed=False,
            timezone=timezone or "Asia/Kolkata",
            files_renamed_total=0,
            bytes_used_total=0,
            daily_bytes_used=0,
            daily_files_used=0,
            last_reset_date="",
            total_samples_generated=0,
            total_screenshots_generated=0,
            total_watermarks_applied=0,
            total_metadata_applied=0,
            referral_points=0,
            total_referrals=0,
            referral_rewards_claimed=0,
            referred_by=None
        )

    async def add_user(self, b, m):
        u = m.from_user
        if not u:
            return
        lang = (getattr(u, "language_code", None) or "").lower()
        auto_tz = LANG_TZ_MAP.get(lang, "Asia/Kolkata")
        if not await self.is_user_exist(u.id):
            user = self.new_user(u.id, first_name=u.first_name, username=u.username, timezone=auto_tz)
            await self.col.insert_one(user)            
            await send_log(b, u)
        else:
            update_data = {}
            if u.first_name:
                update_data["first_name"] = u.first_name
            if u.username:
                update_data["username"] = u.username
            if update_data:
                await self.col.update_one({'_id': int(u.id)}, {'$set': update_data})

    async def update_user_info(self, u):
        if not u:
            return
        update_data = {}
        if getattr(u, "first_name", None):
            update_data["first_name"] = u.first_name
        if getattr(u, "username", None):
            update_data["username"] = u.username
        if update_data:
            await self.col.update_one({'_id': int(u.id)}, {'$set': update_data}, upsert=True)

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
        _cache_invalidate(f"user_settings:{id}")

    async def get_thumbnail(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return user.get('file_id', None) if user else None

    # Caption methods
    async def set_caption(self, id, caption):
        await self.col.update_one({'_id': int(id)}, {'$set': {'caption': caption}}, upsert=True)
        _cache_invalidate(f"user_settings:{id}")

    async def get_caption(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return user.get('caption', None) if user else None
        
    # Prefix methods
    async def set_prefix(self, id, prefix):
        await self.col.update_one({'_id': int(id)}, {'$set': {'prefix': prefix}}, upsert=True)  
        _cache_invalidate(f"user_settings:{id}")
        
    async def get_prefix(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return user.get('prefix', None) if user else None

    # Episode Template methods
    async def set_template(self, id, template):
        await self.col.update_one({'_id': int(id)}, {'$set': {'episode_template': template}}, upsert=True)
        _cache_invalidate(f"user_settings:{id}")

    async def get_template(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return user.get('episode_template', None) if user else None
        
    # Suffix methods
    async def set_suffix(self, id, suffix):
        await self.col.update_one({'_id': int(id)}, {'$set': {'suffix': suffix}}, upsert=True)  
        _cache_invalidate(f"user_settings:{id}")
        
    async def get_suffix(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return user.get('suffix', None) if user else None

    # Metadata methods
    async def set_metadata_bool(self, id, metadata_bool):
        await self.col.update_one({'_id': int(id)}, {'$set': {'metadata_bool': bool(metadata_bool)}}, upsert=True)
        _cache_invalidate(f"user_settings:{id}")

    async def get_metadata_bool(self, id):
        user = await self.col.find_one({'_id': int(id)})
        if not user or 'metadata_bool' not in user:
            return True
        return bool(user.get('metadata_bool', True))

    async def set_metadata_code(self, id, metadata_code):
        await self.col.update_one({'_id': int(id)}, {'$set': {'metadata_code': metadata_code}}, upsert=True)
        _cache_invalidate(f"user_settings:{id}")

    async def get_metadata_code(self, id):
        user = await self.col.find_one({'_id': int(id)})
        if not user or not user.get('metadata_code'):
            return await self.get_default_metadata()
        return user.get('metadata_code') or await self.get_default_metadata()

    # Word cleaner & replacer methods
    async def set_clean_words(self, id, clean_words):
        await self.col.update_one({'_id': int(id)}, {'$set': {'clean_words': clean_words}}, upsert=True)
        _cache_invalidate(f"user_settings:{id}")

    async def get_clean_words(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return user.get('clean_words', None) if user else None

    async def set_replace_words(self, id, replace_words):
        await self.col.update_one({'_id': int(id)}, {'$set': {'replace_words': replace_words}}, upsert=True)
        _cache_invalidate(f"user_settings:{id}")

    async def get_replace_words(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return user.get('replace_words', None) if user else None

    # Sample duration methods
    async def set_sample_duration(self, id, sample_duration):
        await self.col.update_one({'_id': int(id)}, {'$set': {'sample_duration': int(sample_duration)}}, upsert=True)
        _cache_invalidate(f"user_settings:{id}")

    async def get_sample_duration(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return int(user.get('sample_duration', 0)) if user else 0

    # Screenshot methods
    async def set_screenshots(self, id, screenshots):
        await self.col.update_one({'_id': int(id)}, {'$set': {'screenshots': int(screenshots)}}, upsert=True)
        _cache_invalidate(f"user_settings:{id}")

    async def get_screenshots(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return int(user.get('screenshots', 0)) if user else 0

    # Dump channel methods
    async def set_dump_channel(self, id, dump_channel):
        await self.col.update_one({'_id': int(id)}, {'$set': {'dump_channel': dump_channel, 'user_dump': dump_channel}}, upsert=True)
        _cache_invalidate(f"user_settings:{id}")

    async def get_dump_channel(self, id):
        user = await self.col.find_one({'_id': int(id)})
        if user:
            return user.get('dump_channel') or user.get('user_dump')
        return None

    # Upload mode methods ("Ask", "Document", "Video", "Audio")
    async def set_upload_mode(self, id, upload_mode):
        await self.col.update_one({'_id': int(id)}, {'$set': {'upload_mode': upload_mode}}, upsert=True)
        _cache_invalidate(f"user_settings:{id}")

    async def get_upload_mode(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return user.get('upload_mode', "Ask") if user else "Ask"

    # Full User Settings Aggregator
    async def get_user_settings(self, id):
        ck = f"user_settings:{id}"
        cached = _cache_get(ck)
        if cached is not None:
            return cached
        user = await self.col.find_one({'_id': int(id)})
        if not user:
            res = {
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
            _cache_set(ck, res)
            return res
        res = {
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
        _cache_set(ck, res)
        return res

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
        _cache_invalidate(f"prem_info:{user_id}")
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
        _cache_invalidate(f"prem_info:{user_id}")

    async def get_premium_info(self, user_id: int) -> dict:
        ck = f"prem_info:{user_id}"
        cached = _cache_get(ck)
        if cached is not None:
            return cached

        if int(user_id) in Config.ADMIN:
            res = {
                "tier": 3,
                "plan_name": "👑 Owner (Diamond)",
                "expiry": 0,
                "days_left": 9999,
                "hours_left": 0,
                "is_owner": True,
                "active": True
            }
            _cache_set(ck, res)
            return res

        user = await self.col.find_one({'_id': int(user_id)})
        if not user:
            res = {
                "tier": 0,
                "plan_name": "Free",
                "expiry": 0,
                "days_left": 0,
                "hours_left": 0,
                "is_owner": False,
                "active": False
            }
            _cache_set(ck, res)
            return res

        tier = int(user.get("premium_tier", 0) or 0)
        expiry = float(user.get("premium_expiry", 0) or 0)
        now = time.time()

        # Check expiration
        if tier > 0 and expiry > 0 and now > expiry:
            await self.remove_premium_user(user_id)
            res = {
                "tier": 0,
                "plan_name": "Free (Expired)",
                "expiry": 0,
                "days_left": 0,
                "hours_left": 0,
                "is_owner": False,
                "active": False
            }
            _cache_set(ck, res)
            return res

        if tier > 0 and expiry > now:
            remaining_sec = expiry - now
            days_left = int(remaining_sec // 86400)
            hours_left = int((remaining_sec % 86400) // 3600)
            res = {
                "tier": tier,
                "plan_name": user.get("plan_name", TIER_NAMES.get(tier, f"Level {tier}")),
                "expiry": expiry,
                "days_left": days_left,
                "hours_left": hours_left,
                "is_owner": False,
                "active": True
            }
            _cache_set(ck, res)
            return res

        res = {
            "tier": 0,
            "plan_name": "Free",
            "expiry": 0,
            "days_left": 0,
            "hours_left": 0,
            "is_owner": False,
            "active": False
        }
        _cache_set(ck, res)
        return res

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
        ck = f"trial:{user_id}"
        cached = _cache_get(ck)
        if cached is not None:
            return cached
        user = await self.col.find_one({'_id': int(user_id)})
        if user and user.get("trial_claimed"):
            _cache_set(ck, True)
            return True
        cfg = await self.cfg.find_one({'_id': 'bot_settings'})
        claimed_ids = cfg.get("claimed_trial_ids", []) if cfg else []
        res = int(user_id) in claimed_ids
        _cache_set(ck, res)
        return res

    async def claim_free_trial(self, user_id: int) -> bool:
        if await self.has_claimed_trial(user_id):
            return False
        # Record claimed status permanently on both user doc and global bot_config
        await self.col.update_one({'_id': int(user_id)}, {'$set': {'trial_claimed': True}}, upsert=True)
        await self.cfg.update_one({'_id': 'bot_settings'}, {'$addToSet': {'claimed_trial_ids': int(user_id)}}, upsert=True)
        _cache_invalidate(f"trial:{user_id}", f"prem_info:{user_id}")
        # Grant 3 days Level 2 Gold (4GB)
        await self.set_user_premium(user_id, tier=2, days=3, plan_name="Gold (3-Day Trial)")
        return True

    async def reset_user_trial(self, user_id: int) -> bool:
        """Resets a user's trial status allowing them to claim free trial again."""
        await self.col.update_one({'_id': int(user_id)}, {'$set': {'trial_claimed': False}}, upsert=True)
        await self.cfg.update_one({'_id': 'bot_settings'}, {'$pull': {'claimed_trial_ids': int(user_id)}}, upsert=True)
        _cache_invalidate(f"trial:{user_id}", f"prem_info:{user_id}")
        return True

    async def reset_user_tasks(self, user_id: int) -> int:
        """Deletes all active and queued tasks for a user from MongoDB and clears active counter."""
        res = await self.tasks.delete_many({"user_id": int(user_id)})
        return res.deleted_count

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
            "global_samples": int(cfg.get("global_total_samples_generated", 0)) if cfg else 0,
            "global_screenshots": int(cfg.get("global_total_screenshots_generated", 0)) if cfg else 0,
            "global_watermarks": int(cfg.get("global_total_watermarks_applied", 0)) if cfg else 0,
            "global_metadata": int(cfg.get("global_total_metadata_applied", 0)) if cfg else 0,
            "global_referrals": int(cfg.get("global_total_referrals_completed", 0)) if cfg else 0,
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

    # ==================== WATERMARK METHODS ====================
    async def get_watermark(self, user_id: int) -> dict:
        user = await self.col.find_one({'_id': int(user_id)})
        if not user:
            return {
                "enabled": False,
                "text": "",
                "position": "top_right",
                "size": 28,
                "color": "white"
            }
        return {
            "enabled": bool(user.get("wm_enabled", False)),
            "text": user.get("wm_text", ""),
            "position": user.get("wm_position", "top_right"),
            "size": int(user.get("wm_size", 28)),
            "color": user.get("wm_color", "white")
        }

    async def set_watermark(self, user_id: int, **kwargs):
        update_dict = {}
        if "enabled" in kwargs:
            update_dict["wm_enabled"] = bool(kwargs["enabled"])
        if "text" in kwargs:
            update_dict["wm_text"] = str(kwargs["text"]).strip()
        if "position" in kwargs:
            update_dict["wm_position"] = str(kwargs["position"]).strip().lower()
        if "size" in kwargs:
            update_dict["wm_size"] = int(kwargs["size"])
        if "color" in kwargs:
            update_dict["wm_color"] = str(kwargs["color"]).strip().lower()

        if update_dict:
            await self.col.update_one({'_id': int(user_id)}, {'$set': update_dict}, upsert=True)

    # ==================== SAMPLE VIDEO SETTINGS ====================
    async def get_sample_settings(self, user_id: int) -> dict:
        user = await self.col.find_one({'_id': int(user_id)})
        if not user:
            return {"duration": 0, "start_mode": "auto"}
        return {
            "duration": int(user.get("sample_duration", 0)),
            "start_mode": user.get("sample_start_mode", "auto")
        }

    async def set_sample_start_mode(self, user_id: int, start_mode: str):
        await self.col.update_one({'_id': int(user_id)}, {'$set': {'sample_start_mode': str(start_mode)}}, upsert=True)

    # ==================== TOP RENAMERS LEADERBOARD ====================
    async def get_top_renamers(self, limit: int = 10) -> list:
        cursor = self.col.find({"files_renamed_total": {"$gt": 0}}).sort("files_renamed_total", -1).limit(limit)
        results = []
        now = time.time()
        async for doc in cursor:
            tier = int(doc.get("premium_tier", 0))
            expiry = float(doc.get("premium_expiry", 0) or 0)
            if tier > 0 and expiry > 0 and now > expiry:
                tier = 0
            results.append({
                "user_id": doc["_id"],
                "first_name": doc.get("first_name") or "User",
                "username": doc.get("username") or "",
                "files": int(doc.get("files_renamed_total", 0)),
                "bytes": int(doc.get("bytes_used_total", 0)),
                "tier": tier
            })
        return results

    async def get_user_rank(self, user_id: int) -> dict:
        user = await self.col.find_one({'_id': int(user_id)})
        if not user:
            return {"rank": "-", "files": 0, "bytes": 0}
        user_files = int(user.get("files_renamed_total", 0))
        if user_files == 0:
            return {"rank": "-", "files": 0, "bytes": 0}
        higher_count = await self.col.count_documents({"files_renamed_total": {"$gt": user_files}})
        return {
            "rank": higher_count + 1,
            "files": user_files,
            "bytes": int(user.get("bytes_used_total", 0))
        }

    # ==================== MAINTENANCE & CONTENT PROTECTION ====================
    async def get_maintenance(self) -> bool:
        cfg = await self.cfg.find_one({'_id': 'bot_settings'})
        return bool(cfg.get('maintenance', False)) if cfg else False

    async def set_maintenance(self, status: bool) -> bool:
        await self.cfg.update_one({'_id': 'bot_settings'}, {'$set': {'maintenance': bool(status)}}, upsert=True)
        return bool(status)

    async def get_protect_content(self) -> bool:
        cfg = await self.cfg.find_one({'_id': 'bot_settings'})
        return bool(cfg.get('protect_content', False)) if cfg else False

    async def set_protect_content(self, status: bool) -> bool:
        await self.cfg.update_one({'_id': 'bot_settings'}, {'$set': {'protect_content': bool(status)}}, upsert=True)
        return bool(status)

    # ==================== DYNAMIC FORCE-SUB ====================
    async def get_fsub_settings(self) -> dict:
        cfg = await self.cfg.find_one({'_id': 'bot_settings'})
        if cfg and 'fsub_channel' in cfg:
            return {
                "channel": cfg.get('fsub_channel'),
                "mode": cfg.get('fsub_mode', 'normal'),
                "enabled": bool(cfg.get('fsub_enabled', True))
            }
        # Fallback to Config.FORCE_SUB
        return {
            "channel": Config.FORCE_SUB,
            "mode": "normal",
            "enabled": bool(Config.FORCE_SUB)
        }

    async def set_fsub_settings(self, channel, mode: str = "normal", enabled: bool = True):
        await self.cfg.update_one(
            {'_id': 'bot_settings'},
            {'$set': {
                'fsub_channel': channel,
                'fsub_mode': mode if mode in ("normal", "request") else "normal",
                'fsub_enabled': bool(enabled)
            }},
            upsert=True
        )

    async def add_fsub_request(self, chat_id: int, user_id: int):
        await self.cfg.update_one(
            {'_id': 'bot_settings'},
            {'$addToSet': {f'fsub_requests_{chat_id}': int(user_id)}},
            upsert=True
        )

    async def has_fsub_request(self, chat_id: int, user_id: int) -> bool:
        cfg = await self.cfg.find_one({'_id': 'bot_settings'})
        if not cfg:
            return False
        reqs = cfg.get(f'fsub_requests_{chat_id}', [])
        return int(user_id) in reqs

    # ==================== ACTIVITY LOGS TRACKER ====================
    async def log_activity(self, user_id: int, name: str, action: str, details: str = ""):
        """Stores real-time activity log and caps at 200 items."""
        try:
            entry = {
                "user_id": int(user_id),
                "name": str(name or "User"),
                "action": str(action),
                "details": str(details),
                "timestamp": time.time()
            }
            await self.logs.insert_one(entry)
            # Cap at 200 documents
            count = await self.logs.count_documents({})
            if count > 200:
                oldest = await self.logs.find().sort("timestamp", 1).limit(count - 200).to_list(length=count - 200)
                if oldest:
                    old_ids = [d["_id"] for d in oldest]
                    await self.logs.delete_many({"_id": {"$in": old_ids}})
        except Exception:
            pass

    async def get_activity_logs(self, limit: int = 15) -> list:
        try:
            return await self.logs.find().sort("timestamp", -1).limit(limit).to_list(length=limit)
        except Exception:
            return []

    async def clear_activity_logs(self) -> bool:
        try:
            await self.logs.delete_many({})
            return True
        except Exception:
            return False

    # ==================== QUICK OWNER EXTENSIONS ====================
    async def extend_premium_days(self, user_id: int, extra_days: int, tier: int = None) -> dict:
        user = await self.col.find_one({'_id': int(user_id)})
        now = time.time()
        current_exp = float(user.get("premium_expiry", 0) or 0) if user else 0
        current_tier = int(user.get("premium_tier", 0) or 0) if user else 0
        base_time = max(now, current_exp)
        new_expiry = base_time + (extra_days * 86400)

        target_tier = tier if tier is not None else (current_tier if current_tier > 0 else 2)
        plan_name = TIER_NAMES.get(target_tier, "Premium")

        await self.col.update_one(
            {'_id': int(user_id)},
            {'$set': {
                'premium_expiry': new_expiry,
                'premium_tier': target_tier,
                'plan_name': plan_name,
                'is_premium': True
            }},
            upsert=True
        )
        return {"new_expiry": new_expiry, "tier": target_tier, "plan_name": plan_name}

    async def upgrade_user_tier(self, user_id: int) -> int:
        user = await self.col.find_one({'_id': int(user_id)})
        curr_tier = int(user.get("premium_tier", 1)) if user else 1
        next_tier = 1 if curr_tier >= 3 else (curr_tier + 1)
        plan_name = TIER_NAMES.get(next_tier, "Premium")
        await self.col.update_one(
            {'_id': int(user_id)},
            {'$set': {'premium_tier': next_tier, 'plan_name': plan_name}},
            upsert=True
        )
        return next_tier

    # ==================== GRANULAR ACTION STATS ====================
    async def increment_stat(self, user_id: int, stat_name: str, count: int = 1):
        """Increments a granular activity counter both on user document and globally."""
        try:
            await self.col.update_one(
                {'_id': int(user_id)},
                {'$inc': {stat_name: count}},
                upsert=True
            )
            await self.cfg.update_one(
                {'_id': 'bot_settings'},
                {'$inc': {f'global_{stat_name}': count}},
                upsert=True
            )
        except Exception:
            pass

    async def get_user_granular_stats(self, user_id: int) -> dict:
        user = await self.col.find_one({'_id': int(user_id)}) or {}
        return {
            "files_renamed": int(user.get("files_renamed_total", 0) or 0),
            "bytes_processed": int(user.get("bytes_used_total", 0) or 0),
            "samples_generated": int(user.get("total_samples_generated", 0) or 0),
            "screenshots_generated": int(user.get("total_screenshots_generated", 0) or 0),
            "watermarks_applied": int(user.get("total_watermarks_applied", 0) or 0),
            "metadata_applied": int(user.get("total_metadata_applied", 0) or 0),
            "referrals": int(user.get("total_referrals", 0) or 0),
            "referral_points": int(user.get("referral_points", 0) or 0),
            "referral_rewards_claimed": int(user.get("referral_rewards_claimed", 0) or 0)
        }

    # ==================== REFER & EARN ENGINE ====================
    async def get_referral_settings(self) -> dict:
        cfg = await self.cfg.find_one({'_id': 'bot_settings'}) or {}
        return {
            "enabled": bool(cfg.get("referral_enabled", True)),
            "required": int(cfg.get("referrals_required", 3)),
            "reward_days": int(cfg.get("referral_reward_days", 3)),
            "reward_tier": int(cfg.get("referral_reward_tier", 2))
        }

    async def set_referral_settings(self, **kwargs) -> dict:
        update = {}
        if "enabled" in kwargs and kwargs["enabled"] is not None:
            update["referral_enabled"] = bool(kwargs["enabled"])
        if "required" in kwargs and kwargs["required"] is not None:
            update["referrals_required"] = max(1, int(kwargs["required"]))
        if "reward_days" in kwargs and kwargs["reward_days"] is not None:
            update["referral_reward_days"] = max(1, int(kwargs["reward_days"]))
        if "reward_tier" in kwargs and kwargs["reward_tier"] is not None:
            update["referral_reward_tier"] = max(1, min(3, int(kwargs["reward_tier"])))
        if update:
            await self.cfg.update_one({'_id': 'bot_settings'}, {'$set': update}, upsert=True)
        return await self.get_referral_settings()

    async def get_user_referral_info(self, user_id: int) -> dict:
        user = await self.col.find_one({'_id': int(user_id)}) or {}
        return {
            "points": int(user.get("referral_points", 0) or 0),
            "total": int(user.get("total_referrals", 0) or 0),
            "claimed": int(user.get("referral_rewards_claimed", 0) or 0),
            "referred_by": user.get("referred_by")
        }

    async def process_referral(self, inviter_id: int, new_user_id: int) -> tuple:
        if int(inviter_id) == int(new_user_id):
            return False, {"reason": "self"}
        settings = await self.get_referral_settings()
        if not settings["enabled"]:
            return False, {"reason": "disabled"}

        new_u = await self.col.find_one({'_id': int(new_user_id)})
        if new_u and new_u.get("referred_by"):
            return False, {"reason": "already_referred"}

        inviter = await self.col.find_one({'_id': int(inviter_id)})
        if not inviter:
            return False, {"reason": "invalid_inviter"}

        # Link referred_by to new user
        await self.col.update_one({'_id': int(new_user_id)}, {'$set': {'referred_by': int(inviter_id)}}, upsert=True)
        # Increment inviter points & count
        await self.col.update_one(
            {'_id': int(inviter_id)},
            {'$inc': {'referral_points': 1, 'total_referrals': 1}},
            upsert=True
        )
        # Increment global counter
        await self.cfg.update_one(
            {'_id': 'bot_settings'},
            {'$inc': {'global_total_referrals_completed': 1}},
            upsert=True
        )

        # Check reward threshold
        updated_inviter = await self.col.find_one({'_id': int(inviter_id)})
        pts = int(updated_inviter.get("referral_points", 0) or 0)
        req = settings["required"]
        reward_triggered = False
        reward_days = settings["reward_days"]
        reward_tier = settings["reward_tier"]

        if pts >= req:
            reward_triggered = True
            rem_points = pts - req
            await self.col.update_one(
                {'_id': int(inviter_id)},
                {'$set': {'referral_points': rem_points}, '$inc': {'referral_rewards_claimed': 1}},
                upsert=True
            )
            await self.extend_premium_days(inviter_id, reward_days, tier=reward_tier)
            await self.log_activity(
                inviter_id,
                updated_inviter.get("first_name", "User"),
                "referral_reward",
                f"Earned {reward_days}D Tier {reward_tier}"
            )

        return True, {
            "reward_triggered": reward_triggered,
            "reward_days": reward_days,
            "reward_tier": reward_tier,
            "req": req,
            "pts": pts,
            "inviter_name": updated_inviter.get("first_name", "User")
        }

    # ==================== ZERO-LOSS PERSISTENT TASK QUEUE ====================
    async def add_active_task(self, task_id: str, user_id: int, file_name: str, file_size: int, task_type: str = "rename", extra: dict = None) -> bool:
        """Stores or updates an active task in MongoDB for crash recovery and queue tracking."""
        try:
            doc = {
                "_id": str(task_id),
                "user_id": int(user_id),
                "file_name": str(file_name),
                "file_size": int(file_size),
                "task_type": str(task_type),
                "created_at": time.time(),
                "updated_at": time.time(),
                "status": "in_progress",
                "extra": extra or {}
            }
            await self.tasks.update_one({"_id": str(task_id)}, {"$set": doc}, upsert=True)
            return True
        except Exception:
            return False

    async def remove_active_task(self, task_id: str) -> bool:
        """Removes a finished or cancelled task from the persistent queue."""
        try:
            res = await self.tasks.delete_one({"_id": str(task_id)})
            return res.deleted_count > 0
        except Exception:
            return False

    async def get_active_tasks(self, max_age_seconds: int = 7200) -> list:
        """Returns all in-progress active tasks created within the last max_age_seconds (default 2h)."""
        try:
            min_ts = time.time() - max_age_seconds
            cursor = self.tasks.find({"updated_at": {"$gte": min_ts}, "status": "in_progress"})
            return await cursor.to_list(length=200)
        except Exception:
            return []

    async def get_user_active_tasks_count(self, user_id: int) -> int:
        """Returns number of active tasks currently running or queued for a user."""
        try:
            min_ts = time.time() - 7200
            return await self.tasks.count_documents({
                "user_id": int(user_id),
                "status": "in_progress",
                "updated_at": {"$gte": min_ts}
            })
        except Exception:
            return 0

    async def cleanup_stale_tasks(self, max_age_seconds: int = 7200) -> int:
        """Deletes tasks older than max_age_seconds from MongoDB."""
        try:
            min_ts = time.time() - max_age_seconds
            res = await self.tasks.delete_many({"updated_at": {"$lt": min_ts}})
            return res.deleted_count
        except Exception:
            return 0

    # ==================== DYNAMIC PRICING ENGINE ====================
    async def get_premium_pricing(self) -> dict:
        """Retrieves live pricing from MongoDB; defaults to PLAN_PRICING with 1:1 INR/Stars parity."""
        cached = _cache_get("premium_pricing")
        if cached is not None:
            return cached
        import copy
        doc = await self.cfg.find_one({'_id': 'premium_pricing'})
        if not doc or not doc.get("pricing"):
            res = copy.deepcopy(PLAN_PRICING)
            _cache_set("premium_pricing", res)
            return res
        raw = doc.get("pricing", {})
        parsed = {}
        for tier_k, tier_v in raw.items():
            t_int = int(tier_k)
            parsed[t_int] = dict(tier_v)
            for d_k, d_v in tier_v.items():
                if str(d_k).isdigit():
                    parsed[t_int][int(d_k)] = d_v
        _cache_set("premium_pricing", parsed)
        return parsed

    async def set_plan_price(self, tier: int, days: int, price: int) -> bool:
        """Sets a plan price with strict 1:1 parity between INR and Stars."""
        import copy
        pricing = await self.get_premium_pricing()
        tier = int(tier)
        days = int(days)
        price = max(1, int(price))
        if tier not in pricing:
            pricing[tier] = copy.deepcopy(PLAN_PRICING.get(tier, {}))
        if days not in pricing[tier]:
            pricing[tier][days] = {}
        pricing[tier][days]["inr"] = price
        pricing[tier][days]["stars"] = price

        db_doc = {str(k): {str(sub_k): sub_v for sub_k, sub_v in v.items()} for k, v in pricing.items()}
        await self.cfg.update_one({'_id': 'premium_pricing'}, {'$set': {'pricing': db_doc}}, upsert=True)
        _cache_invalidate("premium_pricing")
        return True

    async def boost_all_prices_percent(self, percent: float = 30.0) -> dict:
        """Boosts all plan prices by percent% and enforces strict 1:1 INR == Stars parity."""
        pricing = await self.get_premium_pricing()
        factor = 1.0 + (percent / 100.0)
        for tier_k, tier_v in pricing.items():
            for d_k in [30, 90, 180, 365]:
                if d_k in tier_v and isinstance(tier_v[d_k], dict):
                    cur_inr = tier_v[d_k].get("inr", 100)
                    new_val = max(1, round(cur_inr * factor))
                    tier_v[d_k]["inr"] = new_val
                    tier_v[d_k]["stars"] = new_val
        db_doc = {str(k): {str(sub_k): sub_v for sub_k, sub_v in v.items()} for k, v in pricing.items()}
        await self.cfg.update_one({'_id': 'premium_pricing'}, {'$set': {'pricing': db_doc}}, upsert=True)
        _cache_invalidate("premium_pricing")
        return pricing

    async def reset_pricing_defaults(self) -> dict:
        """Resets pricing back to default PLAN_PRICING with +30% 1:1 parity."""
        import copy
        db_doc = {str(k): {str(sub_k): sub_v for sub_k, sub_v in v.items()} for k, v in PLAN_PRICING.items()}
        await self.cfg.update_one({'_id': 'premium_pricing'}, {'$set': {'pricing': db_doc}}, upsert=True)
        _cache_invalidate("premium_pricing")
        return copy.deepcopy(PLAN_PRICING)

    # ==================== ATOMIC STATS & LIVE COUNTERS ====================
    async def increment_rename_stats(self, user_id: int, file_size: int):
        """Atomically increments total files renamed and total bytes processed (global and per-user)."""
        today_str = datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%Y-%m-%d")
        size = int(file_size) if file_size else 0
        try:
            await self.db.bot_stats.update_one(
                {"_id": "global"},
                {
                    "$inc": {
                        "total_files_renamed": 1,
                        "total_bytes_processed": size
                    },
                    "$set": {"last_rename_time": time.time()}
                },
                upsert=True
            )
            await self.db.bot_stats.update_one(
                {"_id": f"daily_{today_str}"},
                {
                    "$inc": {
                        "files_renamed": 1,
                        "bytes_processed": size
                    }
                },
                upsert=True
            )
            await self.col.update_one(
                {"_id": int(user_id)},
                {
                    "$inc": {
                        "files_renamed_total": 1,
                        "bytes_used_total": size,
                        "daily_files_used": 1,
                        "daily_bytes_used": size
                    }
                },
                upsert=True
            )
        except Exception as e:
            print(f"increment_rename_stats error: {e}")

    async def get_global_rename_stats(self) -> dict:
        """Returns live all-time and today rename and bandwidth stats from MongoDB."""
        today_str = datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%Y-%m-%d")
        try:
            g = await self.db.bot_stats.find_one({"_id": "global"}) or {}
            d = await self.db.bot_stats.find_one({"_id": f"daily_{today_str}"}) or {}
            return {
                "total_files": g.get("total_files_renamed", 0),
                "total_bytes": g.get("total_bytes_processed", 0),
                "today_files": d.get("files_renamed", 0),
                "today_bytes": d.get("bytes_processed", 0)
            }
        except Exception:
            return {"total_files": 0, "total_bytes": 0, "today_files": 0, "today_bytes": 0}

    # ==================== DYNAMIC BOT CONFIGURATION ====================
    async def get_bot_settings(self) -> dict:
        """Returns live bot configuration settings with fast TTL cache."""
        cached = _cache_get("bot_settings")
        if cached is not None:
            return cached
        cfg = await self.cfg.find_one({'_id': 'bot_settings'}) or {}
        res = {
            "owner_only": bool(cfg.get("owner_only", Config.OWNER_ONLY)),
            "force_sub": cfg.get("force_sub", Config.FORCE_SUB),
            "free_quota_gb": int(cfg.get("free_quota_gb", 20)),
            "free_concurrency": int(cfg.get("free_concurrency", 1)),
            "prem_concurrency": int(cfg.get("prem_concurrency", 4)),
            "trial_enabled": bool(cfg.get("trial_enabled", True)),
            "trial_days": int(cfg.get("trial_days", 3)),
            "base_month_price_inr": int(cfg.get("base_month_price_inr", 139)),
            "ram_disk_enabled": bool(cfg.get("ram_disk_enabled", True)),
            "session_upload_enabled": bool(cfg.get("session_upload_enabled", True)),
            "auto_sample_enabled": bool(cfg.get("auto_sample_enabled", True)),
            "auto_screenshot_enabled": bool(cfg.get("auto_screenshot_enabled", True)),
            "payment_qr_url": cfg.get("payment_qr_url", getattr(Config, "QR_PIC", "https://graph.org/file/f0a4f5f54316ee0a71be9.jpg")),
            "admin_contact": cfg.get("admin_contact", "NexCRSupportbot")
        }
        _cache_set("bot_settings", res)
        return res

    async def update_bot_settings(self, **kwargs) -> dict:
        """Updates live bot configuration settings in MongoDB."""
        clean = {k: v for k, v in kwargs.items() if v is not None}
        if clean:
            await self.cfg.update_one({'_id': 'bot_settings'}, {'$set': clean}, upsert=True)
            _cache_invalidate("bot_settings")
        return await self.get_bot_settings()


db = Database(Config.DB_URL, Config.DB_NAME)
