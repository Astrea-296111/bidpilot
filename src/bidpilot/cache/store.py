import asyncio
import json
import logging
import time
from typing import Protocol

logger = logging.getLogger(__name__)


class Cache(Protocol):
    async def get(self, key: str): ...
    async def set(self, key: str, value, ttl: int = 300): ...
    async def increment(self, key: str, ttl: int = 60) -> int: ...


class MemoryCache:
    def __init__(self):
        self.data = {}
        self.lock = asyncio.Lock()

    async def get(self, key):
        item = self.data.get(key)
        if item and item[0] > time.monotonic():
            return item[1]
        self.data.pop(key, None)
        return None

    async def set(self, key, value, ttl=300):
        if len(self.data) > 10000:
            self.data = {k: v for k, v in self.data.items() if v[0] > time.monotonic()}
            if len(self.data) > 10000:
                self.data.pop(next(iter(self.data)))
        self.data[key] = (time.monotonic() + ttl, value)

    async def increment(self, key, ttl=60):
        async with self.lock:
            count = await self.get(key)
            if count is None:
                await self.set(key, 1, ttl)
                return 1
            self.data[key] = (self.data[key][0], count + 1)
            return count + 1

    async def close(self):
        pass


class RedisCache(MemoryCache):
    """Redis failure degrades to a per-process cache; health exposes degradation."""

    def __init__(self, url):
        super().__init__()
        from redis.asyncio import Redis

        self.redis = Redis.from_url(
            url, decode_responses=True, socket_timeout=2, socket_connect_timeout=2
        )
        self.degraded = False

    async def get(self, key):
        try:
            value = await self.redis.get(key)
            self.degraded = False
            return json.loads(value) if value else None
        except Exception:
            self.degraded = True
            return await super().get(key)

    async def set(self, key, value, ttl=300):
        await super().set(key, value, ttl)
        try:
            await self.redis.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)
            self.degraded = False
        except Exception:
            self.degraded = True
            logger.warning("Redis unavailable; using memory cache")

    async def increment(self, key, ttl=60):
        try:
            return int(
                await self.redis.eval(
                    "local n=redis.call('INCR',KEYS[1]); if n==1 then "
                    "redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n",
                    1,
                    key,
                    ttl,
                )
            )
        except Exception:
            self.degraded = True
            # Do not dynamically dispatch get/set back into broken Redis.
            async with self.lock:
                item = self.data.get(key)
                if not item or item[0] <= time.monotonic():
                    self.data[key] = (time.monotonic() + ttl, 1)
                else:
                    self.data[key] = (item[0], item[1] + 1)
                return self.data[key][1]

    async def close(self):
        await self.redis.aclose()
