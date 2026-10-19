# Provider compatibility — AdvertFloz v1.7

Provider documentation changes. Values below are the ones the code is parameterised for and must be
re-verified against official docs during Phase 0. The access date column records when the
implementation last read official documentation.

| Provider | Item | Value in code | Configured by | Access date | Status |
|---|---|---|---|---|---|
| Meta Graph API | Version | `META_GRAPH_VERSION=v21.0` | env/secret | not yet verified live | **PENDING** |
| Meta OAuth | Authorize endpoint | `https://www.facebook.com/{version}/dialog/oauth` | `infrastructure/meta/oauth.py` | not yet verified live | **PENDING** |
| Meta OAuth | Token exchange | `POST /{version}/oauth/access_token`, server-side | `oauth.py` | not yet verified live | **PENDING** |
| Meta scopes (IG API with Facebook Login) | `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `instagram_basic`, `instagram_content_publish`, `business_management` | `oauth.DEFAULT_SCOPES` | code | not yet verified live | **PENDING** |
| Meta | Page discovery | `GET /me/accounts` | `facebook_pages.list_pages` | not yet verified live | **PENDING** |
| Meta | Single-image Page post | `POST /{page-id}/photos` (`url`, `caption`, `published`) | `facebook_pages.publish_photo` | not yet verified live | **PENDING** |
| Instagram | Container create | `POST /{ig-user-id}/media` (`image_url`, `caption`) | `instagram_publish.create_container` | not yet verified live | **PENDING** |
| Instagram | Container status | `GET /{container-id}?fields=status_code` | `instagram_publish.check_status` | not yet verified live | **PENDING** |
| Instagram | Publish | `POST /{ig-user-id}/media_publish` (`creation_id`) | `instagram_publish.publish_container` | not yet verified live | **PENDING** |
| Instagram | Media constraints (conservative) | caption ≤2200, ≤5 hashtags, JPEG ≤8 MB, aspect 4:5–1.91:1 | `policy_registry.INSTAGRAM_V1_7` | code policy | **PENDING** re-verify |
| Facebook | Media constraints (conservative) | caption ≤63206, JPEG/PNG ≤10 MB | `policy_registry.FACEBOOK_V1_7` | code policy | **PENDING** re-verify |
| Cloudflare | Worker Cron, D1, R2 limits/pricing | not asserted | `worker/wrangler.toml.example` | not yet verified live | **PENDING** |
| Telegram | Bot API sendMessage | `https://api.telegram.org/bot<token>/sendMessage` | `notifications/telegram.py` | not yet verified live | **PENDING** |

## Reference links (re-check at implementation time)

- Streamlit navigation — https://docs.streamlit.io/develop/api-reference/navigation/st.navigation
- Streamlit theming — https://docs.streamlit.io/develop/concepts/configuration/theming
- Streamlit authentication — https://docs.streamlit.io/develop/concepts/connections/authentication
- Meta Instagram API collection — https://www.postman.com/meta/instagram/documentation/
- Cloudflare Workers limits — https://developers.cloudflare.com/workers/platform/limits/
- Cloudflare Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- Cloudflare R2 — https://developers.cloudflare.com/r2/
- GitHub Actions workflow syntax — https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions

**None of the PENDING rows may be treated as release assumptions until a live Phase 0 test passes.**
