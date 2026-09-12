# Self-hosted Meta, Google Ads, and TikTok Ads MCP

This fork runs FastMCP servers behind Traefik on a private VPS. Each platform is a separate URL and a separate Docker service.

## Hosts

| Platform | URL | Container |
|---|---|---|
| Meta Ads | `https://pipeboard.ovictorfarias.com.br/mcp` | `pipeboard-mcp` |
| Meta Posts | `https://meta-posts.ovictorfarias.com.br/mcp` | `pipeboard-meta-posts-mcp` |
| Google Ads | `https://google-ads.ovictorfarias.com.br/mcp` | `pipeboard-google-ads-mcp` |
| TikTok Ads | `https://tiktok-ads.ovictorfarias.com.br/mcp` | `pipeboard-tiktok-ads-mcp` |

Create DNS A/CNAME records pointing at the VPS (`google-ads`, `tiktok-ads`, and `meta-posts` under `ovictorfarias.com.br`). Traefik issues TLS via `mytlschallenge`.

## Environment

Copy `.env.example` to `.env` and fill in platform credentials. HTTP requests still need a Bearer token (or `?token=`):

- Meta Ads / Meta Posts: Meta access token (`pages_manage_posts` and `instagram_content_publish` are required for posts)
- Google Ads: OAuth **refresh token** (same value as `GOOGLE_ADS_REFRESH_TOKEN`)
- TikTok: Marketing API **access token** (same value as `TIKTOK_ACCESS_TOKEN`)

Google Ads also needs a developer token and OAuth client id/secret in the container env. TikTok needs app id/secret; set `TIKTOK_REFRESH_TOKEN` so the server can renew expired access tokens.

Generate Google/TikTok tokens on a machine with a browser:

```bash
python -m google_ads_mcp --login
python -m tiktok_ads_mcp --login
```

Then copy the refresh/access tokens into the VPS `.env`.

## Deploy

```bash
docker compose up -d --build
```

## Cursor / Claude

```json
{
  "mcpServers": {
    "meta-ads": {
      "url": "https://pipeboard.ovictorfarias.com.br/mcp?token=META_ACCESS_TOKEN"
    },
    "meta-posts": {
      "url": "https://meta-posts.ovictorfarias.com.br/mcp?token=META_ACCESS_TOKEN"
    },
    "google-ads": {
      "url": "https://google-ads.ovictorfarias.com.br/mcp?token=GOOGLE_ADS_REFRESH_TOKEN"
    },
    "tiktok-ads": {
      "url": "https://tiktok-ads.ovictorfarias.com.br/mcp?token=TIKTOK_ACCESS_TOKEN"
    }
  }
}
```

## Smoke test

```bash
python scripts/smoke_mcp.py --url https://google-ads.ovictorfarias.com.br --token "$GOOGLE_ADS_REFRESH_TOKEN"
python scripts/smoke_mcp.py --url https://tiktok-ads.ovictorfarias.com.br --token "$TIKTOK_ACCESS_TOKEN"
python scripts/smoke_mcp.py --url https://pipeboard.ovictorfarias.com.br --token "$META_ACCESS_TOKEN"
python scripts/smoke_mcp.py --url https://meta-posts.ovictorfarias.com.br --token "$META_ACCESS_TOKEN"
```

Writes start paused (`PAUSED` on Google, `DISABLE` on TikTok) unless you explicitly override status.
