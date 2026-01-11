"""
Base Provider Interface for Research Services

All research providers (LinkedIn, Web Search, Scrapers) inherit from BaseProvider.
This ensures consistent interfaces, caching, rate limiting, and error handling.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, TypeVar, Generic
import hashlib
import json

logger = logging.getLogger("Jarvis.Research.Provider")


class ProviderStatus(Enum):
    """Status of provider operations."""
    SUCCESS = "success"
    ERROR = "error"
    RATE_LIMITED = "rate_limited"
    NOT_FOUND = "not_found"
    TIMEOUT = "timeout"
    PENDING = "pending"  # For async operations


@dataclass
class ProviderResult:
    """
    Standard result wrapper for all provider operations.
    
    Attributes:
        status: Operation status (success, error, etc.)
        data: The actual result data (type varies by operation)
        error: Error message if status is ERROR
        metadata: Additional info (request_id, cost, cache_hit, etc.)
        raw_response: Original API response for debugging
    """
    status: ProviderStatus
    data: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    raw_response: Optional[Dict] = None
    
    @property
    def is_success(self) -> bool:
        return self.status == ProviderStatus.SUCCESS
    
    @property
    def is_error(self) -> bool:
        return self.status == ProviderStatus.ERROR
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "status": self.status.value,
            "data": self.data,
            "error": self.error,
            "metadata": self.metadata,
        }
    
    @classmethod
    def success(cls, data: Any, **metadata) -> "ProviderResult":
        """Factory for success results."""
        return cls(status=ProviderStatus.SUCCESS, data=data, metadata=metadata)
    
    @classmethod
    def failure(cls, error: str, **metadata) -> "ProviderResult":
        """Factory for error results."""
        return cls(status=ProviderStatus.ERROR, error=error, metadata=metadata)


# Simple TTL cache for provider results
_provider_cache: Dict[str, tuple] = {}  # {cache_key: (expires_at, result)}
_CACHE_DEFAULT_TTL = 3600  # 1 hour default
_CACHE_MAX_SIZE = 500


def _cache_key(provider: str, operation: str, params: Dict) -> str:
    """Generate a deterministic cache key."""
    params_str = json.dumps(params, sort_keys=True)
    key_str = f"{provider}:{operation}:{params_str}"
    return hashlib.sha256(key_str.encode()).hexdigest()[:32]


def _get_cached(key: str) -> Optional[ProviderResult]:
    """Get cached result if not expired."""
    if key in _provider_cache:
        expires_at, result = _provider_cache[key]
        if datetime.now(timezone.utc).timestamp() < expires_at:
            return result
        else:
            del _provider_cache[key]
    return None


def _set_cached(key: str, result: ProviderResult, ttl: int = _CACHE_DEFAULT_TTL):
    """Cache a result with TTL."""
    # Evict old entries if cache is full
    if len(_provider_cache) >= _CACHE_MAX_SIZE:
        now = datetime.now(timezone.utc).timestamp()
        expired = [k for k, (exp, _) in _provider_cache.items() if exp < now]
        for k in expired[:100]:  # Remove up to 100 expired entries
            del _provider_cache[k]
    
    expires_at = datetime.now(timezone.utc).timestamp() + ttl
    _provider_cache[key] = (expires_at, result)


class BaseProvider(ABC):
    """
    Abstract base class for all research providers.
    
    Providers must implement:
    - name: Unique provider identifier
    - _execute: The actual API call logic
    
    Features provided by base:
    - Automatic caching with TTL
    - Rate limiting (TODO)
    - Retry logic (TODO)
    - Unified error handling
    - Logging
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for this provider (e.g., 'brightdata_linkedin')."""
        pass
    
    @abstractmethod
    async def _execute(self, operation: str, params: Dict[str, Any]) -> ProviderResult:
        """
        Execute the actual provider operation.
        
        Args:
            operation: The operation to perform (e.g., 'search_profiles', 'get_company')
            params: Operation-specific parameters
            
        Returns:
            ProviderResult with data or error
        """
        pass
    
    async def execute(
        self,
        operation: str,
        params: Dict[str, Any],
        use_cache: bool = True,
        cache_ttl: int = _CACHE_DEFAULT_TTL
    ) -> ProviderResult:
        """
        Execute an operation with caching and error handling.
        
        Args:
            operation: Operation to perform
            params: Operation parameters
            use_cache: Whether to check/update cache
            cache_ttl: Cache TTL in seconds
            
        Returns:
            ProviderResult
        """
        # Check cache first
        cache_key = _cache_key(self.name, operation, params)
        if use_cache:
            cached = _get_cached(cache_key)
            if cached:
                logger.debug(f"{self.name}.{operation}: cache hit")
                cached.metadata["cache_hit"] = True
                return cached
        
        # Execute operation
        try:
            logger.info(f"{self.name}.{operation}: executing")
            result = await self._execute(operation, params)
            
            # Cache successful results
            if result.is_success and use_cache:
                _set_cached(cache_key, result, cache_ttl)
                result.metadata["cache_hit"] = False
            
            return result
            
        except Exception as e:
            logger.error(f"{self.name}.{operation} failed: {e}", exc_info=True)
            return ProviderResult.failure(str(e))
    
    @abstractmethod
    def get_operations(self) -> List[Dict[str, Any]]:
        """
        Return list of available operations for this provider.
        
        Each operation should have:
        - name: Operation identifier
        - description: What it does
        - parameters: List of required/optional params
        
        Used to generate tool definitions for chat/agents.
        """
        pass
    
    def to_tool_definitions(self) -> List[Dict[str, Any]]:
        """
        Convert provider operations to Claude tool format.
        
        Returns list of tool definitions compatible with chat service.
        """
        tools = []
        for op in self.get_operations():
            tool = {
                "name": f"{self.name}_{op['name']}",
                "description": op.get("description", ""),
                "input_schema": {
                    "type": "object",
                    "properties": op.get("parameters", {}),
                    "required": op.get("required", [])
                }
            }
            tools.append(tool)
        return tools
