import html
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.models.document import Document
from app.models.integration import Integration
from app.services.ingestion import ingest_text

MAX_PAGES = 40
MAX_CRAWL_DEPTH = 2
MIN_PAGE_CHARS = 200
HEADERS = {"User-Agent": "ChatyyBot/1.0 (+https://chatyy.app)"}

SKIP_EXTENSIONS = (
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico",
    ".css", ".js", ".json", ".xml", ".zip", ".mp4", ".mp3", ".woff", ".woff2",
)


def _normalize_url(url: str) -> str:
    """Strip fragment and trailing slash so the same page isn't crawled twice."""
    url = url.split("#", 1)[0]
    return url.rstrip("/")


def _same_host(url: str, host: str) -> bool:
    return urlparse(url).netloc == host


def _extract_title(page_html: str) -> str | None:
    m = re.search(r"<title[^>]*>(.*?)</title>", page_html, re.IGNORECASE | re.DOTALL)
    if m:
        title = html.unescape(re.sub(r"\s+", " ", m.group(1))).strip()
        return title or None
    return None


def _html_to_text(page_html: str) -> str:
    # Drop non-content blocks before stripping tags
    cleaned = re.sub(
        r"<(script|style|noscript|svg|iframe|nav|footer)[^>]*>.*?</\1>",
        " ",
        page_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    # Preserve block boundaries as newlines so text doesn't run together
    cleaned = re.sub(r"</(p|div|li|h[1-6]|tr|section|article|br)\s*>|<br\s*/?>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n\s*\n+", "\n\n", cleaned)
    return cleaned.strip()


def _extract_links(page_html: str, base_url: str) -> list[str]:
    links = []
    for m in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\']', page_html, re.IGNORECASE):
        href = m.group(1).strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        absolute = _normalize_url(urljoin(base_url, href))
        if urlparse(absolute).path.lower().endswith(SKIP_EXTENSIONS):
            continue
        links.append(absolute)
    return links


async def _fetch(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        r = await client.get(url)
        if r.status_code != 200 or "text/html" not in r.headers.get("content-type", "text/html"):
            return None
        return r.text
    except httpx.HTTPError:
        return None


async def _urls_from_sitemap(client: httpx.AsyncClient, base_url: str, host: str) -> list[str]:
    try:
        r = await client.get(f"{base_url}/sitemap.xml")
        if r.status_code != 200:
            return []
        content = r.text
    except httpx.HTTPError:
        return []

    locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", content)

    # Sitemap index: fetch nested sitemaps (bounded)
    if "<sitemapindex" in content:
        urls: list[str] = []
        for sitemap_url in locs[:5]:
            try:
                r = await client.get(sitemap_url.strip())
                if r.status_code == 200:
                    urls.extend(re.findall(r"<loc>\s*(.*?)\s*</loc>", r.text))
            except httpx.HTTPError:
                continue
        locs = urls

    result = []
    for u in locs:
        u = _normalize_url(html.unescape(u.strip()))
        if _same_host(u, host) and not urlparse(u).path.lower().endswith(SKIP_EXTENSIONS):
            result.append(u)
        if len(result) >= MAX_PAGES:
            break
    return result


async def _urls_from_crawl(client: httpx.AsyncClient, base_url: str, host: str) -> dict[str, str]:
    """BFS the site starting at the homepage. Returns {url: html}."""
    pages: dict[str, str] = {}
    seen = {base_url}
    frontier = [base_url]

    for _ in range(MAX_CRAWL_DEPTH + 1):
        next_frontier: list[str] = []
        for url in frontier:
            if len(pages) >= MAX_PAGES:
                return pages
            page_html = await _fetch(client, url)
            if page_html is None:
                continue
            pages[url] = page_html
            for link in _extract_links(page_html, url):
                if link not in seen and _same_host(link, host):
                    seen.add(link)
                    next_frontier.append(link)
        frontier = next_frontier
        if not frontier:
            break
    return pages


async def sync_website(integration_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Integration).where(Integration.id == integration_id))
        integration = result.scalar_one()
        config = integration.config or {}
        site_url = (config.get("site_url") or "").strip().rstrip("/")

        if not site_url:
            integration.status = "error"
            integration.error_message = "Missing website URL."
            await db.commit()
            return

        if "://" not in site_url:
            site_url = f"https://{site_url}"
        host = urlparse(site_url).netloc

        try:
            async with httpx.AsyncClient(headers=HEADERS, timeout=15.0, follow_redirects=True) as client:
                sitemap_urls = await _urls_from_sitemap(client, site_url, host)
                if sitemap_urls:
                    pages: dict[str, str] = {}
                    for url in sitemap_urls:
                        if len(pages) >= MAX_PAGES:
                            break
                        page_html = await _fetch(client, url)
                        if page_html is not None:
                            pages[url] = page_html
                else:
                    pages = await _urls_from_crawl(client, site_url, host)

            if not pages:
                raise RuntimeError("No pages could be fetched — check the URL is reachable.")

            # Replace previously crawled pages for this tenant
            await db.execute(
                delete(Document).where(
                    Document.tenant_id == tenant_id,
                    Document.storage_path.like("web://%"),
                )
            )

            ingested = 0
            for url, page_html in pages.items():
                content = _html_to_text(page_html)
                if len(content) < MIN_PAGE_CHARS:
                    continue
                title = _extract_title(page_html) or urlparse(url).path or url
                await ingest_text(db, tenant_id, f"Web: {title}"[:255], f"web://{url}", content)
                ingested += 1

            if ingested == 0:
                raise RuntimeError("Pages were fetched but contained no readable text.")

            integration.status = "ready"
            integration.error_message = None
            integration.last_synced_at = datetime.now(timezone.utc)

        except Exception as e:
            integration.status = "error"
            integration.error_message = str(e)[:900]

        await db.commit()
