"""Problem+JSON errors with the stable codes of the API contract."""

from __future__ import annotations

from typing import Any

PROBLEM_TYPE_PREFIX = "urn:ontaix:problem:"
BUSY_RETRY_AFTER_SECONDS = 1

TITLES: dict[str, str] = {
    "bad_request": "Bad request",
    "unauthorized": "Unauthorized",
    "forbidden": "Forbidden",
    "not_found": "Not found",
    "validation_failed": "Validation failed",
    "duplicate_label": "Duplicate label",
    "duplicate_relation": "Duplicate relation",
    "structural_relation": "Structural relation",
    "cross_company_disabled": "Companies may not interact",
    "same_company": "Same company",
    "already_bound": "Already bound",
    "source_pending": "Source pending",
    "root_concept": "Root concept",
    "home_company": "Home company",
    "proposal_not_ready": "Proposal not ready",
    "proposal_not_half_approved": "Proposal not half approved",
    "proposal_decided": "Proposal already decided",
    "same_approver": "Same approver",
    "locked_setting": "Locked setting",
    "confirmation_required": "Confirmation required",
    "confirmation_mismatch": "Confirmation mismatch",
    "duplicate_role": "Duplicate role",
    "not_demo_tenant": "Not a demo tenant",
    "story_finished": "Story finished",
    "payload_too_large": "Payload too large",
    "unsupported_media_type": "Unsupported media type",
    "unavailable": "Unavailable",
    "busy": "Busy",
    "rate_limited": "Rate limited",
    "duplicate_attribute": "Duplicate attribute",
    "duplicate_agent": "Duplicate agent",
}


class ProblemError(Exception):
    """An error the API reports as `application/problem+json` with a stable code."""

    def __init__(
        self,
        status: int,
        code: str,
        detail: str | None = None,
        errors: list[dict[str, str]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail or TITLES.get(code, code))
        self.status = status
        self.code = code
        self.detail = detail
        self.errors = errors
        self.headers = headers

    def body(self, instance: str | None) -> dict[str, Any]:
        """Serialise to the `Problem` schema of the contract."""
        body: dict[str, Any] = {
            "type": PROBLEM_TYPE_PREFIX + self.code,
            "title": TITLES.get(self.code, self.code),
            "status": self.status,
            "code": self.code,
        }
        if self.detail:
            body["detail"] = self.detail
        if instance:
            body["instance"] = instance
        if self.errors:
            body["errors"] = self.errors
        return body


def not_found(what: str) -> ProblemError:
    return ProblemError(404, "not_found", f"{what} not found in this tenant")


def forbidden(detail: str | None = None) -> ProblemError:
    return ProblemError(403, "forbidden", detail)


def unauthorized(detail: str | None = None) -> ProblemError:
    return ProblemError(401, "unauthorized", detail)


def conflict(code: str, detail: str | None = None) -> ProblemError:
    return ProblemError(409, code, detail)


def bad_request(detail: str) -> ProblemError:
    return ProblemError(400, "bad_request", detail)


def busy(detail: str) -> ProblemError:
    """Contention on a lock, a deadlock or a serialisation failure: nothing was written."""
    return ProblemError(503, "busy", detail, headers={"Retry-After": str(BUSY_RETRY_AFTER_SECONDS)})


def validation_failed(field: str, message: str) -> ProblemError:
    return ProblemError(
        422, "validation_failed", message, errors=[{"field": field, "message": message}]
    )
