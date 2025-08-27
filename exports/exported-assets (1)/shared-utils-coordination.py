"""
Redis-based coordination utilities to solve Windows file lock contention.
Provides distributed locking and coordination between services.
"""

import redis
import time
import logging
import uuid
from typing import Optional, Any, Dict, List
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Lock
import json
import hashlib

from ..config.settings import get_settings

logger = logging.getLogger(__name__)

@dataclass
class CursorPosition:
    """Represents a cursor position for incremental reading"""
    file_path: str
    position: int
    last_updated: float
    checksum: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'file_path': self.file_path,
            'position': self.position,
            'last_updated': self.last_updated,
            'checksum': self.checksum
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CursorPosition':
        return cls(
            file_path=data['file_path'],
            position=data['position'],
            last_updated=data['last_updated'],
            checksum=data.get('checksum', '')
        )

class RedisCoordinator:
    """Redis-based coordination for distributed file operations and caching"""
    
    def __init__(self):
        settings = get_settings()
        self.redis_client = redis.Redis(
            host=settings.redis.host,
            port=settings.redis.port,
            db=settings.redis.db,
            password=settings.redis.password,
            socket_timeout=settings.redis.socket_timeout,
            retry_on_timeout=settings.redis.retry_on_timeout,
            decode_responses=True
        )
        self._local_locks = {}
        self._local_lock = Lock()
        
    def ping(self) -> bool:
        """Test Redis connectivity"""
        try:
            return self.redis_client.ping()
        except Exception as e:
            logger.error(f"Redis ping failed: {e}")
            return False
    
    @contextmanager
    def distributed_lock(self, lock_name: str, timeout: int = 30, retry_delay: float = 0.1):
        """
        Distributed lock using Redis to prevent Windows file lock conflicts.
        
        Args:
            lock_name: Unique identifier for the lock
            timeout: Maximum time to hold the lock
            retry_delay: Delay between lock acquisition attempts
        """
        lock_key = f"lock:{lock_name}"
        lock_value = str(uuid.uuid4())
        acquired = False
        
        try:
            # Try to acquire the lock with exponential backoff
            start_time = time.time()
            attempt = 0
            
            while time.time() - start_time < timeout:
                if self.redis_client.set(lock_key, lock_value, nx=True, ex=timeout):
                    acquired = True
                    logger.debug(f"Acquired distributed lock: {lock_name}")
                    break
                
                # Exponential backoff with jitter
                delay = min(retry_delay * (2 ** attempt) + (time.time() % 0.1), 2.0)
                time.sleep(delay)
                attempt += 1
            
            if not acquired:
                raise TimeoutError(f"Could not acquire lock {lock_name} within {timeout} seconds")
            
            yield
            
        finally:
            if acquired:
                # Only release if we own the lock
                lua_script = """
                if redis.call("GET", KEYS[1]) == ARGV[1] then
                    return redis.call("DEL", KEYS[1])
                else
                    return 0
                end
                """
                try:
                    self.redis_client.eval(lua_script, 1, lock_key, lock_value)
                    logger.debug(f"Released distributed lock: {lock_name}")
                except Exception as e:
                    logger.warning(f"Failed to release lock {lock_name}: {e}")
    
    def set_file_cursor(self, file_path: str, position: int, checksum: str = "") -> bool:
        """Set cursor position for incremental file reading"""
        cursor = CursorPosition(
            file_path=file_path,
            position=position,
            last_updated=time.time(),
            checksum=checksum
        )
        
        cursor_key = f"cursor:{self._hash_file_path(file_path)}"
        try:
            self.redis_client.hset(cursor_key, mapping=cursor.to_dict())
            self.redis_client.expire(cursor_key, 86400)  # 24 hour TTL
            return True
        except Exception as e:
            logger.error(f"Failed to set cursor for {file_path}: {e}")
            return False
    
    def get_file_cursor(self, file_path: str) -> Optional[CursorPosition]:
        """Get cursor position for incremental file reading"""
        cursor_key = f"cursor:{self._hash_file_path(file_path)}"
        try:
            cursor_data = self.redis_client.hgetall(cursor_key)
            if cursor_data:
                return CursorPosition.from_dict({
                    k: float(v) if k in ['position', 'last_updated'] else v 
                    for k, v in cursor_data.items()
                })
            return None
        except Exception as e:
            logger.error(f"Failed to get cursor for {file_path}: {e}")
            return None
    
    def clear_file_cursor(self, file_path: str) -> bool:
        """Clear cursor for a file"""
        cursor_key = f"cursor:{self._hash_file_path(file_path)}"
        try:
            return bool(self.redis_client.delete(cursor_key))
        except Exception as e:
            logger.error(f"Failed to clear cursor for {file_path}: {e}")
            return False
    
    def cache_set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """Set a cached value with TTL"""
        try:
            serialized_value = json.dumps(value) if not isinstance(value, str) else value
            return self.redis_client.setex(key, ttl, serialized_value)
        except Exception as e:
            logger.error(f"Failed to cache value for key {key}: {e}")
            return False
    
    def cache_get(self, key: str) -> Optional[Any]:
        """Get a cached value"""
        try:
            value = self.redis_client.get(key)
            if value is None:
                return None
            
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        except Exception as e:
            logger.error(f"Failed to get cached value for key {key}: {e}")
            return None
    
    def cache_delete(self, key: str) -> bool:
        """Delete a cached value"""
        try:
            return bool(self.redis_client.delete(key))
        except Exception as e:
            logger.error(f"Failed to delete cached key {key}: {e}")
            return False
    
    def publish_message(self, channel: str, message: Dict[str, Any]) -> bool:
        """Publish a message to a Redis channel"""
        try:
            serialized_message = json.dumps(message)
            return bool(self.redis_client.publish(channel, serialized_message))
        except Exception as e:
            logger.error(f"Failed to publish message to {channel}: {e}")
            return False
    
    def subscribe_to_channel(self, channel: str):
        """Subscribe to a Redis channel"""
        try:
            pubsub = self.redis_client.pubsub()
            pubsub.subscribe(channel)
            return pubsub
        except Exception as e:
            logger.error(f"Failed to subscribe to channel {channel}: {e}")
            return None
    
    def get_service_health(self, service_name: str) -> Optional[Dict[str, Any]]:
        """Get health status of a service"""
        health_key = f"health:{service_name}"
        return self.cache_get(health_key)
    
    def set_service_health(self, service_name: str, health_data: Dict[str, Any], ttl: int = 60) -> bool:
        """Set health status of a service"""
        health_key = f"health:{service_name}"
        health_data['timestamp'] = time.time()
        return self.cache_set(health_key, health_data, ttl)
    
    def get_active_services(self) -> List[str]:
        """Get list of active services"""
        try:
            keys = self.redis_client.keys("health:*")
            return [key.split(":", 1)[1] for key in keys]
        except Exception as e:
            logger.error(f"Failed to get active services: {e}")
            return []
    
    def coordinate_batch_write(self, batch_id: str, total_writers: int, timeout: int = 300) -> bool:
        """
        Coordinate batch writing across multiple services.
        Returns True when all writers have completed.
        """
        batch_key = f"batch:{batch_id}"
        writer_id = str(uuid.uuid4())
        
        try:
            # Register this writer
            self.redis_client.sadd(f"{batch_key}:writers", writer_id)
            self.redis_client.expire(f"{batch_key}:writers", timeout)
            
            # Signal completion
            self.redis_client.sadd(f"{batch_key}:completed", writer_id)
            self.redis_client.expire(f"{batch_key}:completed", timeout)
            
            # Check if all writers completed
            completed_count = self.redis_client.scard(f"{batch_key}:completed")
            return completed_count >= total_writers
            
        except Exception as e:
            logger.error(f"Failed to coordinate batch write {batch_id}: {e}")
            return False
    
    def _hash_file_path(self, file_path: str) -> str:
        """Create a hash of the file path for Redis key"""
        return hashlib.md5(file_path.encode()).hexdigest()
    
    def cleanup_expired_cursors(self, max_age_hours: int = 24) -> int:
        """Clean up old cursor positions"""
        try:
            cursor_keys = self.redis_client.keys("cursor:*")
            cleaned = 0
            cutoff_time = time.time() - (max_age_hours * 3600)
            
            for key in cursor_keys:
                cursor_data = self.redis_client.hgetall(key)
                if cursor_data and float(cursor_data.get('last_updated', 0)) < cutoff_time:
                    self.redis_client.delete(key)
                    cleaned += 1
            
            logger.info(f"Cleaned up {cleaned} expired cursors")
            return cleaned
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired cursors: {e}")
            return 0

class FileCoordinator:
    """High-level file coordination utilities using Redis"""
    
    def __init__(self):
        self.redis_coord = RedisCoordinator()
    
    @contextmanager
    def coordinated_file_write(self, file_path: str, timeout: int = 30):
        """
        Context manager for coordinated file writing.
        Solves Windows file lock contention by using distributed locking.
        """
        lock_name = f"file_write:{self.redis_coord._hash_file_path(file_path)}"
        
        with self.redis_coord.distributed_lock(lock_name, timeout):
            yield
    
    @contextmanager
    def coordinated_file_read(self, file_path: str, timeout: int = 10):
        """
        Context manager for coordinated file reading.
        Allows multiple readers but coordinates with writers.
        """
        lock_name = f"file_read:{self.redis_coord._hash_file_path(file_path)}"
        
        with self.redis_coord.distributed_lock(lock_name, timeout):
            yield
    
    def get_incremental_cursor(self, file_path: str) -> int:
        """Get the current cursor position for incremental reading"""
        cursor = self.redis_coord.get_file_cursor(file_path)
        return cursor.position if cursor else 0
    
    def update_incremental_cursor(self, file_path: str, position: int, checksum: str = "") -> bool:
        """Update cursor position after incremental reading"""
        return self.redis_coord.set_file_cursor(file_path, position, checksum)

# Global coordinator instances
redis_coordinator = RedisCoordinator()
file_coordinator = FileCoordinator()

def get_redis_coordinator() -> RedisCoordinator:
    """Get the global Redis coordinator instance"""
    return redis_coordinator

def get_file_coordinator() -> FileCoordinator:
    """Get the global file coordinator instance"""
    return file_coordinator

# Health check function
def check_coordination_health() -> Dict[str, Any]:
    """Check the health of the coordination system"""
    coordinator = get_redis_coordinator()
    
    health = {
        'redis_connected': False,
        'active_services': [],
        'active_locks': 0,
        'active_cursors': 0,
        'timestamp': time.time()
    }
    
    try:
        health['redis_connected'] = coordinator.ping()
        if health['redis_connected']:
            health['active_services'] = coordinator.get_active_services()
            
            # Count active locks and cursors
            try:
                lock_keys = coordinator.redis_client.keys("lock:*")
                cursor_keys = coordinator.redis_client.keys("cursor:*")
                health['active_locks'] = len(lock_keys)
                health['active_cursors'] = len(cursor_keys)
            except Exception as e:
                logger.warning(f"Failed to count active locks/cursors: {e}")
                
    except Exception as e:
        logger.error(f"Coordination health check failed: {e}")
    
    return health