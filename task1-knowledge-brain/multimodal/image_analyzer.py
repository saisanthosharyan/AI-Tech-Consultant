import logging
import base64
import httpx
from typing import Optional, Dict, Any
import shared
from shared.config import settings

logger = logging.getLogger("knowledge_brain.multimodal")

class ImageAnalyzer:
    def __init__(self, api_key: str = settings.anthropic_api_key):
        self.api_key = api_key
        self.client = None
        if self.api_key:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Could not initialize Anthropic client for vision: {e}")

    def analyze_screenshot(self, image_url: str, article_title: str, section: str, surrounding_text: str) -> str:
        """
        Analyzes a screenshot from a help article. Uses Claude Vision if API key is configured;
        otherwise provides a structured fallback description based on surrounding context.
        """
        if not self.client:
            return self._fallback_description(image_url, article_title, section, surrounding_text)

        try:
            # Download image bytes with timeout
            with httpx.Client(timeout=8.0) as http_client:
                resp = http_client.get(image_url)
                if resp.status_code != 200:
                    return self._fallback_description(image_url, article_title, section, surrounding_text)
                
                content_type = resp.headers.get("content-type", "image/png").split(";")[0]
                if content_type not in ["image/jpeg", "image/png", "image/gif", "image/webp"]:
                    content_type = "image/png"
                img_b64 = base64.b64encode(resp.content).decode("utf-8")

            prompt = (
                f"Describe this UI screenshot from the Brilliant Directories support article '{article_title}'. "
                f"Section: '{section}'. Focus on visible buttons, form fields, navigation tabs, settings, "
                f"and instructions shown in the interface. Keep it concise (2-3 sentences)."
            )

            response = self.client.messages.create(
                model=settings.anthropic_model,
                max_tokens=200,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": content_type,
                                    "data": img_b64,
                                },
                            },
                            {"type": "text", "text": prompt}
                        ],
                    }
                ],
            )
            description = response.content[0].text.strip()
            logger.info(f"Claude Vision generated description for {image_url[:40]}")
            return description

        except Exception as e:
            logger.warning(f"Claude Vision call failed for {image_url}: {e}. Using fallback.")
            return self._fallback_description(image_url, article_title, section, surrounding_text)

    def _fallback_description(self, image_url: str, article_title: str, section: str, surrounding_text: str) -> str:
        snippet = surrounding_text[:160].replace("\n", " ") if surrounding_text else "Visual walkthrough"
        filename = image_url.split("/")[-1].split("?")[0]
        return f"[UI Screenshot: '{filename}' in section '{section}' of '{article_title}': {snippet}...]"
