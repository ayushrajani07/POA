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
import os
import sys

# Add path for imports
sys.path.append(str(Path(__file__).parent.parent) if '__file__' in locals() else '.')

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
            position=int(data['position']),
            last_updated=float(data['last_updated']),
            checksum=data.get('checksum', '')
        )

class RedisCoordinator:
    """Redis-based coordination for distributed file operations and caching"""
    
    def __init__(self, redis_host: str = "localhost", redis_port: int = 6379, redis_db: int = 0, redis_password: Optional[str] = None):
        try:
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                password=redis_password,
                socket_timeout=5.0,
                retry_on_timeout=True,
                decode_responses=True
            )
            # Test connection
            self.redis_client.ping()
            self.connected = True
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}. Operating in standalone mode.")
            self.redis_client = None
            self.connected = False
        
        self._local_locks = {}
        self._local_lock = Lock()
        self._cursors = {}  # Fallback cursor storage
        
    def ping(self) -> bool:
        """Test Redis connectivity"""
        try:
            if self.redis_client:
                return self.redis_client.ping()
            return False
        except Exception as e:
            logger.error(f"Redis ping failed: {e}")
            return False
    
    @contextmanager
    def distributed_lock(self, lock_name: str, timeout: int = 30, retry_delay: float = 0.1):
        """
        Distributed lock using Redis to prevent Windows file lock conflicts.
        Falls back to local locking if Redis unavailable.
        
        Args:
            lock_name: Unique identifier for the lock
            timeout: Maximum time to hold the lock
            retry_delay: Delay between lock acquisition attempts
        """
        if not self.connected:
            # Fallback to local locking
            with self._local_lock:
                if lock_name not in self._local_locks:
                    self._local_locks[lock_name] = Lock()
            
            with self._local_locks[lock_name]:
                yield
            return
        
        # Redis distributed locking
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
                logger.warning(f"Could not acquire lock {lock_name} within {timeout} seconds")
                # Still proceed, but with warning
            
            yield
            
        finally:
            if acquired and self.redis_client:
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
        
        if not self.connected:
            # Fallback to local storage
            self._cursors[file_path] = cursor
            return True
        
        try:
            self.redis_client.hset(cursor_key, mapping=cursor.to_dict())
            self.redis_client.expire(cursor_key, 86400)  # 24 hour TTL
            return True
        except Exception as e:
            logger.error(f"Failed to set cursor for {file_path}: {e}")
            # Fallback to local storage
            self._cursors[file_path] = cursor
            return False
    
    def get_file_cursor(self, file_path: str) -> Optional[CursorPosition]:
        """Get cursor position for incremental file reading"""
        if not self.connected:
            # Fallback to local storage
            return self._cursors.get(file_path)
        
        cursor_key = f"cursor:{self._hash_file_path(file_path)}"
        try:
            cursor_data = self.redis_client.hgetall(cursor_key)
            if cursor_data:
                return CursorPosition.from_dict(cursor_data)
            return None
        except Exception as e:
            logger.error(f"Failed to get cursor for {file_path}: {e}")
            # Fallback to local storage
            return self._cursors.get(file_path)
    
    def clear_file_cursor(self, file_path: str) -> bool:
        """Clear cursor for a file"""
        if not self.connected:
            # Fallback to local storage
            if file_path in self._cursors:
                del self._cursors[file_path]
                return True
            return False
        
        cursor_key = f"cursor:{self._hash_file_path(file_path)}"
        try:
            result = bool(self.redis_client.delete(cursor_key))
            # Also clear from local fallback
            if file_path in self._cursors:
                del self._cursors[file_path]
            return result
        except Exception as e:
            logger.error(f"Failed to clear cursor for {file_path}: {e}")
            return False
    
    def cache_set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """Set a cached value with TTL"""
        if not self.connected:
            return False
        
        try:
            serialized_value = json.dumps(value) if not isinstance(value, str) else value
            return self.redis_client.setex(key, ttl, serialized_value)
        except Exception as e:
            logger.error(f"Failed to cache value for key {key}: {e}")
            return False
    
    def cache_get(self, key: str) -> Optional[Any]:
        """Get a cached value"""
        if not self.connected:
            return None
        
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
        if not self.connected:
            return False
        
        try:
            return bool(self.redis_client.delete(key))
        except Exception as e:
            logger.error(f"Failed to delete cached key {key}: {e}")
            return False
    
    def publish_message(self, channel: str, message: Dict[str, Any]) -> bool:
        """Publish a message to a Redis channel"""
        if not self.connected:
            return False
        
        try:
            serialized_message = json.dumps(message)
            return bool(self.redis_client.publish(channel, serialized_message))
        except Exception as e:
            logger.error(f"Failed to publish message to {channel}: {e}")
            return False
    
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
        if not self.connected:
            return []
        
        try:
            keys = self.redis_client.keys("health:*")
            return [key.split(":", 1)[1] for key in keys]
        except Exception as e:
            logger.error(f"Failed to get active services: {e}")
            return []
    
    def _hash_file_path(self, file_path: str) -> str:
        """Create a hash of the file path for Redis key"""
        return hashlib.md5(file_path.encode()).hexdigest()
    
    def cleanup_expired_cursors(self, max_age_hours: int = 24) -> int:
        """Clean up old cursor positions"""
        if not self.connected:
            # Clean local cursors
            cutoff_time = time.time() - (max_age_hours * 3600)
            cleaned = 0
            for file_path, cursor in list(self._cursors.items()):
                if cursor.last_updated < cutoff_time:
                    del self._cursors[file_path]
                    cleaned += 1
            return cleaned
        
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
    
    def __init__(self, redis_coordinator: Optional[RedisCoordinator] = None):
        self.redis_coord = redis_coordinator or get_redis_coordinator()
    
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
_redis_coordinator = None
_file_coordinator = None

def get_redis_coordinator() -> RedisCoordinator:
    """Get the global Redis coordinator instance"""
    global _redis_coordinator
    if _redis_coordinator is None:
        # Get Redis connection details from environment
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        redis_db = int(os.getenv("REDIS_DB", "0"))
        redis_password = os.getenv("REDIS_PASSWORD")
        
        _redis_coordinator = RedisCoordinator(
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
            redis_password=redis_password
        )
    return _redis_coordinator

def get_file_coordinator() -> FileCoordinator:
    """Get the global file coordinator instance"""
    global _file_coordinator
    if _file_coordinator is None:
        _file_coordinator = FileCoordinator()
    return _file_coordinator

# Health check function
def check_coordination_health() -> Dict[str, Any]:
    """Check the health of the coordination system"""
    coordinator = get_redis_coordinator()
    
    health = {
        'redis_connected': False,
        'active_services': [],
        'active_locks': 0,
        'active_cursors': 0,
        'timestamp': time.time(),
        'fallback_mode': not coordinator.connected
    }
    
    try:
        health['redis_connected'] = coordinator.ping()
        if health['redis_connected']:
            health['active_services'] = coordinator.get_active_services()
            
            # Count active locks and cursors
            try:
                if coordinator.redis_client:
                    lock_keys = coordinator.redis_client.keys("lock:*")
                    cursor_keys = coordinator.redis_client.keys("cursor:*")
                    health['active_locks'] = len(lock_keys)
                    health['active_cursors'] = len(cursor_keys)
            except Exception as e:
                logger.warning(f"Failed to count active locks/cursors: {e}")
        else:
            # Report fallback stats
            health['active_cursors'] = len(coordinator._cursors)
                
    except Exception as e:
        logger.error(f"Coordination health check failed: {e}")
    
    return health

# Convenience functions for common file operations
def read_with_coordination(file_path: str, mode: str = 'r', **kwargs):
    """Read a file with coordination to avoid conflicts"""
    from pathlib import Path
    
    coordinator = get_file_coordinator()
    with coordinator.coordinated_file_read(file_path):
        with open(file_path, mode, **kwargs) as f:
            return f.read()

def write_with_coordination(file_path: str, content: str, mode: str = 'w', **kwargs):
    """Write to a file with coordination to avoid conflicts"""
    from pathlib import Path
    
    # Ensure directory exists
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)
    
    coordinator = get_file_coordinator()
    with coordinator.coordinated_file_write(file_path):
        with open(file_path, mode, **kwargs) as f:
            return f.write(content)

def append_with_coordination(file_path: str, content: str, **kwargs):
    """Append to a file with coordination to avoid conflicts"""
    return write_with_coordination(file_path, content, mode='a', **kwargs)

# Example usage and testing
if __name__ == "__main__":
    import tempfile
    from pathlib import Path
    
    # Test coordination system
    print("=== Coordination System Demo ===")
    
    # Check health
    health = check_coordination_health()
    print(f"Coordination Health: {health}")
    
    # Test Redis coordinator
    coordinator = get_redis_coordinator()
    print(f"Redis Connected: {coordinator.connected}")
    
    # Test distributed locking
    lock_name = "test_lock"
    print(f"\nTesting distributed lock: {lock_name}")
    
    with coordinator.distributed_lock(lock_name, timeout=10):
        print("Lock acquired successfully")
        time.sleep(1)
    print("Lock released")
    
    # Test file cursor operations
    test_file = "/tmp/test_file.csv"
    print(f"\nTesting cursor operations for: {test_file}")
    
    # Set cursor
    result = coordinator.set_file_cursor(test_file, 1024, "checksum123")
    print(f"Set cursor result: {result}")
    
    # Get cursor
    cursor = coordinator.get_file_cursor(test_file)
    print(f"Retrieved cursor: {cursor}")
    
    # Test file coordination
    file_coordinator = get_file_coordinator()
    
    # Create a test file
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        test_file_path = f.name
        f.write("ts,index,last_price\n")
        f.write("2025-08-24 14:30:00,NIFTY,100.50\n")
    
    print(f"\nTesting coordinated file operations: {test_file_path}")
    
    # Test coordinated reading
    with file_coordinator.coordinated_file_read(test_file_path):
        with open(test_file_path, 'r') as f:
            content = f.read()
            print(f"Read content: {content.strip()}")
    
    # Test coordinated writing
    with file_coordinator.coordinated_file_write(test_file_path):
        with open(test_file_path, 'a') as f:
            f.write("2025-08-24 14:31:00,NIFTY,101.00\n")
    
    print("Coordinated write completed")
    
    # Test incremental cursor
    position = file_coordinator.get_incremental_cursor(test_file_path)
    print(f"Current cursor position: {position}")
    
    # Update cursor
    new_position = 50
    result = file_coordinator.update_incremental_cursor(test_file_path, new_position, "new_checksum")
    print(f"Updated cursor to {new_position}: {result}")
    
    # Verify updated cursor
    updated_position = file_coordinator.get_incremental_cursor(test_file_path)
    print(f"Verified cursor position: {updated_position}")
    
    # Cleanup
    Path(test_file_path).unlink(missing_ok=True)
    print("\nDemo completed successfully!")