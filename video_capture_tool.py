


# ================================================================
# TRAINING GUIDE PUBLISHER - Generates HACSM-branded output
# ================================================================
class TrainingGuidePublisher:
    def __init__(self, project): self.project = project

    def publish_all(self):
        steps = self.project.get_active_steps()
        title = self.project.metadata.get("video_title", "Training Guide")
        if Config.GENERATE_MARKDOWN: self.publish_markdown(steps, title)
        if Config.GENERATE_HTML: self.publish_html(steps, title)
        self.publish_json(steps, title)
        self.project.metadata["phase"] = "published"
        self.project.metadata["version"] = self.project.metadata.get("version", 0) + 1
        self.project.save()

    def publish_markdown(self, steps, title):
        org = Config.HACSM_BRANDING; md = []
        md.append(f"# {org['org_short']} Training Guide: {title}")
        md.append(f"**{org['org_name']}** | Version {self.project.metadata.get('version',1)} | {len(steps)} Steps\n---\n")
        md.append("## Table of Contents\n")
        for s in steps:
            desc = s.hacsm_description or s.description
            badge = " [HACSM Custom]" if s.status == StepData.STATUS_CUSTOM else (" [Modified]" if s.status == StepData.STATUS_DIVERGE else "")
            md.append(f"- Step {s.step_number}: {desc[:60]}{badge}")
        md.append("\n---\n")
        for s in steps:
            desc = s.hacsm_description or s.description
            md.append(f"### Step {s.step_number}: {desc}")
            if s.timestamp_seconds > 0: md.append(f"*Video ref: {s.timestamp_formatted}*\n")
            if s.status == StepData.STATUS_CUSTOM: md.append("> **HACSM-SPECIFIC STEP** - Not in Yardi training\n")
            elif s.status == StepData.STATUS_DIVERGE: md.append(f"> **PROCESS DIFFERENCE:** {s.divergence_note}\n")
            if s.screenshot_path: md.append(f"![Step {s.step_number}](../screenshots/{os.path.basename(s.custom_screenshot_path or s.screenshot_path)})\n")
            for z in s.zoom_paths: md.append(f"![Detail](../screenshots/{os.path.basename(z)})\n")
            if s.hacsm_notes: md.append(f"> **Note:** {s.hacsm_notes}\n")
            md.append("---\n")
        with open(self.project.output_dir / "training_guide.md", 'w') as f: f.write('\n'.join(md))

    def publish_html(self, steps, title):
        org = Config.HACSM_BRANDING
        css = f"""body{{font-family:'Segoe UI',Arial;max-width:1200px;margin:0 auto;padding:20px;background:#f8fafc}}
.header{{background:{org['primary_color']};color:white;padding:30px;border-radius:8px;margin-bottom:30px}}
.step{{background:white;border-radius:8px;padding:24px;margin:16px 0;box-shadow:0 1px 3px rgba(0,0,0,.12)}}
.step img{{max-width:100%;border:1px solid #e2e8f0;border-radius:4px;margin:12px 0}}
.step-header{{color:{org['primary_color']};border-bottom:2px solid {org['accent_color']};padding-bottom:8px}}
.badge-custom{{background:#48bb78;color:white;padding:2px 10px;border-radius:12px;font-size:.8em}}
.badge-diverge{{background:#ed8936;color:white;padding:2px 10px;border-radius:12px;font-size:.8em}}
.diverge-box{{background:#fffaf0;border-left:4px solid #ed8936;padding:12px;margin:12px 0}}
.custom-box{{background:#f0fff4;border-left:4px solid #48bb78;padding:12px;margin:12px 0}}
.notes-box{{background:#ebf8ff;border-left:4px solid #4299e1;padding:12px;margin:12px 0;font-style:italic}}"""
        html = [f"<!DOCTYPE html><html><head><title>{org['org_short']} - {title}</title><style>{css}</style></head><body>"]
        html.append(f'<div class="header"><h1>{org["org_short"]} Training Guide</h1><h2>{title}</h2></div>')
        for s in steps:
            desc = s.hacsm_description or s.description
            html.append(f'<div class="step"><h2 class="step-header">Step {s.step_number}: {desc}</h2>')
            if s.status == StepData.STATUS_CUSTOM: html.append('<div class="custom-box"><strong>HACSM-SPECIFIC STEP</strong></div>')
            elif s.status == StepData.STATUS_DIVERGE and s.divergence_note: html.append(f'<div class="diverge-box"><strong>PROCESS DIFFERENCE:</strong> {s.divergence_note}</div>')
            img = s.custom_screenshot_path or s.screenshot_path
            if img: html.append(f'<img src="../screenshots/{os.path.basename(img)}" alt="Step {s.step_number}">')
            if s.hacsm_notes: html.append(f'<div class="notes-box"><strong>Note:</strong> {s.hacsm_notes}</div>')
            html.append('</div>')
        html.append("</body></html>")
        with open(self.project.output_dir / "training_guide.html", 'w') as f: f.write('\n'.join(html))

    def publish_json(self, steps, title):
        with open(self.project.output_dir / "training_guide.json", 'w') as f:
            json.dump({"title": title, "org": Config.HACSM_BRANDING, "metadata": self.project.metadata, "steps": [s.to_dict() for s in steps]}, f, indent=2)


# ================================================================
# MAIN ORCHESTRATOR
# ================================================================
class VideoCaptureOrchestrator:
    def __init__(self, browser_name="chrome", headless=False, browser_path=None):
        self.browser = BrowserManager(browser_name, headless, browser_path)
        self.driver = None; self.vimeo = None

    def setup(self):
        self.driver = self.browser.start(); self.vimeo = VimeoController(self.driver)
        self.driver.get(Config.BASE_URL)
        print("="*60 + "\n  Log in to HACSM University (Vimeo requires active session)\n  Press Enter when ready...\n" + "="*60)
        input()

    def capture_single_video(self, video_title=None, video_index=0):
        safe_title = re.sub(r'[^a-zA-Z0-9_-]', '_', video_title or f"video_{video_index}")
        project = ProjectManager(Path(Config.OUTPUT_DIR) / safe_title)
        project.create(video_title=video_title or f"Video {video_index}")
        engine = ScreenshotEngine(self.driver, project.screenshots_dir)
        scanner = VideoLibraryScanner(self.driver); scanner.open_library()
        if video_title: self._click_video_by_title(video_title)
        else: self._click_video_by_index(video_index)
        time.sleep(3)
        if not self.vimeo.switch_to_player(): return
        duration = self.vimeo.get_duration() or Config.MAX_VIDEO_DURATION_MINUTES * 60
        self._capture_frames(duration, engine, project)
        self.vimeo.switch_to_main()
        project.metadata["phase"] = "captured"; project.save()
        print(f"\n  DONE: {video_title} | {len(project.steps)} steps | Next: run 'review'")

    def _capture_frames(self, duration, engine, project):
        interval = Config.SCREENSHOT_INTERVAL_SECONDS; step_count = 0
        try: self.vimeo.pause()
        except: pass
        for i in range(int(duration / interval) + 1):
            t = i * interval
            if t > duration: break
            self.vimeo.seek_to(t); time.sleep(0.5)
            self.vimeo.switch_to_main()
            fp, img = engine.capture_full(label=f"t{int(t):04d}")
            if engine.has_significant_change(img):
                zooms = []
                if Config.ZOOM_REGIONS_ENABLED:
                    for region, label in engine.detect_ui_regions(img):
                        try: zp, _ = engine.capture_zoom(img, region, label); zooms.append(zp)
                        except: pass
                step_count += 1
                project.add_step(StepData(step_count, t, fp, zooms,
                    f"Screen at {int(t//60):02d}:{int(t%60):02d} - [Edit for HACSM]"))
            else: os.remove(fp); engine.step_counter -= 1
            self.vimeo.switch_to_player()

    def capture_all_videos(self):
        scanner = VideoLibraryScanner(self.driver); scanner.open_library()
        for v in scanner.get_all_videos():
            if v['has_video']:
                try: self.capture_single_video(video_title=v['title'])
                except Exception as e: print(f"  [ERROR] {e}")

    def list_all_videos(self):
        scanner = VideoLibraryScanner(self.driver); scanner.open_library()
        for v in scanner.get_all_videos():
            print(f"  [{'VIDEO' if v['has_video'] else 'PDF'}] {v['title']}")

    def _click_video_by_title(self, title):
        widgets = self.driver.find_elements(By.CSS_SELECTOR, Config.VIDEO_WIDGET_SELECTOR)
        titles = self.driver.find_elements(By.CSS_SELECTOR, Config.TITLE_SELECTOR)
        for i, t in enumerate(titles):
            if title.lower() in t.text.lower(): widgets[i].click(); return

    def _click_video_by_index(self, idx):
        self.driver.find_elements(By.CSS_SELECTOR, Config.VIDEO_WIDGET_SELECTOR)[idx].click()

    def cleanup(self): self.browser.stop()


# ================================================================
# CLI - Command Line Interface
# ================================================================
def main():
    parser = argparse.ArgumentParser(description="HACSM Training Video Capture & Customization Tool v2.0")
    sub = parser.add_subparsers(dest="command")

    cap = sub.add_parser("capture", help="Capture video screenshots")
    cap.add_argument("--video-title", type=str); cap.add_argument("--all", action="store_true")
    cap.add_argument("--interval", type=int, default=5); cap.add_argument("--browser", type=str, default="chrome")
    cap.add_argument("--browser-path", type=str); cap.add_argument("--headless", action="store_true")
    cap.add_argument("--no-zoom", action="store_true"); cap.add_argument("--output", type=str, default="training_video_captures")
    cap.add_argument("--url", type=str, default=Config.BASE_URL)

    sub.add_parser("list", help="List videos").add_argument("--browser", type=str, default="chrome")

    rev = sub.add_parser("review", help="Interactive review"); rev.add_argument("--project", required=True)
    rev.add_argument("--output", type=str, default="training_video_captures")

    cust = sub.add_parser("customize", help="Programmatic customization"); cust.add_argument("--project", required=True)
    cust.add_argument("--output", default="training_video_captures"); cust.add_argument("--insert-after", type=int)
    cust.add_argument("--description", type=str); cust.add_argument("--modify-step", type=int)
    cust.add_argument("--hacsm-desc", type=str); cust.add_argument("--diverge", type=str)
    cust.add_argument("--notes", type=str); cust.add_argument("--remove-step", type=int)

    pub = sub.add_parser("publish", help="Generate final training docs"); pub.add_argument("--project", required=True)
    pub.add_argument("--output", default="training_video_captures")
    pub.add_argument("--no-html", action="store_true"); pub.add_argument("--no-markdown", action="store_true")

    sub.add_parser("browsers", help="List supported browsers")
    args = parser.parse_args()
    if not args.command: parser.print_help(); return

    if args.command == "browsers": BrowserManager.list_supported_browsers(); return
    if args.command == "review":
        p = ProjectManager(Path(args.output) / args.project); p.load()
        InteractiveReviewer(p).start_review(); return
    if args.command == "customize":
        p = ProjectManager(Path(args.output) / args.project); p.load()
        if args.insert_after and args.description: p.insert_custom_step(args.insert_after, args.description, notes=args.notes or "")
        elif args.modify_step: p.modify_step(args.modify_step, args.hacsm_desc, args.diverge, args.notes)
        elif args.remove_step: p.remove_step(args.remove_step)
        return
    if args.command == "publish":
        Config.GENERATE_HTML = not getattr(args, 'no_html', False)
        Config.GENERATE_MARKDOWN = not getattr(args, 'no_markdown', False)
        p = ProjectManager(Path(args.output) / args.project); p.load()
        TrainingGuidePublisher(p).publish_all(); return

    Config.SCREENSHOT_INTERVAL_SECONDS = getattr(args, 'interval', 5)
    Config.OUTPUT_DIR = getattr(args, 'output', 'training_video_captures')
    Config.BASE_URL = getattr(args, 'url', Config.BASE_URL)
    Config.ZOOM_REGIONS_ENABLED = not getattr(args, 'no_zoom', False)
    orch = VideoCaptureOrchestrator(getattr(args, 'browser', 'chrome'), getattr(args, 'headless', False), getattr(args, 'browser_path', None))
    try:
        orch.setup()
        if args.command == "list": orch.list_all_videos()
        elif args.command == "capture":
            if args.all: orch.capture_all_videos()
            elif args.video_title: orch.capture_single_video(video_title=args.video_title)
    except KeyboardInterrupt: print("\nInterrupted.")
    finally: orch.cleanup()

if __name__ == "__main__":
    main()


# ================================================================
# TRAINING GUIDE PUBLISHER - Generates HACSM-branded output
# ================================================================
class TrainingGuidePublisher:
    def __init__(self, project): self.project = project

    def publish_all(self):
        steps = self.project.get_active_steps()
        title = self.project.metadata.get("video_title", "Training Guide")
        if Config.GENERATE_MARKDOWN: self.publish_markdown(steps, title)
        if Config.GENERATE_HTML: self.publish_html(steps, title)
        self.publish_json(steps, title)
        self.project.metadata["phase"] = "published"
        self.project.metadata["version"] = self.project.metadata.get("version", 0) + 1
        self.project.save()

    def publish_markdown(self, steps, title):
        org = Config.HACSM_BRANDING; md = []
        md.append(f"# {org['org_short']} Training Guide: {title}")
        md.append(f"**{org['org_name']}** | Version {self.project.metadata.get('version',1)} | {len(steps)} Steps\n---\n")
        md.append("## Table of Contents\n")
        for s in steps:
            desc = s.hacsm_description or s.description
            badge = " [HACSM Custom]" if s.status == StepData.STATUS_CUSTOM else (" [Modified]" if s.status == StepData.STATUS_DIVERGE else "")
            md.append(f"- Step {s.step_number}: {desc[:60]}{badge}")
        md.append("\n---\n")
        for s in steps:
            desc = s.hacsm_description or s.description
            md.append(f"### Step {s.step_number}: {desc}")
            if s.timestamp_seconds > 0: md.append(f"*Video ref: {s.timestamp_formatted}*\n")
            if s.status == StepData.STATUS_CUSTOM: md.append("> **HACSM-SPECIFIC STEP** - Not in Yardi training\n")
            elif s.status == StepData.STATUS_DIVERGE: md.append(f"> **PROCESS DIFFERENCE:** {s.divergence_note}\n")
            if s.screenshot_path: md.append(f"![Step {s.step_number}](../screenshots/{os.path.basename(s.custom_screenshot_path or s.screenshot_path)})\n")
            for z in s.zoom_paths: md.append(f"![Detail](../screenshots/{os.path.basename(z)})\n")
            if s.hacsm_notes: md.append(f"> **Note:** {s.hacsm_notes}\n")
            md.append("---\n")
        with open(self.project.output_dir / "training_guide.md", 'w') as f: f.write('\n'.join(md))

    def publish_html(self, steps, title):
        org = Config.HACSM_BRANDING
        css = f"""body{{font-family:'Segoe UI',Arial;max-width:1200px;margin:0 auto;padding:20px;background:#f8fafc}}
.header{{background:{org['primary_color']};color:white;padding:30px;border-radius:8px;margin-bottom:30px}}
.step{{background:white;border-radius:8px;padding:24px;margin:16px 0;box-shadow:0 1px 3px rgba(0,0,0,.12)}}
.step img{{max-width:100%;border:1px solid #e2e8f0;border-radius:4px;margin:12px 0}}
.step-header{{color:{org['primary_color']};border-bottom:2px solid {org['accent_color']};padding-bottom:8px}}
.badge-custom{{background:#48bb78;color:white;padding:2px 10px;border-radius:12px;font-size:.8em}}
.badge-diverge{{background:#ed8936;color:white;padding:2px 10px;border-radius:12px;font-size:.8em}}
.diverge-box{{background:#fffaf0;border-left:4px solid #ed8936;padding:12px;margin:12px 0}}
.custom-box{{background:#f0fff4;border-left:4px solid #48bb78;padding:12px;margin:12px 0}}
.notes-box{{background:#ebf8ff;border-left:4px solid #4299e1;padding:12px;margin:12px 0;font-style:italic}}"""
        html = [f"<!DOCTYPE html><html><head><title>{org['org_short']} - {title}</title><style>{css}</style></head><body>"]
        html.append(f'<div class="header"><h1>{org["org_short"]} Training Guide</h1><h2>{title}</h2></div>')
        for s in steps:
            desc = s.hacsm_description or s.description
            html.append(f'<div class="step"><h2 class="step-header">Step {s.step_number}: {desc}</h2>')
            if s.status == StepData.STATUS_CUSTOM: html.append('<div class="custom-box"><strong>HACSM-SPECIFIC STEP</strong></div>')
            elif s.status == StepData.STATUS_DIVERGE and s.divergence_note: html.append(f'<div class="diverge-box"><strong>PROCESS DIFFERENCE:</strong> {s.divergence_note}</div>')
            img = s.custom_screenshot_path or s.screenshot_path
            if img: html.append(f'<img src="../screenshots/{os.path.basename(img)}" alt="Step {s.step_number}">')
            if s.hacsm_notes: html.append(f'<div class="notes-box"><strong>Note:</strong> {s.hacsm_notes}</div>')
            html.append('</div>')
        html.append("</body></html>")
        with open(self.project.output_dir / "training_guide.html", 'w') as f: f.write('\n'.join(html))

    def publish_json(self, steps, title):
        with open(self.project.output_dir / "training_guide.json", 'w') as f:
            json.dump({"title": title, "org": Config.HACSM_BRANDING, "metadata": self.project.metadata, "steps": [s.to_dict() for s in steps]}, f, indent=2)


# ================================================================
# MAIN ORCHESTRATOR
# ================================================================
class VideoCaptureOrchestrator:
    def __init__(self, browser_name="chrome", headless=False, browser_path=None):
        self.browser = BrowserManager(browser_name, headless, browser_path)
        self.driver = None; self.vimeo = None

    def setup(self):
        self.driver = self.browser.start(); self.vimeo = VimeoController(self.driver)
        self.driver.get(Config.BASE_URL)
        print("="*60 + "\n  Log in to HACSM University (Vimeo requires active session)\n  Press Enter when ready...\n" + "="*60)
        input()

    def capture_single_video(self, video_title=None, video_index=0):
        safe_title = re.sub(r'[^a-zA-Z0-9_-]', '_', video_title or f"video_{video_index}")
        project = ProjectManager(Path(Config.OUTPUT_DIR) / safe_title)
        project.create(video_title=video_title or f"Video {video_index}")
        engine = ScreenshotEngine(self.driver, project.screenshots_dir)
        scanner = VideoLibraryScanner(self.driver); scanner.open_library()
        if video_title: self._click_video_by_title(video_title)
        else: self._click_video_by_index(video_index)
        time.sleep(3)
        if not self.vimeo.switch_to_player(): return
        duration = self.vimeo.get_duration() or Config.MAX_VIDEO_DURATION_MINUTES * 60
        self._capture_frames(duration, engine, project)
        self.vimeo.switch_to_main()
        project.metadata["phase"] = "captured"; project.save()
        print(f"\n  DONE: {video_title} | {len(project.steps)} steps | Next: run 'review'")

    def _capture_frames(self, duration, engine, project):
        interval = Config.SCREENSHOT_INTERVAL_SECONDS; step_count = 0
        try: self.vimeo.pause()
        except: pass
        for i in range(int(duration / interval) + 1):
            t = i * interval
            if t > duration: break
            self.vimeo.seek_to(t); time.sleep(0.5)
            self.vimeo.switch_to_main()
            fp, img = engine.capture_full(label=f"t{int(t):04d}")
            if engine.has_significant_change(img):
                zooms = []
                if Config.ZOOM_REGIONS_ENABLED:
                    for region, label in engine.detect_ui_regions(img):
                        try: zp, _ = engine.capture_zoom(img, region, label); zooms.append(zp)
                        except: pass
                step_count += 1
                project.add_step(StepData(step_count, t, fp, zooms,
                    f"Screen at {int(t//60):02d}:{int(t%60):02d} - [Edit for HACSM]"))
            else: os.remove(fp); engine.step_counter -= 1
            self.vimeo.switch_to_player()

    def capture_all_videos(self):
        scanner = VideoLibraryScanner(self.driver); scanner.open_library()
        for v in scanner.get_all_videos():
            if v['has_video']:
                try: self.capture_single_video(video_title=v['title'])
                except Exception as e: print(f"  [ERROR] {e}")

    def list_all_videos(self):
        scanner = VideoLibraryScanner(self.driver); scanner.open_library()
        for v in scanner.get_all_videos():
            print(f"  [{'VIDEO' if v['has_video'] else 'PDF'}] {v['title']}")

    def _click_video_by_title(self, title):
        widgets = self.driver.find_elements(By.CSS_SELECTOR, Config.VIDEO_WIDGET_SELECTOR)
        titles = self.driver.find_elements(By.CSS_SELECTOR, Config.TITLE_SELECTOR)
        for i, t in enumerate(titles):
            if title.lower() in t.text.lower(): widgets[i].click(); return

    def _click_video_by_index(self, idx):
        self.driver.find_elements(By.CSS_SELECTOR, Config.VIDEO_WIDGET_SELECTOR)[idx].click()

    def cleanup(self): self.browser.stop()


# ================================================================
# CLI - Command Line Interface
# ================================================================
def main():
    parser = argparse.ArgumentParser(description="HACSM Training Video Capture & Customization Tool v2.0")
    sub = parser.add_subparsers(dest="command")

    cap = sub.add_parser("capture", help="Capture video screenshots")
    cap.add_argument("--video-title", type=str); cap.add_argument("--all", action="store_true")
    cap.add_argument("--interval", type=int, default=5); cap.add_argument("--browser", type=str, default="chrome")
    cap.add_argument("--browser-path", type=str); cap.add_argument("--headless", action="store_true")
    cap.add_argument("--no-zoom", action="store_true"); cap.add_argument("--output", type=str, default="training_video_captures")
    cap.add_argument("--url", type=str, default=Config.BASE_URL)

    sub.add_parser("list", help="List videos").add_argument("--browser", type=str, default="chrome")

    rev = sub.add_parser("review", help="Interactive review"); rev.add_argument("--project", required=True)
    rev.add_argument("--output", type=str, default="training_video_captures")

    cust = sub.add_parser("customize", help="Programmatic customization"); cust.add_argument("--project", required=True)
    cust.add_argument("--output", default="training_video_captures"); cust.add_argument("--insert-after", type=int)
    cust.add_argument("--description", type=str); cust.add_argument("--modify-step", type=int)
    cust.add_argument("--hacsm-desc", type=str); cust.add_argument("--diverge", type=str)
    cust.add_argument("--notes", type=str); cust.add_argument("--remove-step", type=int)

    pub = sub.add_parser("publish", help="Generate final training docs"); pub.add_argument("--project", required=True)
    pub.add_argument("--output", default="training_video_captures")
    pub.add_argument("--no-html", action="store_true"); pub.add_argument("--no-markdown", action="store_true")

    sub.add_parser("browsers", help="List supported browsers")
    args = parser.parse_args()
    if not args.command: parser.print_help(); return

    if args.command == "browsers": BrowserManager.list_supported_browsers(); return
    if args.command == "review":
        p = ProjectManager(Path(args.output) / args.project); p.load()
        InteractiveReviewer(p).start_review(); return
    if args.command == "customize":
        p = ProjectManager(Path(args.output) / args.project); p.load()
        if args.insert_after and args.description: p.insert_custom_step(args.insert_after, args.description, notes=args.notes or "")
        elif args.modify_step: p.modify_step(args.modify_step, args.hacsm_desc, args.diverge, args.notes)
        elif args.remove_step: p.remove_step(args.remove_step)
        return
    if args.command == "publish":
        Config.GENERATE_HTML = not getattr(args, 'no_html', False)
        Config.GENERATE_MARKDOWN = not getattr(args, 'no_markdown', False)
        p = ProjectManager(Path(args.output) / args.project); p.load()
        TrainingGuidePublisher(p).publish_all(); return

    Config.SCREENSHOT_INTERVAL_SECONDS = getattr(args, 'interval', 5)
    Config.OUTPUT_DIR = getattr(args, 'output', 'training_video_captures')
    Config.BASE_URL = getattr(args, 'url', Config.BASE_URL)
    Config.ZOOM_REGIONS_ENABLED = not getattr(args, 'no_zoom', False)
    orch = VideoCaptureOrchestrator(getattr(args, 'browser', 'chrome'), getattr(args, 'headless', False), getattr(args, 'browser_path', None))
    try:
        orch.setup()
        if args.command == "list": orch.list_all_videos()
        elif args.command == "capture":
            if args.all: orch.capture_all_videos()
            elif args.video_title: orch.capture_single_video(video_title=args.video_title)
    except KeyboardInterrupt: print("\nInterrupted.")
    finally: orch.cleanup()

if __name__ == "__main__":
    main()


# ================================================================
# TRAINING GUIDE PUBLISHER - Generates HACSM-branded output
# ================================================================
class TrainingGuidePublisher:
    def __init__(self, project): self.project = project

    def publish_all(self):
        steps = self.project.get_active_steps()
        title = self.project.metadata.get("video_title", "Training Guide")
        if Config.GENERATE_MARKDOWN: self.publish_markdown(steps, title)
        if Config.GENERATE_HTML: self.publish_html(steps, title)
        self.publish_json(steps, title)
        self.project.metadata["phase"] = "published"
        self.project.metadata["version"] = self.project.metadata.get("version", 0) + 1
        self.project.save()

    def publish_markdown(self, steps, title):
        org = Config.HACSM_BRANDING; md = []
        md.append(f"# {org['org_short']} Training Guide: {title}")
        md.append(f"**{org['org_name']}** | Version {self.project.metadata.get('version',1)} | {len(steps)} Steps\n---\n")
        md.append("## Table of Contents\n")
        for s in steps:
            desc = s.hacsm_description or s.description
            badge = " [HACSM Custom]" if s.status == StepData.STATUS_CUSTOM else (" [Modified]" if s.status == StepData.STATUS_DIVERGE else "")
            md.append(f"- Step {s.step_number}: {desc[:60]}{badge}")
        md.append("\n---\n")
        for s in steps:
            desc = s.hacsm_description or s.description
            md.append(f"### Step {s.step_number}: {desc}")
            if s.timestamp_seconds > 0: md.append(f"*Video ref: {s.timestamp_formatted}*\n")
            if s.status == StepData.STATUS_CUSTOM: md.append("> **HACSM-SPECIFIC STEP** - Not in Yardi training\n")
            elif s.status == StepData.STATUS_DIVERGE: md.append(f"> **PROCESS DIFFERENCE:** {s.divergence_note}\n")
            if s.screenshot_path: md.append(f"![Step {s.step_number}](../screenshots/{os.path.basename(s.custom_screenshot_path or s.screenshot_path)})\n")
            for z in s.zoom_paths: md.append(f"![Detail](../screenshots/{os.path.basename(z)})\n")
            if s.hacsm_notes: md.append(f"> **Note:** {s.hacsm_notes}\n")
            md.append("---\n")
        with open(self.project.output_dir / "training_guide.md", 'w') as f: f.write('\n'.join(md))

    def publish_html(self, steps, title):
        org = Config.HACSM_BRANDING
        css = f"""body{{font-family:'Segoe UI',Arial;max-width:1200px;margin:0 auto;padding:20px;background:#f8fafc}}
.header{{background:{org['primary_color']};color:white;padding:30px;border-radius:8px;margin-bottom:30px}}
.step{{background:white;border-radius:8px;padding:24px;margin:16px 0;box-shadow:0 1px 3px rgba(0,0,0,.12)}}
.step img{{max-width:100%;border:1px solid #e2e8f0;border-radius:4px;margin:12px 0}}
.step-header{{color:{org['primary_color']};border-bottom:2px solid {org['accent_color']};padding-bottom:8px}}
.badge-custom{{background:#48bb78;color:white;padding:2px 10px;border-radius:12px;font-size:.8em}}
.badge-diverge{{background:#ed8936;color:white;padding:2px 10px;border-radius:12px;font-size:.8em}}
.diverge-box{{background:#fffaf0;border-left:4px solid #ed8936;padding:12px;margin:12px 0}}
.custom-box{{background:#f0fff4;border-left:4px solid #48bb78;padding:12px;margin:12px 0}}
.notes-box{{background:#ebf8ff;border-left:4px solid #4299e1;padding:12px;margin:12px 0;font-style:italic}}"""
        html = [f"<!DOCTYPE html><html><head><title>{org['org_short']} - {title}</title><style>{css}</style></head><body>"]
        html.append(f'<div class="header"><h1>{org["org_short"]} Training Guide</h1><h2>{title}</h2></div>')
        for s in steps:
            desc = s.hacsm_description or s.description
            html.append(f'<div class="step"><h2 class="step-header">Step {s.step_number}: {desc}</h2>')
            if s.status == StepData.STATUS_CUSTOM: html.append('<div class="custom-box"><strong>HACSM-SPECIFIC STEP</strong></div>')
            elif s.status == StepData.STATUS_DIVERGE and s.divergence_note: html.append(f'<div class="diverge-box"><strong>PROCESS DIFFERENCE:</strong> {s.divergence_note}</div>')
            img = s.custom_screenshot_path or s.screenshot_path
            if img: html.append(f'<img src="../screenshots/{os.path.basename(img)}" alt="Step {s.step_number}">')
            if s.hacsm_notes: html.append(f'<div class="notes-box"><strong>Note:</strong> {s.hacsm_notes}</div>')
            html.append('</div>')
        html.append("</body></html>")
        with open(self.project.output_dir / "training_guide.html", 'w') as f: f.write('\n'.join(html))

    def publish_json(self, steps, title):
        with open(self.project.output_dir / "training_guide.json", 'w') as f:
            json.dump({"title": title, "org": Config.HACSM_BRANDING, "metadata": self.project.metadata, "steps": [s.to_dict() for s in steps]}, f, indent=2)


# ================================================================
# MAIN ORCHESTRATOR
# ================================================================
class VideoCaptureOrchestrator:
    def __init__(self, browser_name="chrome", headless=False, browser_path=None):
        self.browser = BrowserManager(browser_name, headless, browser_path)
        self.driver = None; self.vimeo = None

    def setup(self):
        self.driver = self.browser.start(); self.vimeo = VimeoController(self.driver)
        self.driver.get(Config.BASE_URL)
        print("="*60 + "\n  Log in to HACSM University (Vimeo requires active session)\n  Press Enter when ready...\n" + "="*60)
        input()

    def capture_single_video(self, video_title=None, video_index=0):
        safe_title = re.sub(r'[^a-zA-Z0-9_-]', '_', video_title or f"video_{video_index}")
        project = ProjectManager(Path(Config.OUTPUT_DIR) / safe_title)
        project.create(video_title=video_title or f"Video {video_index}")
        engine = ScreenshotEngine(self.driver, project.screenshots_dir)
        scanner = VideoLibraryScanner(self.driver); scanner.open_library()
        if video_title: self._click_video_by_title(video_title)
        else: self._click_video_by_index(video_index)
        time.sleep(3)
        if not self.vimeo.switch_to_player(): return
        duration = self.vimeo.get_duration() or Config.MAX_VIDEO_DURATION_MINUTES * 60
        self._capture_frames(duration, engine, project)
        self.vimeo.switch_to_main()
        project.metadata["phase"] = "captured"; project.save()
        print(f"\n  DONE: {video_title} | {len(project.steps)} steps | Next: run 'review'")

    def _capture_frames(self, duration, engine, project):
        interval = Config.SCREENSHOT_INTERVAL_SECONDS; step_count = 0
        try: self.vimeo.pause()
        except: pass
        for i in range(int(duration / interval) + 1):
            t = i * interval
            if t > duration: break
            self.vimeo.seek_to(t); time.sleep(0.5)
            self.vimeo.switch_to_main()
            fp, img = engine.capture_full(label=f"t{int(t):04d}")
            if engine.has_significant_change(img):
                zooms = []
                if Config.ZOOM_REGIONS_ENABLED:
                    for region, label in engine.detect_ui_regions(img):
                        try: zp, _ = engine.capture_zoom(img, region, label); zooms.append(zp)
                        except: pass
                step_count += 1
                project.add_step(StepData(step_count, t, fp, zooms,
                    f"Screen at {int(t//60):02d}:{int(t%60):02d} - [Edit for HACSM]"))
            else: os.remove(fp); engine.step_counter -= 1
            self.vimeo.switch_to_player()

    def capture_all_videos(self):
        scanner = VideoLibraryScanner(self.driver); scanner.open_library()
        for v in scanner.get_all_videos():
            if v['has_video']:
                try: self.capture_single_video(video_title=v['title'])
                except Exception as e: print(f"  [ERROR] {e}")

    def list_all_videos(self):
        scanner = VideoLibraryScanner(self.driver); scanner.open_library()
        for v in scanner.get_all_videos():
            print(f"  [{'VIDEO' if v['has_video'] else 'PDF'}] {v['title']}")

    def _click_video_by_title(self, title):
        widgets = self.driver.find_elements(By.CSS_SELECTOR, Config.VIDEO_WIDGET_SELECTOR)
        titles = self.driver.find_elements(By.CSS_SELECTOR, Config.TITLE_SELECTOR)
        for i, t in enumerate(titles):
            if title.lower() in t.text.lower(): widgets[i].click(); return

    def _click_video_by_index(self, idx):
        self.driver.find_elements(By.CSS_SELECTOR, Config.VIDEO_WIDGET_SELECTOR)[idx].click()

    def cleanup(self): self.browser.stop()


# ================================================================
# CLI - Command Line Interface
# ================================================================
def main():
    parser = argparse.ArgumentParser(description="HACSM Training Video Capture & Customization Tool v2.0")
    sub = parser.add_subparsers(dest="command")

    cap = sub.add_parser("capture", help="Capture video screenshots")
    cap.add_argument("--video-title", type=str); cap.add_argument("--all", action="store_true")
    cap.add_argument("--interval", type=int, default=5); cap.add_argument("--browser", type=str, default="chrome")
    cap.add_argument("--browser-path", type=str); cap.add_argument("--headless", action="store_true")
    cap.add_argument("--no-zoom", action="store_true"); cap.add_argument("--output", type=str, default="training_video_captures")
    cap.add_argument("--url", type=str, default=Config.BASE_URL)

    sub.add_parser("list", help="List videos").add_argument("--browser", type=str, default="chrome")

    rev = sub.add_parser("review", help="Interactive review"); rev.add_argument("--project", required=True)
    rev.add_argument("--output", type=str, default="training_video_captures")

    cust = sub.add_parser("customize", help="Programmatic customization"); cust.add_argument("--project", required=True)
    cust.add_argument("--output", default="training_video_captures"); cust.add_argument("--insert-after", type=int)
    cust.add_argument("--description", type=str); cust.add_argument("--modify-step", type=int)
    cust.add_argument("--hacsm-desc", type=str); cust.add_argument("--diverge", type=str)
    cust.add_argument("--notes", type=str); cust.add_argument("--remove-step", type=int)

    pub = sub.add_parser("publish", help="Generate final training docs"); pub.add_argument("--project", required=True)
    pub.add_argument("--output", default="training_video_captures")
    pub.add_argument("--no-html", action="store_true"); pub.add_argument("--no-markdown", action="store_true")

    sub.add_parser("browsers", help="List supported browsers")
    args = parser.parse_args()
    if not args.command: parser.print_help(); return

    if args.command == "browsers": BrowserManager.list_supported_browsers(); return
    if args.command == "review":
        p = ProjectManager(Path(args.output) / args.project); p.load()
        InteractiveReviewer(p).start_review(); return
    if args.command == "customize":
        p = ProjectManager(Path(args.output) / args.project); p.load()
        if args.insert_after and args.description: p.insert_custom_step(args.insert_after, args.description, notes=args.notes or "")
        elif args.modify_step: p.modify_step(args.modify_step, args.hacsm_desc, args.diverge, args.notes)
        elif args.remove_step: p.remove_step(args.remove_step)
        return
    if args.command == "publish":
        Config.GENERATE_HTML = not getattr(args, 'no_html', False)
        Config.GENERATE_MARKDOWN = not getattr(args, 'no_markdown', False)
        p = ProjectManager(Path(args.output) / args.project); p.load()
        TrainingGuidePublisher(p).publish_all(); return

    Config.SCREENSHOT_INTERVAL_SECONDS = getattr(args, 'interval', 5)
    Config.OUTPUT_DIR = getattr(args, 'output', 'training_video_captures')
    Config.BASE_URL = getattr(args, 'url', Config.BASE_URL)
    Config.ZOOM_REGIONS_ENABLED = not getattr(args, 'no_zoom', False)
    orch = VideoCaptureOrchestrator(getattr(args, 'browser', 'chrome'), getattr(args, 'headless', False), getattr(args, 'browser_path', None))
    try:
        orch.setup()
        if args.command == "list": orch.list_all_videos()
        elif args.command == "capture":
            if args.all: orch.capture_all_videos()
            elif args.video_title: orch.capture_single_video(video_title=args.video_title)
    except KeyboardInterrupt: print("\nInterrupted.")
    finally: orch.cleanup()

if __name__ == "__main__":
    main()


# ================================================================
# TRAINING GUIDE PUBLISHER - Generates HACSM-branded output
# ================================================================
class TrainingGuidePublisher:
    def __init__(self, project): self.project = project

    def publish_all(self):
        steps = self.project.get_active_steps()
        title = self.project.metadata.get("video_title", "Training Guide")
        if Config.GENERATE_MARKDOWN: self.publish_markdown(steps, title)
        if Config.GENERATE_HTML: self.publish_html(steps, title)
        self.publish_json(steps, title)
        self.project.metadata["phase"] = "published"
        self.project.metadata["version"] = self.project.metadata.get("version", 0) + 1
        self.project.save()

    def publish_markdown(self, steps, title):
        org = Config.HACSM_BRANDING; md = []
        md.append(f"# {org['org_short']} Training Guide: {title}")
        md.append(f"**{org['org_name']}** | Version {self.project.metadata.get('version',1)} | {len(steps)} Steps\n---\n")
        md.append("## Table of Contents\n")
        for s in steps:
            desc = s.hacsm_description or s.description
            badge = " [HACSM Custom]" if s.status == StepData.STATUS_CUSTOM else (" [Modified]" if s.status == StepData.STATUS_DIVERGE else "")
            md.append(f"- Step {s.step_number}: {desc[:60]}{badge}")
        md.append("\n---\n")
        for s in steps:
            desc = s.hacsm_description or s.description
            md.append(f"### Step {s.step_number}: {desc}")
            if s.timestamp_seconds > 0: md.append(f"*Video ref: {s.timestamp_formatted}*\n")
            if s.status == StepData.STATUS_CUSTOM: md.append("> **HACSM-SPECIFIC STEP** - Not in Yardi training\n")
            elif s.status == StepData.STATUS_DIVERGE: md.append(f"> **PROCESS DIFFERENCE:** {s.divergence_note}\n")
            if s.screenshot_path: md.append(f"![Step {s.step_number}](../screenshots/{os.path.basename(s.custom_screenshot_path or s.screenshot_path)})\n")
            for z in s.zoom_paths: md.append(f"![Detail](../screenshots/{os.path.basename(z)})\n")
            if s.hacsm_notes: md.append(f"> **Note:** {s.hacsm_notes}\n")
            md.append("---\n")
        with open(self.project.output_dir / "training_guide.md", 'w') as f: f.write('\n'.join(md))

    def publish_html(self, steps, title):
        org = Config.HACSM_BRANDING
        css = f"""body{{font-family:'Segoe UI',Arial;max-width:1200px;margin:0 auto;padding:20px;background:#f8fafc}}
.header{{background:{org['primary_color']};color:white;padding:30px;border-radius:8px;margin-bottom:30px}}
.step{{background:white;border-radius:8px;padding:24px;margin:16px 0;box-shadow:0 1px 3px rgba(0,0,0,.12)}}
.step img{{max-width:100%;border:1px solid #e2e8f0;border-radius:4px;margin:12px 0}}
.step-header{{color:{org['primary_color']};border-bottom:2px solid {org['accent_color']};padding-bottom:8px}}
.badge-custom{{background:#48bb78;color:white;padding:2px 10px;border-radius:12px;font-size:.8em}}
.badge-diverge{{background:#ed8936;color:white;padding:2px 10px;border-radius:12px;font-size:.8em}}
.diverge-box{{background:#fffaf0;border-left:4px solid #ed8936;padding:12px;margin:12px 0}}
.custom-box{{background:#f0fff4;border-left:4px solid #48bb78;padding:12px;margin:12px 0}}
.notes-box{{background:#ebf8ff;border-left:4px solid #4299e1;padding:12px;margin:12px 0;font-style:italic}}"""
        html = [f"<!DOCTYPE html><html><head><title>{org['org_short']} - {title}</title><style>{css}</style></head><body>"]
        html.append(f'<div class="header"><h1>{org["org_short"]} Training Guide</h1><h2>{title}</h2></div>')
        for s in steps:
            desc = s.hacsm_description or s.description
            html.append(f'<div class="step"><h2 class="step-header">Step {s.step_number}: {desc}</h2>')
            if s.status == StepData.STATUS_CUSTOM: html.append('<div class="custom-box"><strong>HACSM-SPECIFIC STEP</strong></div>')
            elif s.status == StepData.STATUS_DIVERGE and s.divergence_note: html.append(f'<div class="diverge-box"><strong>PROCESS DIFFERENCE:</strong> {s.divergence_note}</div>')
            img = s.custom_screenshot_path or s.screenshot_path
            if img: html.append(f'<img src="../screenshots/{os.path.basename(img)}" alt="Step {s.step_number}">')
            if s.hacsm_notes: html.append(f'<div class="notes-box"><strong>Note:</strong> {s.hacsm_notes}</div>')
            html.append('</div>')
        html.append("</body></html>")
        with open(self.project.output_dir / "training_guide.html", 'w') as f: f.write('\n'.join(html))

    def publish_json(self, steps, title):
        with open(self.project.output_dir / "training_guide.json", 'w') as f:
            json.dump({"title": title, "org": Config.HACSM_BRANDING, "metadata": self.project.metadata, "steps": [s.to_dict() for s in steps]}, f, indent=2)


# ================================================================
# MAIN ORCHESTRATOR
# ================================================================
class VideoCaptureOrchestrator:
    def __init__(self, browser_name="chrome", headless=False, browser_path=None):
        self.browser = BrowserManager(browser_name, headless, browser_path)
        self.driver = None; self.vimeo = None

    def setup(self):
        self.driver = self.browser.start(); self.vimeo = VimeoController(self.driver)
        self.driver.get(Config.BASE_URL)
        print("="*60 + "\n  Log in to HACSM University (Vimeo requires active session)\n  Press Enter when ready...\n" + "="*60)
        input()

    def capture_single_video(self, video_title=None, video_index=0):
        safe_title = re.sub(r'[^a-zA-Z0-9_-]', '_', video_title or f"video_{video_index}")
        project = ProjectManager(Path(Config.OUTPUT_DIR) / safe_title)
        project.create(video_title=video_title or f"Video {video_index}")
        engine = ScreenshotEngine(self.driver, project.screenshots_dir)
        scanner = VideoLibraryScanner(self.driver); scanner.open_library()
        if video_title: self._click_video_by_title(video_title)
        else: self._click_video_by_index(video_index)
        time.sleep(3)
        if not self.vimeo.switch_to_player(): return
        duration = self.vimeo.get_duration() or Config.MAX_VIDEO_DURATION_MINUTES * 60
        self._capture_frames(duration, engine, project)
        self.vimeo.switch_to_main()
        project.metadata["phase"] = "captured"; project.save()
        print(f"\n  DONE: {video_title} | {len(project.steps)} steps | Next: run 'review'")

    def _capture_frames(self, duration, engine, project):
        interval = Config.SCREENSHOT_INTERVAL_SECONDS; step_count = 0
        try: self.vimeo.pause()
        except: pass
        for i in range(int(duration / interval) + 1):
            t = i * interval
            if t > duration: break
            self.vimeo.seek_to(t); time.sleep(0.5)
            self.vimeo.switch_to_main()
            fp, img = engine.capture_full(label=f"t{int(t):04d}")
            if engine.has_significant_change(img):
                zooms = []
                if Config.ZOOM_REGIONS_ENABLED:
                    for region, label in engine.detect_ui_regions(img):
                        try: zp, _ = engine.capture_zoom(img, region, label); zooms.append(zp)
                        except: pass
                step_count += 1
                project.add_step(StepData(step_count, t, fp, zooms,
                    f"Screen at {int(t//60):02d}:{int(t%60):02d} - [Edit for HACSM]"))
            else: os.remove(fp); engine.step_counter -= 1
            self.vimeo.switch_to_player()

    def capture_all_videos(self):
        scanner = VideoLibraryScanner(self.driver); scanner.open_library()
        for v in scanner.get_all_videos():
            if v['has_video']:
                try: self.capture_single_video(video_title=v['title'])
                except Exception as e: print(f"  [ERROR] {e}")

    def list_all_videos(self):
        scanner = VideoLibraryScanner(self.driver); scanner.open_library()
        for v in scanner.get_all_videos():
            print(f"  [{'VIDEO' if v['has_video'] else 'PDF'}] {v['title']}")

    def _click_video_by_title(self, title):
        widgets = self.driver.find_elements(By.CSS_SELECTOR, Config.VIDEO_WIDGET_SELECTOR)
        titles = self.driver.find_elements(By.CSS_SELECTOR, Config.TITLE_SELECTOR)
        for i, t in enumerate(titles):
            if title.lower() in t.text.lower(): widgets[i].click(); return

    def _click_video_by_index(self, idx):
        self.driver.find_elements(By.CSS_SELECTOR, Config.VIDEO_WIDGET_SELECTOR)[idx].click()

    def cleanup(self): self.browser.stop()


# ================================================================
# CLI - Command Line Interface
# ================================================================
def main():
    parser = argparse.ArgumentParser(description="HACSM Training Video Capture & Customization Tool v2.0")
    sub = parser.add_subparsers(dest="command")

    cap = sub.add_parser("capture", help="Capture video screenshots")
    cap.add_argument("--video-title", type=str); cap.add_argument("--all", action="store_true")
    cap.add_argument("--interval", type=int, default=5); cap.add_argument("--browser", type=str, default="chrome")
    cap.add_argument("--browser-path", type=str); cap.add_argument("--headless", action="store_true")
    cap.add_argument("--no-zoom", action="store_true"); cap.add_argument("--output", type=str, default="training_video_captures")
    cap.add_argument("--url", type=str, default=Config.BASE_URL)

    sub.add_parser("list", help="List videos").add_argument("--browser", type=str, default="chrome")

    rev = sub.add_parser("review", help="Interactive review"); rev.add_argument("--project", required=True)
    rev.add_argument("--output", type=str, default="training_video_captures")

    cust = sub.add_parser("customize", help="Programmatic customization"); cust.add_argument("--project", required=True)
    cust.add_argument("--output", default="training_video_captures"); cust.add_argument("--insert-after", type=int)
    cust.add_argument("--description", type=str); cust.add_argument("--modify-step", type=int)
    cust.add_argument("--hacsm-desc", type=str); cust.add_argument("--diverge", type=str)
    cust.add_argument("--notes", type=str); cust.add_argument("--remove-step", type=int)

    pub = sub.add_parser("publish", help="Generate final training docs"); pub.add_argument("--project", required=True)
    pub.add_argument("--output", default="training_video_captures")
    pub.add_argument("--no-html", action="store_true"); pub.add_argument("--no-markdown", action="store_true")

    sub.add_parser("browsers", help="List supported browsers")
    args = parser.parse_args()
    if not args.command: parser.print_help(); return

    if args.command == "browsers": BrowserManager.list_supported_browsers(); return
    if args.command == "review":
        p = ProjectManager(Path(args.output) / args.project); p.load()
        InteractiveReviewer(p).start_review(); return
    if args.command == "customize":
        p = ProjectManager(Path(args.output) / args.project); p.load()
        if args.insert_after and args.description: p.insert_custom_step(args.insert_after, args.description, notes=args.notes or "")
        elif args.modify_step: p.modify_step(args.modify_step, args.hacsm_desc, args.diverge, args.notes)
        elif args.remove_step: p.remove_step(args.remove_step)
        return
    if args.command == "publish":
        Config.GENERATE_HTML = not getattr(args, 'no_html', False)
        Config.GENERATE_MARKDOWN = not getattr(args, 'no_markdown', False)
        p = ProjectManager(Path(args.output) / args.project); p.load()
        TrainingGuidePublisher(p).publish_all(); return

    Config.SCREENSHOT_INTERVAL_SECONDS = getattr(args, 'interval', 5)
    Config.OUTPUT_DIR = getattr(args, 'output', 'training_video_captures')
    Config.BASE_URL = getattr(args, 'url', Config.BASE_URL)
    Config.ZOOM_REGIONS_ENABLED = not getattr(args, 'no_zoom', False)
    orch = VideoCaptureOrchestrator(getattr(args, 'browser', 'chrome'), getattr(args, 'headless', False), getattr(args, 'browser_path', None))
    try:
        orch.setup()
        if args.command == "list": orch.list_all_videos()
        elif args.command == "capture":
            if args.all: orch.capture_all_videos()
            elif args.video_title: orch.capture_single_video(video_title=args.video_title)
    except KeyboardInterrupt: print("\nInterrupted.")
    finally: orch.cleanup()

if __name__ == "__main__":
    main()
