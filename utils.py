import random
import redis
from config import Config

def generate_verification_code():
    return str(random.randint(100000, 999999))

def get_redis_connection():
    return redis.Redis.from_url(Config.REDIS_URL)

def store_verification_data(phone, data):
    r = get_redis_connection()
    key = f"famelees:verification:{phone}"
    r.setex(key, Config.SESSION_TTL, data)
    return key

def get_verification_data(phone):
    r = get_redis_connection()
    key = f"famelees:verification:{phone}"
    data = r.get(key)
    return data.decode('utf-8') if data else None

def delete_verification_data(phone):
    r = get_redis_connection()
    key = f"famelees:verification:{phone}"
    r.delete(key)
