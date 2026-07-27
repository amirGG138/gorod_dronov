"""Inactive high-level client for the isolated commerce runtime.

Nothing in the current agent roles imports or instantiates this module.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import httpx


class _CommerceClientError(RuntimeError):
    pass


class CommerceClient:
    def __init__(
        self,
        base_url: str,
        bearer_credential: str,
        *,
        idempotency_namespace: str,
        timeout_seconds: float = 10,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._bearer = bearer_credential
        self._namespace = idempotency_namespace
        self._owns_http = http_client is None
        self._http = http_client or httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
        )

    def _headers(self, operation: dict[str, Any] | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self._bearer}"}
        if operation is not None:
            canonical = json.dumps(
                operation, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            digest = hashlib.sha256(canonical).hexdigest()[:32]
            headers["Idempotency-Key"] = f"{self._namespace}:{digest}"
        return headers

    def _response(self, response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as error:
            raise _CommerceClientError(
                f"commerce returned HTTP {response.status_code}"
            ) from error
        if response.is_error:
            public_error = body.get("error", {})
            code = public_error.get("code", "HTTP_ERROR")
            message = public_error.get("message", "commerce request failed")
            raise _CommerceClientError(f"{code}: {message}")
        return body

    def list_services(self) -> dict[str, Any]:
        return self._response(
            self._http.get("/v1/services", headers=self._headers())
        )

    def open_negotiation(self, service_id: str) -> dict[str, Any]:
        body = {"service_id": service_id}
        operation = {"method": "open_negotiation", **body}
        return self._response(self._http.post(
            "/v1/negotiations", json=body, headers=self._headers(operation)
        ))

    def act(
        self,
        negotiation_id: str,
        action: str,
        amount_cents: int | None = None,
    ) -> dict[str, Any]:
        body = {"action": action, "amount_cents": amount_cents}
        operation = {
            "method": "act",
            "negotiation_id": negotiation_id,
            **body,
        }
        return self._response(self._http.post(
            f"/v1/negotiations/{negotiation_id}/actions",
            json=body,
            headers=self._headers(operation),
        ))

    def purchase(self, quote_id: str) -> dict[str, Any]:
        operation = {"method": "purchase", "quote_id": quote_id}
        return self._response(self._http.post(
            f"/v1/quotes/{quote_id}/purchase",
            json={},
            headers=self._headers(operation),
        ))

    def get_payment(self, payment_id: str) -> dict[str, Any]:
        return self._response(self._http.get(
            f"/v1/payments/{payment_id}", headers=self._headers()
        ))
