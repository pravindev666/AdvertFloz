"""Instagram professional-account discovery and the persisted publish state machine (PRD §3.2, §9).

Publishing is three durable stages resumed across scheduler ticks:
``CREATE_CONTAINER`` → ``CHECK_STATUS`` → ``PUBLISH``. Nothing here sleeps or busy-waits
waiting for media processing.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ...domain.enums import ErrorClass
from .graph_client import GraphClient, classify_graph_error


class InstagramStage(str, Enum):
    CREATE_CONTAINER = "CREATE_CONTAINER"
    CHECK_STATUS = "CHECK_STATUS"
    PUBLISH = "PUBLISH"
    DONE = "DONE"


class ContainerStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    FINISHED = "FINISHED"
    ERROR = "ERROR"
    EXPIRED = "EXPIRED"
    PUBLISHED = "PUBLISHED"


@dataclass
class IgAccount:
    ig_user_id: str
    username: str


@dataclass
class ContainerResult:
    container_id: str
    error_class: ErrorClass | None = None
    summary: str = ""

    @property
    def ok(self) -> bool:
        return self.error_class is None and bool(self.container_id)


@dataclass
class StatusResult:
    status: ContainerStatus
    error_class: ErrorClass | None = None
    summary: str = ""

    @property
    def ok(self) -> bool:
        return self.error_class is None


@dataclass
class IgPublishResult:
    ok: bool
    media_id: str = ""
    permalink: str = ""
    error_class: ErrorClass | None = None
    summary: str = ""


@dataclass
class IgDiscovery:
    account: IgAccount | None
    error_class: ErrorClass | None = None
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.error_class is None and self.account is not None


def discover_account(client: GraphClient, page_id: str, page_token: str) -> IgDiscovery:
    """Find the professional Instagram account linked to the selected Page."""
    resp = client.get(
        page_id,
        {"fields": "instagram_business_account{id,username},connected_instagram_account{id,username}"},
        page_token,
    )
    if not resp.ok:
        return IgDiscovery(None, classify_graph_error(resp), resp.sanitized_summary())
    payload = resp.json
    node = payload.get("instagram_business_account") or payload.get("connected_instagram_account")
    if not node:
        return IgDiscovery(None, None, "No eligible professional Instagram account is linked to this Page.")
    return IgDiscovery(IgAccount(node.get("id", ""), node.get("username", "")), None, "found")


def create_container(client: GraphClient, ig_user_id: str, token: str, image_url: str, caption: str) -> ContainerResult:
    resp = client.post(
        f"{ig_user_id}/media",
        {"image_url": image_url, "caption": caption},
        token,
    )
    if not resp.ok:
        return ContainerResult("", classify_graph_error(resp), resp.sanitized_summary())
    return ContainerResult(resp.json.get("id", ""), None, "container created")


def check_status(client: GraphClient, container_id: str, token: str) -> StatusResult:
    resp = client.get(container_id, {"fields": "status_code,status"}, token)
    if not resp.ok:
        return StatusResult(ContainerStatus.ERROR, classify_graph_error(resp), resp.sanitized_summary())
    raw = resp.json.get("status_code", "")
    try:
        return StatusResult(ContainerStatus(raw), None, raw)
    except ValueError:
        return StatusResult(ContainerStatus.ERROR, ErrorClass.UNKNOWN, f"unexpected status {raw!r}")


def publish_container(client: GraphClient, ig_user_id: str, token: str, container_id: str) -> IgPublishResult:
    resp = client.post(f"{ig_user_id}/media_publish", {"creation_id": container_id}, token)
    if not resp.ok:
        return IgPublishResult(False, error_class=classify_graph_error(resp), summary=resp.sanitized_summary())
    media_id = resp.json.get("id", "")
    return IgPublishResult(True, media_id=media_id, permalink=resp.json.get("permalink", ""), summary=f"id={media_id}")


def next_stage(stage: InstagramStage, container_status: ContainerStatus | None) -> InstagramStage:
    """Advance the state machine without ever blocking a tick."""
    if stage is InstagramStage.CREATE_CONTAINER:
        return InstagramStage.CHECK_STATUS
    if stage is InstagramStage.CHECK_STATUS:
        if container_status is ContainerStatus.FINISHED:
            return InstagramStage.PUBLISH
        if container_status in {ContainerStatus.ERROR, ContainerStatus.EXPIRED}:
            return InstagramStage.CREATE_CONTAINER  # retry container creation
        return InstagramStage.CHECK_STATUS       # still processing; resume next tick
    if stage is InstagramStage.PUBLISH:
        return InstagramStage.DONE
    return InstagramStage.DONE
