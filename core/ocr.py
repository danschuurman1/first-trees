# core/ocr.py
from __future__ import annotations
from typing import List

import cv2
import numpy as np
import pytesseract
from PIL import Image


class OCRReader:
    """Extracts item name text from a screen region using Tesseract."""

    def read_item_names(self, img_bgr: np.ndarray) -> List[str]:
        """Return list of lowercase item name strings found in the image."""
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)
        pil_img = Image.fromarray(thresh)
        raw = pytesseract.image_to_string(
            pil_img,
            config="--psm 6 --oem 3",
        )
        names = [line.strip().lower() for line in raw.splitlines() if line.strip()]
        return names

    def any_whitelisted(self, img_bgr: np.ndarray, whitelist: List[str]) -> bool:
        """Return True if any detected item name appears in the whitelist."""
        found = self.read_item_names(img_bgr)
        wl_lower = [w.lower() for w in whitelist]
        return any(name in wl_lower for name in found)
