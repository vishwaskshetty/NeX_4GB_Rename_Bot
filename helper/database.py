import motor.motor_asyncio
from config import Config
from .utils import send_log


class Database:

    def __init__(self, uri, database_name):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.col = self.db.user

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
            upload_mode="Ask"
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
            return "Telegram : @Nex_bots"
        return user.get('metadata_code', "Telegram : @Nex_bots")

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
                "upload_mode": "Ask"
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
            "upload_mode": user.get('upload_mode', "Ask")
        }


db = Database(Config.DB_URL, Config.DB_NAME)
