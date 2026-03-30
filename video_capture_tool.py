#!/usr/bin/env python3
"""
HACSM Training Video Capture & Customization Tool v2.1
Captures step-by-step screenshots from Yardi Aspire training videos
and generates HACSM-specific training documentation.

Usage:
    python video_capture_tool.py capture --url <aspire_url> [--all | --video-title <title>]
        python video_capture_tool.py list --url <aspire_url>
            python video_capture_tool.py review --project <project_dir>
                python video_capture_tool.py customize --project <project_dir> <action> [options]
                    python video_capture_tool.py publish --project <project_dir>
                        python video_capture_tool.py browsers
                        """

import argparse
import json
import os
import re
import sys
import time
import shutil
import platform
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any

try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import (
            TimeoutException, NoSuchElementException, WebDriverException
    )
        SELENIUM_AVAILABLE = True
except ImportError:
        SELENIUM_AVAILABLE = False

try:
        from PIL import Image
        PIL_AVAILABLE = True
except ImportError:
        PIL_AVAILABLE = False


# ==========================================================================
# CONFIGURATION
# ==========================================================================
class Config:
        """Central configuration for the tool."""
        # Output settings
        OUTPUT_DIR = "hacsm_training_captures"
        SCREENSHOT_FORMAT = "png"
        GENERATE_MARKDOWN = True
        GENERATE_HTML = True

    # Capture settings
        CAPTURE_INTERVAL = 2.0        # seconds between captures
    CHANGE_THRESHOLD = 0.05       # minimum pixel change ratio to save frame
    ZOOM_REGIONS = True           # capture zoomed regions of interest
    MAX_CAPTURE_DURATION = 600    # max seconds to capture a single video

    # Vimeo player selectors
    VIMEO_IFRAME_SEL = "iframe[src*='vimeo']"
    VIMEO_PLAY_BTN = ".play-button, button[aria-label='Play']"
    VIMEO_PROGRESS = ".vp-progress"

    # Yardi Aspire selectors
    ASPIRE_VIDEO_WIDGET = ".media_embed.videoWidget"
    ASPIRE_VIDEO_DATASRC = "data-src"
    ASPIRE_TITLE_SEL = "h2.RL"
    ASPIRE_FAQ_MODAL = "#FAQModal"
    ASPIRE_FAQ_ENTRY = ".FAQEnt"

    # HACSM branding
    HACSM_BRANDING = {
                "org_name": "Housing Authority of the County of San Mateo",
                "org_short": "HACSM",
                "footer": "Internal Use Only - HACSM Training Documentation",
                "logo_path": None,
    }

    # Browser wait times
    PAGE_LOAD_WAIT = 15
    ELEMENT_WAIT = 10
    LOGIN_WAIT = 120  # wait for manual login


# ==========================================================================
# DATA MODELS
# ==========================================================================
@dataclass
class StepData:
        """Represents a single step in a training guide."""
        step_number: int
        timestamp: float = 0.0
        description: str = ""
        screenshot_path: str = ""
        zoom_path: str = ""
        status: str = "draft"  # draft, keep, modify, remove, custom, diverge
    hacsm_description: str = ""
    hacsm_note: str = ""
    divergence_yardi: str = ""
    divergence_hacsm: str = ""
    custom_screenshot_path: str = ""
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
                return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "StepData":
                # Handle the tags field which may not exist in older data
                if "tags" not in data:
                                data["tags"] = []
                            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ==========================================================================
# BROWSER MANAGER - Multi-browser support
# ==========================================================================
class BrowserManager:
        """Manages browser detection and Selenium WebDriver creation."""

    # Known browser paths by platform
    BROWSER_PATHS = {
                "darwin": {  # macOS
                    "chrome": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                                "brave": "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
                                "edge": "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                                "arc": "/Applications/Arc.app/Contents/MacOS/Arc",
                                "chromium": "/Applications/Chromium.app/Contents/MacOS/Chromium",
                                "firefox": "/Applications/Firefox.app/Contents/MacOS/firefox",
                                "perplexity": "/Applications/Perplexity.app/Contents/MacOS/Perplexity",
                },
                "win32": {  # Windows
                    "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                                "brave": r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
                                "edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                                "firefox": r"C:\Program Files\Mozilla Firefox\firefox.exe",
                                "chromium": r"C:\Program Files\Chromium\Application\chrome.exe",
                },
                "linux": {
                                "chrome": "/usr/bin/google-chrome",
                                "brave": "/usr/bin/brave-browser",
                                "edge": "/usr/bin/microsoft-edge",
                                "firefox": "/usr/bin/firefox",
                                "chromium": "/usr/bin/chromium-browser",
                },
    }

    @classmethod
    def get_platform(cls) -> str:
                plat = sys.platform
        if plat == "darwin":
                        return "darwin"
elif plat.startswith("win"):
            return "win32"
        return "linux"

    @classmethod
    def list_available_browsers(cls) -> List[Dict[str, str]]:
                """Detect which supported browsers are installed."""
        plat = cls.get_platform()
        paths = cls.BROWSER_PATHS.get(plat, {})
        available = []
        for name, path in paths.items():
                        exists = os.path.exists(path)
                        available.append({
                            "name": name,
                            "path": path,
                            "installed": exists,
                            "platform": plat,
                        })
                    return available

    @classmethod
    def create_driver(cls, browser: str = "chrome", custom_path: str = None,
                                            headless: bool = False) -> "webdriver.Remote":
                                                        """Create a Selenium WebDriver for the specified browser."""
                                                        if not SELENIUM_AVAILABLE:
                                                                        raise RuntimeError(
                                                                                            "Selenium is not installed. Run: pip install selenium"
                                                                        )

                                                        plat = cls.get_platform()
                                                        browser = browser.lower().strip()

        # Chromium-based browsers use Chrome WebDriver
        chromium_browsers = {"chrome", "brave", "edge", "arc", "chromium", "perplexity"}
        is_chromium = browser in chromium_browsers

        if is_chromium:
                        options = webdriver.ChromeOptions()
                        binary = custom_path or cls.BROWSER_PATHS.get(plat, {}).get(browser)
                        if binary and os.path.exists(binary):
                                            options.binary_location = binary
                                        if headless:
                            options.add_argument("--headless=new")
                                                        options.add_argument("--start-maximized")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")

            if browser == "edge":
                                driver = webdriver.Edge(options=options)
            else:
                driver = webdriver.Chrome(options=options)

elif browser == "firefox":
            options = webdriver.FirefoxOptions()
            binary = custom_path or cls.BROWSER_PATHS.get(plat, {}).get("firefox")
            if binary and os.path.exists(binary):
                                options.binary_location = binary
                            if headless:
                                                options.add_argument("--headless")
                                            driver = webdriver.Firefox(options=options)

else:
            # Fallback: treat as chromium with custom path
                if not custom_path:
                                    raise ValueError(
                                                            f"Unknown browser '{browser}'. Provide a --browser-path."
                                    )
                                options = webdriver.ChromeOptions()
            options.binary_location = custom_path
            if headless:
                                options.add_argument("--headless=new")
                            options.add_argument("--start-maximized")
            driver = webdriver.Chrome(options=options)

        driver.implicitly_wait(Config.ELEMENT_WAIT)
        return driver


# ==========================================================================
# PROJECT MANAGER - Handles project persistence and lifecycle
# ==========================================================================
class ProjectManager:
        """Manages a capture project: saving/loading steps, metadata, screenshots."""

    def __init__(self, project_dir: str):
                self.project_dir = Path(project_dir)
        self.screenshots_dir = self.project_dir / "screenshots"
        self.zoom_dir = self.project_dir / "screenshots" / "zoom"
        self.custom_dir = self.project_dir / "custom_screenshots"
        self.output_dir = self.project_dir / "output"
        self.project_file = self.project_dir / "project.json"
        self.steps: List[StepData] = []
        self.metadata: Dict[str, Any] = {}

    def create(self, video_title: str = "", video_url: str = ""):
                """Initialize a new project directory."""
        for d in [self.screenshots_dir, self.zoom_dir, self.custom_dir, self.output_dir]:
                        d.mkdir(parents=True, exist_ok=True)
        self.metadata = {
                        "video_title": video_title,
                        "video_url": video_url,
                        "created": datetime.now().isoformat(),
                        "phase": "capture",
                        "version": 0,
                        "tool_version": "2.1",
        }
        self.save()
        print(f"[+] Project created: {self.project_dir}")

    def save(self):
                """Save project state to disk."""
        data = {
                        "metadata": self.metadata,
                        "steps": [s.to_dict() for s in self.steps],
        }
        with open(self.project_file, "w") as f:
                        json.dump(data, f, indent=2)

    def load(self):
                """Load project state from disk."""
        if not self.project_file.exists():
                        raise FileNotFoundError(f"No project found at {self.project_file}")
        with open(self.project_file) as f:
                        data = json.load(f)
        self.metadata = data.get("metadata", {})
        self.steps = [StepData.from_dict(s) for s in data.get("steps", [])]
        print(f"[+] Loaded project: {self.metadata.get('video_title', 'Untitled')}")
        print(f"    Phase: {self.metadata.get('phase', 'unknown')} | "
                            f"Steps: {len(self.steps)} | Version: {self.metadata.get('version', 0)}")

    def add_step(self, step: StepData):
                """Add a step and save."""
        self.steps.append(step)
        self.save()

    def get_active_steps(self) -> List[StepData]:
                """Return steps that are not marked for removal."""
        return [s for s in self.steps if s.status != "remove"]

    def renumber_steps(self):
                """Re-number active steps sequentially."""
        active = self.get_active_steps()
        for i, step in enumerate(active, 1):
                        step.step_number = i
        self.save()


# ==========================================================================
# SCREENSHOT ENGINE - Capture and compare screenshots
# ==========================================================================
class ScreenshotEngine:
        """Captures screenshots and detects meaningful visual changes."""

    def __init__(self, driver, project: ProjectManager):
                self.driver = driver
        self.project = project
        self.last_screenshot_data = None
        self.capture_count = 0

    def capture_full(self, label: str = "") -> str:
                """Take a full-page screenshot and save it."""
        self.capture_count += 1
        filename = f"step_{self.capture_count:03d}"
        if label:
                        safe_label = re.sub(r'[^\w\-]', '_', label)[:50]
            filename += f"_{safe_label}"
        filename += f".{Config.SCREENSHOT_FORMAT}"
        filepath = self.project.screenshots_dir / filename
        self.driver.save_screenshot(str(filepath))
        print(f"    [screenshot] {filepath.name}")
        return str(filepath)

    def capture_zoom(self, element=None, region: tuple = None, label: str = "") -> str:
                """Capture a zoomed region - either around an element or a fixed region."""
        if not PIL_AVAILABLE:
                        print("    [warn] Pillow not installed, skipping zoom capture")
            return ""

        # First take a full screenshot
        temp_path = self.project.screenshots_dir / "_temp_zoom.png"
        self.driver.save_screenshot(str(temp_path))

        img = Image.open(temp_path)

        if element:
                        loc = element.location
            size = element.size
            padding = 20
            left = max(0, loc['x'] - padding)
            top = max(0, loc['y'] - padding)
            right = min(img.width, loc['x'] + size['width'] + padding)
            bottom = min(img.height, loc['y'] + size['height'] + padding)
elif region:
            left, top, right, bottom = region
else:
            # Default: center 50% of screen
                w, h = img.size
            left, top = w // 4, h // 4
            right, bottom = 3 * w // 4, 3 * h // 4

        cropped = img.crop((left, top, right, bottom))

        self.capture_count += 1
        filename = f"zoom_{self.capture_count:03d}"
        if label:
                        safe_label = re.sub(r'[^\w\-]', '_', label)[:50]
            filename += f"_{safe_label}"
        filename += f".{Config.SCREENSHOT_FORMAT}"
        filepath = self.project.zoom_dir / filename
        cropped.save(str(filepath))
        temp_path.unlink(missing_ok=True)
        print(f"    [zoom] {filepath.name}")
        return str(filepath)

    def has_significant_change(self) -> bool:
                """Compare current screen to last capture to detect meaningful changes."""
        if not PIL_AVAILABLE or self.last_screenshot_data is None:
                        return True  # always capture if we can't compare

        temp_path = self.project.screenshots_dir / "_temp_compare.png"
        self.driver.save_screenshot(str(temp_path))
        current = Image.open(temp_path)

        last = Image.open(self.last_screenshot_data)

        if current.size != last.size:
                        temp_path.unlink(missing_ok=True)
            return True

        # Simple pixel comparison
        pixels_current = list(current.getdata())
        pixels_last = list(last.getdata())
        total = len(pixels_current)
        diff_count = sum(1 for a, b in zip(pixels_current, pixels_last) if a != b)
        change_ratio = diff_count / total if total > 0 else 0

        temp_path.unlink(missing_ok=True)
        return change_ratio > Config.CHANGE_THRESHOLD

    def update_last(self, screenshot_path: str):
                """Update reference for change detection."""
        self.last_screenshot_data = screenshot_path


# ==========================================================================
# VIMEO CONTROLLER - Interacts with embedded Vimeo player
# ==========================================================================
class VimeoController:
        """Controls a Vimeo player embedded in a Yardi Aspire page."""

    def __init__(self, driver):
                self.driver = driver
        self.iframe_handle = None

    def find_and_switch_to_player(self) -> bool:
                """Find the Vimeo iframe and switch context into it."""
        try:
                        iframe = WebDriverWait(self.driver, Config.ELEMENT_WAIT).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, Config.VIMEO_IFRAME_SEL))
        )
            self.driver.switch_to.frame(iframe)
            self.iframe_handle = iframe
            return True
except TimeoutException:
            print("    [warn] No Vimeo iframe found on this page")
            return False

    def play(self):
                """Click the play button inside the Vimeo player."""
        try:
                        play_btn = WebDriverWait(self.driver, Config.ELEMENT_WAIT).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, Config.VIMEO_PLAY_BTN))
        )
            play_btn.click()
            time.sleep(1)
            print("    [vimeo] Playing video")
except TimeoutException:
            # Try JavaScript play
            self.driver.execute_script(
                                "document.querySelector('video')?.play();"
            )
            print("    [vimeo] Playing video via JS")

    def pause(self):
                """Pause the video."""
        self.driver.execute_script(
                        "document.querySelector('video')?.pause();"
        )

    def get_duration(self) -> float:
                """Get video duration in seconds."""
        try:
                        return float(self.driver.execute_script(
                            "return document.querySelector('video')?.duration || 0;"
        ))
except Exception:
            return 0.0

    def get_current_time(self) -> float:
                """Get current playback position."""
        try:
                        return float(self.driver.execute_script(
                            "return document.querySelector('video')?.currentTime || 0;"
        ))
except Exception:
            return 0.0

    def seek_to(self, seconds: float):
                """Seek to a specific time."""
        self.driver.execute_script(
                        f"document.querySelector('video').currentTime = {seconds};"
        )
        time.sleep(0.5)

    def is_playing(self) -> bool:
                """Check if video is currently playing."""
        try:
                        return self.driver.execute_script(
                            "var v = document.querySelector('video'); "
                            "return v && !v.paused && !v.ended;"
        )
except Exception:
            return False

    def switch_back(self):
                """Switch back to the main page from the iframe."""
        self.driver.switch_to.default_content()


# ==========================================================================
# VIDEO LIBRARY SCANNER - Discovers videos in Yardi Aspire
# ==========================================================================
class VideoLibraryScanner:
        """Scans the Yardi Aspire Training Video Library for available videos."""

    def __init__(self, driver):
                self.driver = driver

    def scan(self) -> List[Dict[str, str]]:
                """Scan the page for video widgets and extract titles + URLs."""
        videos = []

        # Try to find video widgets with Vimeo data-src
        widgets = self.driver.find_elements(By.CSS_SELECTOR, Config.ASPIRE_VIDEO_WIDGET)

        if not widgets:
                        # Fallback: look for iframes directly
                        iframes = self.driver.find_elements(By.CSS_SELECTOR, Config.VIMEO_IFRAME_SEL)
            for i, iframe in enumerate(iframes):
                                src = iframe.get_attribute("src") or iframe.get_attribute("data-src") or ""
                                videos.append({
                                    "index": i,
                                    "title": f"Video {i + 1}",
                                    "url": src,
                                })
                            return videos

        # Extract titles - they are in h2.RL elements preceding each video widget
        titles = self.driver.find_elements(By.CSS_SELECTOR, Config.ASPIRE_TITLE_SEL)
        title_texts = [t.text.strip() for t in titles if t.text.strip()]

        for i, widget in enumerate(widgets):
                        src = widget.get_attribute(Config.ASPIRE_VIDEO_DATASRC) or ""
            # Try to match a title by position
            title = title_texts[i] if i < len(title_texts) else f"Video {i + 1}"
            videos.append({
                                "index": i,
                                "title": title,
                                "url": src,
            })

        return videos

    def find_video_by_title(self, title: str) -> Optional[Dict[str, str]]:
                """Find a specific video by partial title match."""
        videos = self.scan()
        title_lower = title.lower()
        for v in videos:
                        if title_lower in v["title"].lower():
                                            return v
                                    return None


# ==========================================================================
# INTERACTIVE REVIEWER - Terminal-based step review workflow
# ==========================================================================
class InteractiveReviewer:
        """Interactive terminal UI for reviewing and marking captured steps."""

    STATUS_OPTIONS = {
                "k": "keep",
                "m": "modify",
                "r": "remove",
                "d": "diverge",
                "s": "skip",
    }

    def __init__(self, project: ProjectManager):
                self.project = project

    def review_all(self):
                """Walk through all steps interactively."""
        steps = self.project.steps
        if not steps:
                        print("[!] No steps to review.")
            return

        print(f"\n{'='*60}")
        print(f" STEP REVIEW - {self.project.metadata.get('video_title', 'Untitled')}")
        print(f" {len(steps)} steps to review")
        print(f"{'='*60}")
        print(" Commands: (k)eep  (m)odify  (r)emove  (d)iverge  (s)kip")
        print(f"{'='*60}\n")

        for i, step in enumerate(steps):
                        print(f"\n--- Step {step.step_number} [{step.status}] ---")
            print(f"  Timestamp: {step.timestamp:.1f}s")
            print(f"  Description: {step.description}")
            if step.screenshot_path:
                                print(f"  Screenshot: {step.screenshot_path}")

            while True:
                                choice = input(f"\n  Action [k/m/r/d/s] (current: {step.status}): ").strip().lower()
                                if not choice:
                                                        break  # keep current status
                if choice not in self.STATUS_OPTIONS:
                                        print("  Invalid choice. Use k/m/r/d/s.")
                                        continue

                if choice == "s":
                                        break

                status = self.STATUS_OPTIONS[choice]
                step.status = status

                if status == "modify":
                                        new_desc = input("  New HACSM description: ").strip()
                                        if new_desc:
                                                                    step.hacsm_description = new_desc
                                                                note = input("  HACSM note (optional): ").strip()
                    if note:
                                                step.hacsm_note = note

elif status == "diverge":
                    step.divergence_yardi = input("  Yardi shows: ").strip()
                    step.divergence_hacsm = input("  HACSM does instead: ").strip()

                print(f"  -> Marked as: {status}")
                break

        self.project.metadata["phase"] = "review"
        self.project.save()

        # Print summary
        counts = {}
        for s in steps:
                        counts[s.status] = counts.get(s.status, 0) + 1
        print(f"\n{'='*60}")
        print(" Review Summary:")
        for status, count in sorted(counts.items()):
                        print(f"   {status}: {count}")
        print(f"{'='*60}\n")

    def insert_custom_step(self, after_step: int, description: str,
                                                      screenshot: str = "") -> StepData:
                                                                  """Insert a custom HACSM-only step after the given step number."""
                                                                  new_step = StepData(
                                                                      step_number=after_step + 1,
                                                                      description=f"[HACSM Custom] {description}",
                                                                      hacsm_description=description,
                                                                      status="custom",
                                                                      custom_screenshot_path=screenshot,
                                                                      tags=["hacsm-custom"],
                                                                  )

        # Find insertion point
        insert_idx = 0
        for i, s in enumerate(self.project.steps):
                        if s.step_number == after_step:
                                            insert_idx = i + 1
                                            break

        self.project.steps.insert(insert_idx, new_step)
        self.project.renumber_steps()
        print(f"[+] Custom step inserted after step {after_step}: {description}")
        return new_step


# ==========================================================================
# TRAINING GUIDE PUBLISHER - Generates HACSM-branded output
# ==========================================================================
class TrainingGuidePublisher:
        """Generates polished training documentation in multiple formats."""

    def __init__(self, project: ProjectManager):
                self.project = project

    def publish_all(self):
                """Generate all output formats."""
        steps = self.project.get_active_steps()
        title = self.project.metadata.get("video_title", "Training Guide")
        if Config.GENERATE_MARKDOWN:
                        self.publish_markdown(steps, title)
        if Config.GENERATE_HTML:
                        self.publish_html(steps, title)
        self.publish_json(steps, title)
        self.project.metadata["phase"] = "published"
        self.project.metadata["version"] = self.project.metadata.get("version", 0) + 1
        self.project.save()

    def publish_markdown(self, steps: List[StepData], title: str):
                """Generate a Markdown training guide."""
        org = Config.HACSM_BRANDING
        md = []
        md.append(f"# {org['org_short']} Training Guide: {title}")
        md.append(f"**{org['org_name']}** | Version {self.project.metadata.get('version', 1)} | {len(steps)} Steps\n---\n")
        md.append("## Table of Contents\n")
        for s in steps:
                        desc = s.hacsm_description or s.description
            md.append(f"- [Step {s.step_number}: {desc[:60]}](#step-{s.step_number})")
        md.append("\n---\n")

        for s in steps:
                        desc = s.hacsm_description or s.description
            md.append(f"## Step {s.step_number}: {desc}\n")

            if s.status == "custom":
                                md.append("> **HACSM-Specific Step** - This step is unique to HACSM processes.\n")
elif s.status == "diverge":
                md.append(f"> **Process Divergence:**")
                md.append(f"> - *Yardi shows:* {s.divergence_yardi}")
                md.append(f"> - *HACSM does:* {s.divergence_hacsm}\n")

            if s.hacsm_note:
                                md.append(f"**Note:** {s.hacsm_note}\n")

            screenshot = s.custom_screenshot_path or s.screenshot_path
            if screenshot:
                                md.append(f"![Step {s.step_number}]({screenshot})\n")

            if s.zoom_path:
                                md.append(f"*Detail view:*\n![Detail]({s.zoom_path})\n")

            md.append(f"*Timestamp: {s.timestamp:.1f}s*\n")
            md.append("---\n")

        md.append(f"\n*{org['footer']}*")
        md.append(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")

        output_path = self.project.output_dir / f"{title.replace(' ', '_')}_guide.md"
        with open(output_path, "w") as f:
                        f.write("\n".join(md))
        print(f"[+] Markdown guide: {output_path}")

    def publish_html(self, steps: List[StepData], title: str):
                """Generate an HTML training guide with embedded styles."""
        org = Config.HACSM_BRANDING
        html_parts = []
        html_parts.append(f"""<!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>{org['org_short']} - {title}</title>
                        <style>
                                body {{ font-family: Arial, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; }}
                                        .header {{ background: #1a365d; color: white; padding: 20px; border-radius: 8px; margin-bottom: 30px; }}
                                                .header h1 {{ margin: 0; font-size: 1.5em; }}
                                                        .header .org {{ font-size: 0.9em; opacity: 0.9; }}
                                                                .step {{ border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin-bottom: 20px; }}
                                                                        .step h2 {{ color: #1a365d; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; }}
                                                                                .step img {{ max-width: 100%; border: 1px solid #ccc; border-radius: 4px; margin: 10px 0; }}
                                                                                        .badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.8em; font-weight: bold; }}
                                                                                                .badge-custom {{ background: #c6f6d5; color: #22543d; }}
                                                                                                        .badge-diverge {{ background: #fed7d7; color: #9b2c2c; }}
                                                                                                                .note {{ background: #ebf8ff; border-left: 4px solid #3182ce; padding: 10px 15px; margin: 10px 0; }}
                                                                                                                        .diverge {{ background: #fff5f5; border-left: 4px solid #e53e3e; padding: 10px 15px; margin: 10px 0; }}
                                                                                                                                .footer {{ text-align: center; color: #718096; font-size: 0.85em; margin-top: 40px; padding-top: 20px; border-top: 1px solid #e2e8f0; }}
                                                                                                                                        .toc {{ background: #f7fafc; padding: 15px; border-radius: 8px; margin-bottom: 30px; }}
                                                                                                                                                .toc a {{ text-decoration: none; color: #2b6cb0; }}
                                                                                                                                                    </style>
                                                                                                                                                    </head>
                                                                                                                                                    <body>
                                                                                                                                                        <div class="header">
                                                                                                                                                                <h1>{title}</h1>
                                                                                                                                                                        <div class="org">{org['org_name']} | Version {self.project.metadata.get('version', 1)} | {len(steps)} Steps</div>
                                                                                                                                                                            </div>
                                                                                                                                                                                <div class="toc"><h3>Table of Contents</h3><ol>""")

        for s in steps:
                        desc = s.hacsm_description or s.description
            html_parts.append(f'        <li><a href="#step-{s.step_number}">{desc[:80]}</a></li>')
        html_parts.append("    </ol></div>")

        for s in steps:
                        desc = s.hacsm_description or s.description
            html_parts.append(f'    <div class="step" id="step-{s.step_number}">')
            badge = ""
            if s.status == "custom":
                                badge = ' <span class="badge badge-custom">HACSM Custom</span>'
elif s.status == "diverge":
                badge = ' <span class="badge badge-diverge">Process Differs</span>'
            html_parts.append(f"        <h2>Step {s.step_number}: {desc}{badge}</h2>")

            if s.status == "diverge" and (s.divergence_yardi or s.divergence_hacsm):
                                html_parts.append(f'        <div class="diverge">')
                html_parts.append(f"            <strong>Yardi shows:</strong> {s.divergence_yardi}<br>")
                html_parts.append(f"            <strong>HACSM does:</strong> {s.divergence_hacsm}")
                html_parts.append(f"        </div>")

            if s.hacsm_note:
                                html_parts.append(f'        <div class="note">{s.hacsm_note}</div>')

            screenshot = s.custom_screenshot_path or s.screenshot_path
            if screenshot:
                                html_parts.append(f'        <img src="{screenshot}" alt="Step {s.step_number}">')
            if s.zoom_path:
                                html_parts.append(f'        <p><em>Detail view:</em></p>')
                html_parts.append(f'        <img src="{s.zoom_path}" alt="Detail">')

            html_parts.append(f"        <p><small>Timestamp: {s.timestamp:.1f}s</small></p>")
            html_parts.append("    </div>")

        html_parts.append(f'    <div class="footer">')
        html_parts.append(f"        <p>{org['footer']}</p>")
        html_parts.append(f"        <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>")
        html_parts.append("    </div>\n</body>\n</html>")

        output_path = self.project.output_dir / f"{title.replace(' ', '_')}_guide.html"
        with open(output_path, "w") as f:
                        f.write("\n".join(html_parts))
        print(f"[+] HTML guide: {output_path}")

    def publish_json(self, steps: List[StepData], title: str):
                """Export structured JSON for further processing."""
        data = {
                        "title": title,
                        "organization": Config.HACSM_BRANDING,
                        "metadata": self.project.metadata,
                        "steps": [s.to_dict() for s in steps],
                        "generated": datetime.now().isoformat(),
        }
        output_path = self.project.output_dir / f"{title.replace(' ', '_')}_guide.json"
        with open(output_path, "w") as f:
                        json.dump(data, f, indent=2)
        print(f"[+] JSON export: {output_path}")


# ==========================================================================
# CAPTURE WORKFLOW - Main video capture logic
# ==========================================================================
def run_capture(driver, url: str, project: ProjectManager,
                                video_title: str = None, capture_all: bool = False):
                                        """Run the capture workflow against a Yardi Aspire page."""
    print(f"\n[*] Navigating to: {url}")
    driver.get(url)

    # Wait for manual login
    print(f"[!] Please log in to Yardi Aspire in the browser window.")
    print(f"    Waiting up to {Config.LOGIN_WAIT}s for the dashboard to load...")
    try:
                WebDriverWait(driver, Config.LOGIN_WAIT).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, "body"))
                )
        # Additional wait for page to fully render
        time.sleep(3)
except TimeoutException:
        print("[!] Timeout waiting for page load. Continuing anyway...")

    input("\n[Press ENTER when you are logged in and ready to capture]\n")

    scanner = VideoLibraryScanner(driver)
    screenshotter = ScreenshotEngine(driver, project)
    vimeo = VimeoController(driver)

    if capture_all:
                videos = scanner.scan()
        if not videos:
                        print("[!] No videos found on this page.")
            return
        print(f"[+] Found {len(videos)} videos. Starting batch capture...")
        for vid in videos:
                        _capture_single_video(driver, vid, project, screenshotter, vimeo)
elif video_title:
        vid = scanner.find_video_by_title(video_title)
        if not vid:
                        print(f"[!] No video found matching: {video_title}")
            print("    Available videos:")
            for v in scanner.scan():
                                print(f"      - {v['title']}")
            return
        _capture_single_video(driver, vid, project, screenshotter, vimeo)
else:
        print("[!] No --all or --video-title specified. Use 'list' to see available videos.")
        return

    project.metadata["phase"] = "captured"
    project.save()
    print(f"\n[+] Capture complete! {len(project.steps)} steps captured.")
    print(f"    Project saved to: {project.project_dir}")


def _capture_single_video(driver, video_info: dict, project: ProjectManager,
                                                    screenshotter: ScreenshotEngine, vimeo: VimeoController):
                                                            """Capture a single video's content."""
                                                            title = video_info.get("title", "Untitled")
                                                            url = video_info.get("url", "")
                                                            print(f"\n{'='*60}")
                                                            print(f"  Capturing: {title}")
                                                            print(f"  URL: {url}")
                                                            print(f"{'='*60}")

    project.metadata["video_title"] = title
    project.metadata["video_url"] = url

    # If the video URL is a Vimeo embed, try to activate it
    if "vimeo" in url.lower():
                # Click on the video widget to load the iframe
                try:
                                widgets = driver.find_elements(By.CSS_SELECTOR, Config.ASPIRE_VIDEO_WIDGET)
                                for w in widgets:
                                                    ds = w.get_attribute(Config.ASPIRE_VIDEO_DATASRC) or ""
                                                    if url in ds or ds in url:
                                                                            w.click()
                                                                            time.sleep(2)
                                                                            break
                except Exception as e:
            print(f"    [warn] Could not click video widget: {e}")

    # Try to switch into the Vimeo iframe
    if not vimeo.find_and_switch_to_player():
                # Capture whatever is on screen as a single step
                print("    [info] No Vimeo player found, capturing current screen")
                path = screenshotter.capture_full(label="overview")
                project.add_step(StepData(
                    step_number=1, description=f"Overview: {title}",
                    screenshot_path=str(path), status="draft",
                ))
                return

    # Get video duration and set up capture
    duration = vimeo.get_duration()
    if duration <= 0:
                duration = Config.MAX_CAPTURE_DURATION
            print(f"    [info] Video duration: {duration:.1f}s")

    # Play the video and capture at intervals
    vimeo.play()
    start_time = time.time()
    step_num = 0

    interval = Config.CAPTURE_INTERVAL
    current_pos = 0.0

    while current_pos < duration:
                vimeo.seek_to(current_pos)
                time.sleep(0.5)

        # Switch back to main frame to capture the full page
                vimeo.switch_back()

        if screenshotter.has_significant_change():
                        step_num += 1
                        label = f"t{current_pos:.0f}s"
                        path = screenshotter.capture_full(label=label)
                        zoom_path = ""
                        if Config.ZOOM_REGIONS:
                                            zoom_path = screenshotter.capture_zoom(label=label)
                                        screenshotter.update_last(path)

            project.add_step(StepData(
                                step_number=step_num,
                                timestamp=current_pos,
                                description=f"Step at {current_pos:.1f}s",
                                screenshot_path=str(path),
                                zoom_path=str(zoom_path),
                                status="draft",
            ))

        # Switch back into iframe for next seek
        vimeo.find_and_switch_to_player()
        current_pos += interval

        # Safety timeout
        if time.time() - start_time > Config.MAX_CAPTURE_DURATION:
                        print("    [warn] Hit max capture duration, stopping")
            break

    vimeo.pause()
    vimeo.switch_back()
    print(f"    [+] Captured {step_num} steps for: {title}")


# ==========================================================================
# CLI - Command Line Interface
# ==========================================================================
def build_cli() -> argparse.ArgumentParser:
        """Build the argument parser."""
    parser = argparse.ArgumentParser(
                prog="video_capture_tool",
                description="HACSM Training Video Capture & Customization Tool v2.1",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # --- capture ---
    cap = sub.add_parser("capture", help="Capture screenshots from training videos")
    cap.add_argument("--url", required=True, help="Yardi Aspire URL")
    cap.add_argument("--browser", default="chrome", help="Browser to use (default: chrome)")
    cap.add_argument("--browser-path", default=None, help="Custom browser binary path")
    cap.add_argument("--headless", action="store_true", help="Run headless (no GUI)")
    cap.add_argument("--output", default=None, help="Project output directory")
    cap.add_argument("--all", action="store_true", dest="capture_all", help="Capture all videos")
    cap.add_argument("--video-title", default=None, help="Capture a specific video by title")
    cap.add_argument("--interval", type=float, default=None, help="Capture interval in seconds")

    # --- list ---
    lst = sub.add_parser("list", help="List available videos on an Aspire page")
    lst.add_argument("--url", required=True, help="Yardi Aspire URL")
    lst.add_argument("--browser", default="chrome", help="Browser to use")
    lst.add_argument("--browser-path", default=None, help="Custom browser binary path")

    # --- review ---
    rev = sub.add_parser("review", help="Interactively review captured steps")
    rev.add_argument("--project", required=True, help="Path to project directory")

    # --- customize ---
    cust = sub.add_parser("customize", help="Customize steps in a project")
    cust.add_argument("--project", required=True, help="Path to project directory")
    cust.add_argument("action", choices=["insert", "modify", "remove", "diverge", "status"],
                                            help="Customization action")
    cust.add_argument("--step", type=int, help="Step number to act on")
    cust.add_argument("--description", default="", help="Description text")
    cust.add_argument("--screenshot", default="", help="Path to custom screenshot")
    cust.add_argument("--note", default="", help="HACSM note")
    cust.add_argument("--yardi-shows", default="", help="What Yardi shows (for diverge)")
    cust.add_argument("--hacsm-does", default="", help="What HACSM does instead (for diverge)")

    # --- publish ---
    pub = sub.add_parser("publish", help="Generate training guide output")
    pub.add_argument("--project", required=True, help="Path to project directory")
    pub.add_argument("--format", choices=["all", "markdown", "html", "json"],
                                          default="all", help="Output format (default: all)")

    # --- browsers ---
    sub.add_parser("browsers", help="List available browsers on this system")

    return parser


def main():
        """Main entry point."""
    parser = build_cli()
    args = parser.parse_args()

    if not args.command:
                parser.print_help()
        sys.exit(1)

    # --- browsers command ---
    if args.command == "browsers":
                print("\nAvailable Browsers:")
        print("-" * 50)
        for b in BrowserManager.list_available_browsers():
                        status = "INSTALLED" if b["installed"] else "not found"
            print(f"  {b['name']:12s} [{status}]  {b['path']}")
        print()
        sys.exit(0)

    # --- review command ---
    if args.command == "review":
                project = ProjectManager(args.project)
        project.load()
        reviewer = InteractiveReviewer(project)
        reviewer.review_all()
        sys.exit(0)

    # --- customize command ---
    if args.command == "customize":
                project = ProjectManager(args.project)
        project.load()
        reviewer = InteractiveReviewer(project)

        if args.action == "status":
                        print(f"\nProject: {project.metadata.get('video_title', 'Untitled')}")
            print(f"Phase: {project.metadata.get('phase')}")
            print(f"Total steps: {len(project.steps)}")
            counts = {}
            for s in project.steps:
                                counts[s.status] = counts.get(s.status, 0) + 1
                            for status, count in sorted(counts.items()):
                                                print(f"  {status}: {count}")
                                            sys.exit(0)

        if not args.step:
                        print("[!] --step is required for insert/modify/remove/diverge")
            sys.exit(1)

        if args.action == "insert":
                        reviewer.insert_custom_step(args.step, args.description, args.screenshot)

elif args.action == "modify":
            for s in project.steps:
                                if s.step_number == args.step:
                                                        s.status = "modify"
                                                        if args.description:
                                                                                    s.hacsm_description = args.description
                                                                                if args.note:
                                                                                                            s.hacsm_note = args.note
                                                                                                        print(f"[+] Step {args.step} modified.")
                                                        break
                                                project.save()

elif args.action == "remove":
            for s in project.steps:
                                if s.step_number == args.step:
                                                        s.status = "remove"
                                                        print(f"[+] Step {args.step} marked for removal.")
                                                        break
                                                project.save()

elif args.action == "diverge":
            for s in project.steps:
                                if s.step_number == args.step:
                                                        s.status = "diverge"
                                                        s.divergence_yardi = args.yardi_shows
                                                        s.divergence_hacsm = args.hacsm_does
                                                        print(f"[+] Step {args.step} marked as divergent.")
                                                        break
                                                project.save()

        sys.exit(0)

    # --- publish command ---
    if args.command == "publish":
                project = ProjectManager(args.project)
        project.load()
        publisher = TrainingGuidePublisher(project)
        if args.format == "all":
                        publisher.publish_all()
else:
            steps = project.get_active_steps()
            title = project.metadata.get("video_title", "Training Guide")
            if args.format == "markdown":
                                publisher.publish_markdown(steps, title)
elif args.format == "html":
                publisher.publish_html(steps, title)
elif args.format == "json":
                publisher.publish_json(steps, title)
            project.save()
        sys.exit(0)

    # --- Commands that need a browser ---
    if not SELENIUM_AVAILABLE:
                print("[!] Selenium is required for capture and list commands.")
        print("    Install it: pip install selenium")
        sys.exit(1)

    driver = BrowserManager.create_driver(
                browser=args.browser,
                custom_path=getattr(args, "browser_path", None),
                headless=getattr(args, "headless", False),
    )

    try:
                if args.command == "list":
                                print(f"\n[*] Navigating to: {args.url}")
            driver.get(args.url)
            input("\n[Press ENTER when logged in and ready]\n")
            scanner = VideoLibraryScanner(driver)
            videos = scanner.scan()
            print(f"\nFound {len(videos)} videos:")
            print("-" * 60)
            for v in videos:
                                print(f"  [{v['index']:3d}] {v['title']}")
                if v['url']:
                                        print(f"        URL: {v['url'][:80]}")
                                print()

elif args.command == "capture":
            if args.interval:
                                Config.CAPTURE_INTERVAL = args.interval
            output = args.output or os.path.join(
                                Config.OUTPUT_DIR,
                                re.sub(r'[^\w\-]', '_', args.video_title or "batch")[:50]
                                + f"_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            project = ProjectManager(output)
            project.create(video_title=args.video_title or "Batch Capture", video_url=args.url)
            run_capture(driver, args.url, project,
                                               video_title=args.video_title, capture_all=args.capture_all)

finally:
        driver.quit()
        print("[*] Browser closed.")


if __name__ == "__main__":
        main()
