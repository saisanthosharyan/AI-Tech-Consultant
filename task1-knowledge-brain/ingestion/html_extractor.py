import re
import hashlib
from urllib.parse import urljoin
from typing import Dict, Any, List
from bs4 import BeautifulSoup, Comment
import logging

logger = logging.getLogger("knowledge_brain.extractor")

class HTMLExtractor:
    def __init__(self):
        # Tags to remove completely
        self.ignore_tags = ["script", "style", "nav", "footer", "header", "aside", "noscript", "svg", "form"]
        # Common boilerplate / navigation class names to remove
        self.ignore_classes = [
            "breadcrumb", "sidebar", "nav", "footer", "header", "menu", "ads", 
            "related-articles", "social-share", "comments", "author-box", "feedback-form"
        ]

    def extract(self, html_content: str, url: str) -> Dict[str, Any]:
        """
        Parses raw HTML and extracts title, main body text, headings,
        lists, tables, screenshots, and computes a content hash.
        """
        soup = BeautifulSoup(html_content, "lxml")

        # 1. Remove comments
        for comment in soup.find_all(text=lambda text: isinstance(text, Comment)):
            comment.extract()

        # 2. Extract Title
        title = ""
        h1 = soup.find("h1")
        if h1 and h1.get_text(strip=True):
            title = h1.get_text(strip=True)
        elif soup.title and soup.title.string:
            title = soup.title.string.strip()
            # Clean common title suffixes like " - Brilliant Directories"
            title = re.sub(r"\s*[-|]\s*Brilliant Directories.*$", "", title, flags=re.IGNORECASE).strip()
        if not title:
            title = url.split("/")[-1].replace("-", " ").capitalize()

        # 3. Target main content container if available
        main_content = (
            soup.find("article") 
            or soup.find("div", class_=re.compile(r"article-body|solution-article|content__body|main-content", re.I))
            or soup.find("main")
            or soup.body
            or soup
        )

        # 4. Remove ignored tags & classes inside main content
        for tag in main_content.find_all(self.ignore_tags):
            tag.decompose()

        for cls in self.ignore_classes:
            for el in main_content.find_all(class_=re.compile(cls, re.I)):
                el.decompose()

        # 5. Extract images with surrounding context
        images = []
        for img in main_content.find_all("img"):
            src = img.get("src")
            if not src or "data:image" in src or "avatar" in src.lower() or "icon" in src.lower():
                continue
            full_img_url = urljoin(url, src)
            alt = img.get("alt", "").strip()
            
            # Find surrounding text (parent or previous/next paragraph)
            surrounding = ""
            parent_p = img.find_parent(["p", "div", "li"])
            if parent_p:
                surrounding = parent_p.get_text(strip=True)
            if not surrounding:
                prev_p = img.find_previous(["p", "h2", "h3"])
                if prev_p:
                    surrounding = prev_p.get_text(strip=True)

            images.append({
                "url": full_img_url,
                "alt": alt,
                "surrounding_text": surrounding[:250]
            })

        # 6. Extract sections, headings, lists, tables
        sections = []
        headings = []
        current_heading = "Overview"
        current_paragraphs = []
        current_images = []

        for element in main_content.children:
            if element.name in ["h1", "h2", "h3", "h4"]:
                h_text = element.get_text(strip=True)
                if h_text:
                    if current_paragraphs or current_images:
                        sec_text = "\n\n".join(current_paragraphs).strip()
                        if sec_text:
                            sections.append({
                                "heading": current_heading,
                                "text": sec_text,
                                "images": current_images
                            })
                    current_heading = h_text
                    headings.append(h_text)
                    current_paragraphs = []
                    current_images = []
            elif element.name in ["p", "blockquote"]:
                text = element.get_text(strip=True)
                if text:
                    current_paragraphs.append(text)
            elif element.name in ["ul", "ol"]:
                items = [f"- {li.get_text(strip=True)}" for li in element.find_all("li") if li.get_text(strip=True)]
                if items:
                    current_paragraphs.append("\n".join(items))
            elif element.name == "table":
                rows = []
                for tr in element.find_all("tr"):
                    cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                    if any(cells):
                        rows.append(" | ".join(cells))
                if rows:
                    current_paragraphs.append("\n".join(rows))

        # Append last section
        if current_paragraphs or current_images:
            sec_text = "\n\n".join(current_paragraphs).strip()
            if sec_text:
                sections.append({
                    "heading": current_heading,
                    "text": sec_text,
                    "images": current_images
                })

        # If no sections were parsed cleanly, fall back to clean full text
        raw_text = "\n\n".join([f"## {s['heading']}\n{s['text']}" for s in sections])
        if not raw_text.strip():
            raw_text = main_content.get_text(separator="\n", strip=True)
            sections = [{"heading": "Overview", "text": raw_text, "images": [img["url"] for img in images]}]

        # 7. Compute deterministic content hash (SHA-256)
        content_hash = hashlib.sha256((title + "\n" + raw_text).encode("utf-8")).hexdigest()

        return {
            "title": title,
            "url": url,
            "content_hash": content_hash,
            "raw_text": raw_text,
            "headings": headings,
            "sections": sections,
            "images": images
        }
