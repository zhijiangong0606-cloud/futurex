from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from ..core.constants import REST_WEIGHT_LIMIT, REST_WEIGHT_WARN_THRESHOLD
from ..core.logging import get_logger

log = get_logger("futurex.data.rest_client")

_ENDPOINT_WEIGHTS: dict[str, int] = {
    "POST /fapi/v1/order": 1,
    "DELETE /fapi/v1/order": 1,
    "POST /fapi/v1/batchOrders": 5,
    "GET /fapi/v1/klines": 5,
    "GET /fapi/v2/account": 5,
    "GET /fapi/v2/balance": 5,
    "GET /fapi/v1/depth": 5,
    "POST /fapi/v1/listenKey": 1,
    "PUT /fapi/v1/listenKey": 1,
    "DELETE /fapi/v1/listenKey": 1,
    "GET /fapi/v1/exchangeInfo": 1,
    "POST /fapi/v1/leverage": 1,
    "POST /fapi/v1/marginType": 1,
}


class RateLimiter:
    def __init__(self, max_weight: int = REST_WEIGHT_LIMIT) -> None:
        self._max_weight = max_weight
        self._used_weight = 0
        self._window_start = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, weight: int) -> float:
        async with self._lock:
            now = time.monotonic()
            if now - self._window_start >= 60:
                self._used_weight = 0
                self._window_start = now

            if self._used_weight + weight > self._max_weight * REST_WEIGHT_WARN_THRESHOLD:
                wait_time = 60 - (now - self._window_start)
                if wait_time > 0:
                    log.warning(
                        "rate_limit_throttle",
                        used=self._used_weight,
                        max=self._max_weight,
                        wait=f"{wait_time:.1f}s",
                    )
                    return wait_time

            self._used_weight += weight
            return 0.0

    def sync_from_header(self, used: int) -> None:
        self._used_weight = used


class RESTClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        api_secret: str,
        proxy_url: str = "",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._api_secret = api_secret
        self._rate_limiter = RateLimiter()
        client_kwargs: dict[str, Any] = {
            "base_url": self._base_url,
            "headers": {"X-MBX-APIKEY": self._api_key},
            "timeout": 10.0,
        }
        if proxy_url:
            client_kwargs["proxy"] = proxy_url
        self._client = httpx.AsyncClient(**client_kwargs)

    async def close(self) -> None:
        await self._client.aclose()

    def _sign(self, params: dict[str, Any]) -> dict[str, Any]:
        params["timestamp"] = int(time.time() * 1000)
        query = urlencode(params)
        signature = hmac.new(
            self._api_secret.encode(), query.encode(), hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        signed: bool = True,
        weight: int | None = None,
    ) -> dict[str, Any]:
        params = params or {}
        endpoint_key = f"{method.upper()} {path}"
        w = weight or _ENDPOINT_WEIGHTS.get(endpoint_key, 1)

        wait = await self._rate_limiter.acquire(w)
        if wait > 0:
            await asyncio.sleep(wait)
            await self._rate_limiter.acquire(w)

        if signed:
            params = self._sign(params)

        max_retries = 3
        for attempt in range(max_retries):
            try:
                if method.upper() == "GET":
                    resp = await self._client.get(path, params=params)
                elif method.upper() == "POST":
                    resp = await self._client.post(path, params=params)
                elif method.upper() == "PUT":
                    resp = await self._client.put(path, params=params)
                elif method.upper() == "DELETE":
                    resp = await self._client.delete(path, params=params)
                else:
                    raise ValueError(f"Unsupported method: {method}")

                used_weight = resp.headers.get("X-MBX-USED-WEIGHT-1M")
                if used_weight:
                    self._rate_limiter.sync_from_header(int(used_weight))

                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", "60"))
                    log.warning("rate_limited", retry_after=retry_after)
                    await asyncio.sleep(retry_after)
                    continue

                if resp.status_code == 418:
                    retry_after = int(resp.headers.get("Retry-After", "120"))
                    log.error("ip_banned", retry_after=retry_after)
                    await asyncio.sleep(retry_after)
                    continue

                resp.raise_for_status()
                return resp.json()

            except httpx.HTTPStatusError as e:
                if attempt < max_retries - 1:
                    delay = 2 ** (attempt + 1)
                    log.warning(
                        "rest_retry",
                        path=path,
                        status=e.response.status_code,
                        attempt=attempt + 1,
                        delay=delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    log.error("rest_failed", path=path, error=str(e))
                    raise
            except Exception as e:
                if attempt < max_retries - 1:
                    delay = 2 ** (attempt + 1)
                    await asyncio.sleep(delay)
                else:
                    raise

        return {}

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
        stop_price: float | None = None,
        time_in_force: str | None = None,
        reduce_only: bool = False,
        close_position: bool = False,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "quantity": f"{quantity:.8f}".rstrip("0").rstrip("."),
        }
        if price is not None:
            params["price"] = f"{price:.8f}".rstrip("0").rstrip(".")
        if stop_price is not None:
            params["stopPrice"] = f"{stop_price:.8f}".rstrip("0").rstrip(".")
        if time_in_force:
            params["timeInForce"] = time_in_force
        if reduce_only:
            params["reduceOnly"] = "true"
        if close_position:
            params["closePosition"] = "true"

        result = await self._request("POST", "/fapi/v1/order", params)
        log.info(
            "order_placed",
            symbol=symbol,
            side=side,
            type=order_type,
            qty=quantity,
            order_id=result.get("orderId"),
        )
        return result

    async def cancel_order(self, symbol: str, order_id: int) -> dict[str, Any]:
        return await self._request(
            "DELETE",
            "/fapi/v1/order",
            {"symbol": symbol, "orderId": order_id},
        )

    async def get_klines(
        self, symbol: str, interval: str, limit: int = 500
    ) -> list[dict[str, Any]]:
        data = await self._request(
            "GET",
            "/fapi/v1/klines",
            {"symbol": symbol, "interval": interval, "limit": limit},
            signed=False,
        )
        candles = []
        for item in data:  # type: ignore[union-attr]
            candles.append(
                {
                    "open_time": item[0],
                    "open": item[1],
                    "high": item[2],
                    "low": item[3],
                    "close": item[4],
                    "volume": item[5],
                    "close_time": item[6],
                    "timestamp": item[0],
                }
            )
        return candles

    async def get_account(self) -> dict[str, Any]:
        return await self._request("GET", "/fapi/v2/account")

    async def set_leverage(self, symbol: str, leverage: int) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/fapi/v1/leverage",
            {"symbol": symbol, "leverage": leverage},
        )

    async def set_margin_type(self, symbol: str, margin_type: str) -> dict[str, Any]:
        try:
            return await self._request(
                "POST",
                "/fapi/v1/marginType",
                {"symbol": symbol, "marginType": margin_type},
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400 and "-4046" in e.response.text:
                return {}
            raise

    async def create_listen_key(self) -> str:
        result = await self._request(
            "POST", "/fapi/v1/listenKey", signed=False
        )
        return result.get("listenKey", "")

    async def renew_listen_key(self) -> None:
        await self._request("PUT", "/fapi/v1/listenKey", signed=False)

    async def get_exchange_info(self) -> dict[str, Any]:
        return await self._request(
            "GET", "/fapi/v1/exchangeInfo", signed=False
        )
