"""Facebook Page discovery, selection and publishing (PRD §3.1, §9)."""
from __future__ import annotations

from dataclasses import dataclass

from ...domain.enums import ErrorClass
from .graph_client import GraphClient, GraphResponse, classify_graph_error


@dataclass(frozen=True)
class PageRef:
    page_id: str
    name: str
    access_token_present: bool = False


@dataclass
class DiscoveryResult:
    pages: list[PageRef]
    error_class: ErrorClass | None = None
    message: str = ""
    request_id: str = ""

    @property
    def ok(self) -> bool:
        return self.error_class is None


@dataclass
class PublishResult:
    ok: bool
    remote_id: str = ""
    permalink: str = ""
    error_class: ErrorClass | None = None
    summary: str = ""

    @classmethod
    def from_response(cls, resp: GraphResponse, *, id_keys: tuple[str, ...] = ("id",)) -> PublishResult:
        if not resp.ok:
            return cls(False, error_class=classify_graph_error(resp), summary=resp.sanitized_summary())
        remote_id = next((resp.json[k] for k in id_keys if resp.json.get(k)), "")
        return cls(True, remote_id=remote_id, permalink=resp.json.get("permalink", ""), summary=f"id={remote_id}")


def list_pages(client: GraphClient, user_token: str) -> DiscoveryResult:
    """Return the Pages the operator authorized. Never treat Page name/ID as credentials."""
    resp: GraphResponse = client.get("me/accounts", {"fields": "id,name,access_token"}, user_token)
    if not resp.ok:
        return DiscoveryResult([], classify_graph_error(resp), resp.sanitized_summary(), resp.request_id)
    pages = [
        PageRef(page_id=item.get("id", ""), name=item.get("name", ""), access_token_present=bool(item.get("access_token")))
        for item in resp.json.get("data", [])
    ]
    return DiscoveryResult(pages, None, f"{len(pages)} page(s) authorized", resp.request_id)


def test_connection(client: GraphClient, page_id: str, page_token: str) -> DiscoveryResult:
    """Non-publishing permission check against the selected Page."""
    resp = client.get(page_id, {"fields": "id,name"}, page_token)
    if not resp.ok:
        return DiscoveryResult([], classify_graph_error(resp), resp.sanitized_summary(), resp.request_id)
    return DiscoveryResult([PageRef(resp.json.get("id", page_id), resp.json.get("name", ""))], None, "connection ok", resp.request_id)


def publish_test_post(client: GraphClient, page_id: str, page_token: str, message: str) -> PublishResult:
    """Publish an explicitly confirmed test post."""
    resp = client.post(f"{page_id}/feed", {"message": message}, page_token)
    return PublishResult.from_response(resp)


def publish_photo(client: GraphClient, page_id: str, page_token: str, image_url: str, caption: str) -> PublishResult:
    """Publish a single-image feed post (matches manual 'What's on your mind' posting)."""
    import json
    # Step 1: Upload photo as unpublished to get media_fbid without creating an album post
    upload_resp = client.post(
        f"{page_id}/photos",
        {"url": image_url, "published": "false"},
        page_token,
    )
    if not upload_resp.ok:
        return PublishResult.from_response(upload_resp, id_keys=("id",))

    photo_id = upload_resp.json.get("id")

    # Step 2: Create a feed post with the photo attached
    feed_resp = client.post(
        f"{page_id}/feed",
        {
            "message": caption,
            "attached_media[0]": json.dumps({"media_fbid": photo_id}),
        },
        page_token,
    )
    return PublishResult.from_response(feed_resp, id_keys=("post_id", "id"))
