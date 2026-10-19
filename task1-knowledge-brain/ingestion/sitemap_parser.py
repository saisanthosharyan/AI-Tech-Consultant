import httpx
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple
import shared
from shared.config import settings
from kb_app.db import get_db_connection, log_audit_event

logger = logging.getLogger("knowledge_brain.sitemap")

class SitemapParser:
    def __init__(self, sitemap_url: str = settings.support_sitemap_url):
        self.sitemap_url = sitemap_url

    def fetch_and_parse(self) -> Tuple[List[Dict[str, str]], Dict[str, int]]:
        """
        Downloads the sitemap XML, parses loc and lastmod, deduplicates,
        and synchronizes with the manifest table in SQLite.
        """
        logger.info(f"Fetching sitemap from {self.sitemap_url}")
        headers = {"User-Agent": "AITechConsultant-IngestionBot/1.0 (+http://localhost:8000)"}

        try:
            with httpx.Client(timeout=15.0, follow_redirects=True, headers=headers) as client:
                response = client.get(self.sitemap_url)
                response.raise_for_status()
                xml_content = response.text
        except Exception as e:
            logger.error(f"Failed to fetch live sitemap: {e}")
            raise RuntimeError(f"Sitemap fetch failed: {str(e)}")

        entries = self.parse_xml(xml_content)
        stats = self.sync_with_manifest(entries)
        return entries, stats

    def parse_xml(self, xml_content: str) -> List[Dict[str, str]]:
        """Parses XML string, extracts loc and lastmod, filters for solution articles."""
        root = ET.fromstring(xml_content)
        namespaces = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        
        raw_entries = []
        for url_tag in root.findall('.//ns:url', namespaces) or root.findall('.//url'):
            loc_el = url_tag.find('ns:loc', namespaces) if url_tag.find('ns:loc', namespaces) is not None else url_tag.find('loc')
            lastmod_el = url_tag.find('ns:lastmod', namespaces) if url_tag.find('ns:lastmod', namespaces) is not None else url_tag.find('lastmod')
            
            if loc_el is not None and loc_el.text:
                url = loc_el.text.strip()
                lastmod = lastmod_el.text.strip() if (lastmod_el is not None and lastmod_el.text) else None
                # Filter for articles
                if "/support/solutions/articles/" in url:
                    raw_entries.append({"url": url, "lastmod": lastmod})

        # Deduplicate preserving order
        seen = set()
        deduped = []
        for entry in raw_entries:
            if entry["url"] not in seen:
                seen.add(entry["url"])
                deduped.append(entry)

        logger.info(f"Parsed {len(deduped)} unique article URLs from sitemap.")
        return deduped

    def sync_with_manifest(self, entries: List[Dict[str, str]]) -> Dict[str, int]:
        """
        Updates the manifest table:
        - Inserts new articles with status 'pending'
        - Identifies unchanged, changed, and removed articles
        """
        conn = get_db_connection()
        cur = conn.cursor()
        now_str = datetime.now(timezone.utc).isoformat()

        cur.execute("SELECT url, lastmod, status, content_hash FROM manifest")
        existing = {row["url"]: dict(row) for row in cur.fetchall()}

        new_count = 0
        unchanged_count = 0
        updated_sitemap_urls = set()

        for entry in entries:
            url = entry["url"]
            lastmod = entry["lastmod"]
            updated_sitemap_urls.add(url)

            if url not in existing:
                cur.execute(
                    "INSERT INTO manifest (url, lastmod, status, updated_at) VALUES (?, ?, 'pending', ?)",
                    (url, lastmod, now_str)
                )
                new_count += 1
            else:
                ex = existing[url]
                if ex.get("lastmod") != lastmod:
                    cur.execute(
                        "UPDATE manifest SET lastmod = ?, status = 'pending', updated_at = ? WHERE url = ?",
                        (lastmod, now_str, url)
                    )
                    new_count += 1
                else:
                    unchanged_count += 1

        # Check for removed articles (present in DB manifest, absent from live sitemap)
        removed_count = 0
        for old_url, ex_data in existing.items():
            if old_url not in updated_sitemap_urls and ex_data.get("status") != "removed":
                cur.execute("UPDATE manifest SET status = 'removed', updated_at = ? WHERE url = ?", (now_str, old_url))
                cur.execute("UPDATE articles SET is_active = 0 WHERE url = ?", (old_url,))
                removed_count += 1

        conn.commit()
        conn.close()

        stats = {
            "total_discovered": len(entries),
            "new_or_modified": new_count,
            "unchanged": unchanged_count,
            "removed": removed_count
        }
        log_audit_event("sitemap_synced", stats)
        return stats
