"""LLM caller with multi-model support and long context management"""

import json
import time
import hashlib
from pathlib import Path
from typing import Optional
from openai import OpenAI, AsyncOpenAI
from litellm import acompletion, completion
from .config import LLMConfig


class LLMCaller:
    """Handles LLM API calls with retry, caching, and context management"""
    
    def __init__(self, config: LLMConfig, cache_dir: str = ".cache"):
        self.config = config
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._client: Optional[OpenAI] = None
        self._async_client: Optional[AsyncOpenAI] = None
    
    @property
    def client(self) -> OpenAI:
        if self._client is None:
            kwargs = {
                "api_key": self.config.api_key,
                "timeout": self.config.timeout,
            }
            if self.config.api_base:
                kwargs["base_url"] = self.config.api_base
            if self.config.provider == "openai":
                self._client = OpenAI(**kwargs)
            else:
                kwargs["base_url"] = self.config.api_base or self._get_provider_url()
                self._client = OpenAI(**kwargs)
        return self._client
    
    def _get_provider_url(self) -> str:
        urls = {
            "deepseek": "https://api.deepseek.com/v1",
            "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "zhipu": "https://open.bigmodel.cn/api/paas/v4",
            "moonshot": "https://api.moonshot.cn/v1",
        }
        return urls.get(self.config.provider, "https://api.openai.com/v1")
    
    def _get_cache_key(self, messages: list[dict]) -> str:
        content = json.dumps(messages, sort_keys=True)
        return hashlib.md5(content.encode()).hexdigest()
    
    def _get_cached_response(self, key: str) -> Optional[str]:
        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists():
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("response")
        return None
    
    def _cache_response(self, key: str, response: str, usage: dict):
        cache_file = self.cache_dir / f"{key}.json"
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({
                "response": response,
                "usage": usage,
                "timestamp": time.time(),
            }, f, ensure_ascii=False, indent=2)
    
    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        use_cache: bool = True,
    ) -> tuple[str, dict]:
        """
        Call LLM with retry logic.
        Returns: (response_text, usage_info)
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        
        if use_cache:
            cache_key = self._get_cache_key(messages)
            cached = self._get_cached_response(cache_key)
            if cached:
                return cached, {"cached": True}
        
        temp = temperature if temperature is not None else self.config.temperature
        tokens = max_tokens if max_tokens is not None else self.config.max_tokens
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if self.config.provider == "openai" or not self.config.api_base:
                    response = self.client.chat.completions.create(
                        model=self.config.model,
                        messages=messages,
                        temperature=temp,
                        max_tokens=tokens,
                    )
                else:
                    response = completion(
                        model=f"{self.config.provider}/{self.config.model}",
                        messages=messages,
                        temperature=temp,
                        max_tokens=tokens,
                        api_base=self.config.api_base or self._get_provider_url(),
                        api_key=self.config.api_key,
                    )
                
                result = response.choices[0].message.content
                usage = {
                    "prompt_tokens": getattr(response.usage, "prompt_tokens", 0),
                    "completion_tokens": getattr(response.usage, "completion_tokens", 0),
                    "total_tokens": getattr(response.usage, "total_tokens", 0),
                }
                
                if use_cache:
                    self._cache_response(cache_key, result, usage)
                
                return result, usage
                
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                wait_time = 2 ** attempt
                time.sleep(wait_time)
    
    async def acall(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        use_cache: bool = True,
    ) -> tuple[str, dict]:
        """Async version of call"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        
        if use_cache:
            cache_key = self._get_cache_key(messages)
            cached = self._get_cached_response(cache_key)
            if cached:
                return cached, {"cached": True}
        
        temp = temperature if temperature is not None else self.config.temperature
        tokens = max_tokens if max_tokens is not None else self.config.max_tokens
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await acompletion(
                    model=f"{self.config.provider}/{self.config.model}" if self.config.provider != "openai" else self.config.model,
                    messages=messages,
                    temperature=temp,
                    max_tokens=tokens,
                    api_base=self.config.api_base or self._get_provider_url() if self.config.provider != "openai" else None,
                    api_key=self.config.api_key if self.config.provider != "openai" else None,
                )
                
                result = response.choices[0].message.content
                usage = {
                    "prompt_tokens": getattr(response.usage, "prompt_tokens", 0),
                    "completion_tokens": getattr(response.usage, "completion_tokens", 0),
                    "total_tokens": getattr(response.usage, "total_tokens", 0),
                }
                
                if use_cache:
                    cache_key = self._get_cache_key(messages)
                    self._cache_response(cache_key, result, usage)
                
                return result, usage
                
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                wait_time = 2 ** attempt
                time.sleep(wait_time)
    
    def estimate_tokens(self, text: str) -> int:
        """Rough estimate of token count (Chinese chars ~1.5 tokens, English ~0.3)"""
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        return int(chinese_chars * 1.5 + other_chars * 0.3)
