# -*- coding: utf-8 -*-
"""
Browser Operations Skill for OROVA MikeBot
Autonomous Lead Research with Headless Playwright

Features:
- BrowsingAgent class for lead research
- Headless Playwright (Docker-safe)
- 30-second safety timeout
- Auto-closes browser on crash
"""

import os
import json
import asyncio
import tempfile
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime
from urllib.parse import quote_plus

# Timeout for browser operations
BROWSE_TIMEOUT = 30  # seconds

# ═══════════════════════════════════════════════════════════════════════════════
# BROWSING AGENT CLASS
# ═══════════════════════════════════════════════════════════════════════════════

class BrowsingAgent:
    """
    Autonomous browsing agent for lead research.
    Uses headless Playwright for safe, controlled browsing.
    """
    
    def __init__(self, headless: bool = True, timeout: int = BROWSE_TIMEOUT):
        self.headless = headless
        self.timeout = timeout
        self.browser = None
        self.context = None
        self.page = None
        self._playwright = None
    
    async def __aenter__(self):
        """Async context manager entry - launches browser"""
        await self.launch()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - ensures browser closes"""
        await self.close()
    
    async def launch(self):
        """Launch headless Playwright browser"""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ImportError("Playwright not installed. Run: pip install playwright && playwright install chromium")
        
        self._playwright = await async_playwright().start()
        
        # Try browserless container first, fall back to local
        ws_url = os.environ.get("PUPPETEER_CONNECT_URL", "")
        
        if ws_url and "browser" in ws_url:
            try:
                self.browser = await self._playwright.chromium.connect_over_cdp(
                    ws_url.replace("ws://", "http://"),
                    timeout=10000
                )
            except Exception:
                pass
        
        if self.browser is None:
            from app.core.browser_utils import get_browser_launch_args
            launch_options = get_browser_launch_args()
            launch_options["headless"] = self.headless
            self.browser = await self._playwright.chromium.launch(**launch_options)
        
        self.context = await self.browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        self.page = await self.context.new_page()
        self.page.set_default_timeout(self.timeout * 1000)
    
    async def close(self):
        """Safely close browser - always call this"""
        try:
            if self.browser:
                await self.browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass  # Ensure no crash on close
        finally:
            self.browser = None
            self.context = None
            self.page = None
            self._playwright = None
    
    async def research_lead_async(self, url: str) -> Dict[str, Any]:
        """
        Research a lead by visiting their website.
        
        Extracts:
        - About Us text
        - Contact details (email, phone)
        - Business niche summary
        
        Args:
            url: The lead's website URL
            
        Returns:
            Dict with extracted information
        """
        result = {
            "success": False,
            "url": url,
            "timestamp": datetime.now().isoformat(),
            "business_info": {}
        }
        
        try:
            if not self.page:
                await self.launch()
            
            # Navigate to the URL
            await self.page.goto(url, wait_until='domcontentloaded', timeout=self.timeout * 1000)
            
            # Extract page title
            title = await self.page.title()
            
            # Extract meta description
            meta_desc = await self.page.evaluate('''() => {
                const meta = document.querySelector('meta[name="description"]');
                return meta ? meta.getAttribute('content') : '';
            }''')
            
            # Extract About Us content
            about_text = await self.page.evaluate('''() => {
                // Try common About Us selectors
                const selectors = [
                    'section.about', '#about', '.about-us', '[id*="about"]', '[class*="about"]',
                    'main', 'article', '.content', '#content'
                ];
                
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText.length > 100) {
                        return el.innerText.slice(0, 2000);
                    }
                }
                
                // Fallback to body text
                return document.body.innerText.slice(0, 2000);
            }''')
            
            # Extract contact information
            contact_info = await self.page.evaluate('''() => {
                const text = document.body.innerText;
                const html = document.body.innerHTML;
                
                // Extract emails
                const emailRegex = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/g;
                const emails = [...new Set((text.match(emailRegex) || []).filter(e => !e.includes('example') && !e.includes('placeholder')))];
                
                // Extract phone numbers
                const phoneRegex = /(\\+?1?[-. ]?\\(?\\d{3}\\)?[-. ]?\\d{3}[-. ]?\\d{4})/g;
                const phones = [...new Set(text.match(phoneRegex) || [])];
                
                // Extract address hints
                const addressHints = [];
                const stateRegex = /(California|CA|Florida|FL|Texas|TX|New York|NY)/gi;
                const stateMatches = text.match(stateRegex);
                if (stateMatches) addressHints.push(...new Set(stateMatches));
                
                // Extract social links
                const socialLinks = {};
                const socials = ['facebook', 'instagram', 'twitter', 'linkedin', 'youtube', 'tiktok'];
                const links = document.querySelectorAll('a[href]');
                links.forEach(a => {
                    socials.forEach(s => {
                        if (a.href.includes(s + '.com')) {
                            socialLinks[s] = a.href;
                        }
                    });
                });
                
                return {
                    emails: emails.slice(0, 3),
                    phones: phones.slice(0, 3),
                    location_hints: addressHints.slice(0, 3),
                    social_media: socialLinks
                };
            }''')
            
            # Determine business niche
            niche = self._classify_niche(title, meta_desc, about_text)
            
            result["success"] = True
            result["business_info"] = {
                "name": title,
                "description": meta_desc,
                "about_text": about_text[:1000],
                "niche": niche,
                "contact": contact_info
            }
            
        except asyncio.TimeoutError:
            result["error"] = f"Timeout after {self.timeout} seconds"
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    def _classify_niche(self, title: str, description: str, about_text: str) -> str:
        """Classify the business niche based on page content"""
        combined = f"{title} {description} {about_text}".lower()
        
        niche_keywords = {
            "Luxury Detailing": ["detailing", "ceramic coating", "paint protection", "ppf", "polish"],
            "Car Dealership": ["dealership", "dealer", "new cars", "used cars", "inventory", "financing"],
            "Auto Rental": ["rental", "rent a car", "car hire", "fleet", "reservation"],
            "Body Shop/Collision": ["collision", "body shop", "auto body", "repair", "accident"],
            "Performance Shop": ["performance", "tuning", "dyno", "exhaust", "turbo", "horsepower"],
            "Wrap/Graphics": ["wrap", "vinyl", "graphics", "color change", "vehicle wrap"],
            "Exotic/Luxury": ["exotic", "luxury", "ferrari", "lamborghini", "porsche", "maserati"],
            "General Automotive": ["automotive", "auto", "car", "vehicle"]
        }
        
        for niche, keywords in niche_keywords.items():
            if any(kw in combined for kw in keywords):
                return niche
        
        return "Automotive Business"


# ═══════════════════════════════════════════════════════════════════════════════
# STANDALONE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def research_lead(url: str) -> Dict[str, Any]:
    """
    Research a lead's website for business information.
    
    Synchronous wrapper with automatic browser cleanup.
    
    Args:
        url: The lead's website URL
        
    Returns:
        Dict with About Us text, Contact details, and Business niche
    """
    async def _research():
        agent = BrowsingAgent(headless=True)
        try:
            await agent.launch()
            return await agent.research_lead_async(url)
        except Exception as e:
            return {"success": False, "url": url, "error": str(e)}
        finally:
            await agent.close()
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    if loop.is_running():
        try:
            import nest_asyncio
            nest_asyncio.apply()
            return loop.run_until_complete(_research())
        except ImportError:
            return {"success": False, "url": url, "error": "Cannot run in async context"}
    else:
        return loop.run_until_complete(_research())


async def browse_and_extract_async(url: str, goal: str = "extract page content") -> Dict[str, Any]:
    """
    Browse a URL and extract structured information.
    
    Args:
        url: The URL to visit
        goal: What to extract (e.g., "find contact info", "get pricing")
    
    Returns:
        JSON with page title, main content, links, and goal-specific data
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {
            "success": False,
            "error": "Playwright not installed. Run: pip install playwright && playwright install chromium"
        }
    
    result = {
        "success": False,
        "url": url,
        "goal": goal,
        "timestamp": datetime.now().isoformat(),
        "data": {}
    }
    
    browser = None
    playwright = None
    
    try:
        playwright = await async_playwright().start()
        
        # Try browserless container first
        ws_url = os.environ.get("PUPPETEER_CONNECT_URL", "")
        
        if ws_url and "browser" in ws_url:
            try:
                browser = await playwright.chromium.connect_over_cdp(
                    ws_url.replace("ws://", "http://").replace(":3000", ":3000"),
                    timeout=10000
                )
            except Exception:
                pass
        
        if browser is None:
            browser = await playwright.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-dev-shm-usage']
            )
        
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        
        page = await context.new_page()
        page.set_default_timeout(BROWSE_TIMEOUT * 1000)
        
        # Navigate with timeout
        await page.goto(url, wait_until='domcontentloaded', timeout=BROWSE_TIMEOUT * 1000)
        
        # Extract page data
        title = await page.title()
        
        # Get main text content (cleaned)
        content = await page.evaluate('''() => {
            const scripts = document.querySelectorAll('script, style, noscript');
            scripts.forEach(s => s.remove());
            
            const main = document.querySelector('main, article, .content, #content, body');
            if (!main) return document.body.innerText.slice(0, 5000);
            return main.innerText.slice(0, 5000);
        }''')
        
        # Get links
        links = await page.evaluate('''() => {
            return Array.from(document.querySelectorAll('a[href]'))
                .slice(0, 20)
                .map(a => ({text: a.innerText.trim().slice(0, 100), href: a.href}))
                .filter(l => l.text && l.href.startsWith('http'));
        }''')
        
        # Get meta description
        meta_desc = await page.evaluate('''() => {
            const meta = document.querySelector('meta[name="description"]');
            return meta ? meta.getAttribute('content') : '';
        }''')
        
        # Goal-specific extraction
        goal_data = {}
        goal_lower = goal.lower()
        
        if 'contact' in goal_lower or 'email' in goal_lower:
            goal_data = await page.evaluate('''() => {
                const text = document.body.innerText;
                const emails = text.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/g) || [];
                const phones = text.match(/(\\+?1?[-.\\s]?\\(?\\d{3}\\)?[-.\\s]?\\d{3}[-.\\s]?\\d{4})/g) || [];
                return {
                    emails: [...new Set(emails)].slice(0, 5),
                    phones: [...new Set(phones)].slice(0, 5)
                };
            }''')
        
        elif 'price' in goal_lower or 'pricing' in goal_lower or 'cost' in goal_lower:
            goal_data = await page.evaluate('''() => {
                const text = document.body.innerText;
                const prices = text.match(/\\$[\\d,]+\\.?\\d*/g) || [];
                return {prices: [...new Set(prices)].slice(0, 10)};
            }''')
        
        elif 'social' in goal_lower:
            goal_data = await page.evaluate('''() => {
                const socials = ['facebook', 'twitter', 'instagram', 'linkedin', 'youtube', 'tiktok'];
                const links = Array.from(document.querySelectorAll('a[href]'));
                const socialLinks = {};
                
                links.forEach(a => {
                    socials.forEach(s => {
                        if (a.href.includes(s + '.com')) {
                            socialLinks[s] = a.href;
                        }
                    });
                });
                
                return socialLinks;
            }''')
        
        result["success"] = True
        result["data"] = {
            "title": title,
            "description": meta_desc,
            "content": content[:3000] if content else "",
            "links": links[:10],
            "goal_specific": goal_data
        }
        
    except asyncio.TimeoutError:
        result["error"] = f"Timeout after {BROWSE_TIMEOUT} seconds"
    except Exception as e:
        result["error"] = str(e)
    finally:
        # Always close browser
        try:
            if browser:
                await browser.close()
            if playwright:
                await playwright.stop()
        except Exception:
            pass
    
    return result


def browse_and_extract(url: str, goal: str = "extract page content") -> Dict[str, Any]:
    """
    Synchronous wrapper for browse_and_extract_async.
    Safe to call from non-async code.
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    if loop.is_running():
        try:
            import nest_asyncio
            nest_asyncio.apply()
            return loop.run_until_complete(browse_and_extract_async(url, goal))
        except ImportError:
            return {
                "success": False,
                "error": "Cannot run in async context. Use browse_and_extract_async directly."
            }
    else:
        return loop.run_until_complete(browse_and_extract_async(url, goal))


# ═══════════════════════════════════════════════════════════════════════════════
# SIMPLE PAGE FETCH (Faster, for basic needs)
# ═══════════════════════════════════════════════════════════════════════════════

def quick_fetch(url: str) -> Dict[str, Any]:
    """
    Quick page fetch without full browser (uses requests + HTML parsing).
    Faster but can't handle JavaScript-rendered pages.
    """
    try:
        import requests
        from html.parser import HTMLParser
        
        class MLStripper(HTMLParser):
            def __init__(self):
                super().__init__()
                self.reset()
                self.strict = False
                self.data = []
            def handle_data(self, d):
                self.data.append(d)
            def get_text(self):
                return ' '.join(self.data)
        
        response = requests.get(url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'
        })
        response.raise_for_status()
        
        html = response.text
        
        # Extract title
        title_start = html.find('<title>')
        title_end = html.find('</title>')
        title = html[title_start+7:title_end] if title_start != -1 else ""
        
        # Strip HTML
        stripper = MLStripper()
        stripper.feed(html)
        text = stripper.get_text()[:3000]
        
        return {
            "success": True,
            "url": url,
            "title": title.strip(),
            "content": text.strip(),
            "method": "quick_fetch"
        }
        
    except Exception as e:
        return {"success": False, "url": url, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# SCREENSHOT CAPTURE
# ═══════════════════════════════════════════════════════════════════════════════

async def capture_screenshot_async(url: str, output_path: str = None) -> Dict[str, Any]:
    """Capture a screenshot of a webpage"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"success": False, "error": "Playwright not installed"}
    
    if output_path is None:
        temp_dir = tempfile.gettempdir()
        output_path = os.path.join(temp_dir, f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
    
    browser = None
    playwright = None
    
    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1280, 'height': 720})
        await page.goto(url, wait_until='networkidle', timeout=BROWSE_TIMEOUT * 1000)
        await page.screenshot(path=output_path, full_page=False)
        
        return {
            "success": True,
            "url": url,
            "screenshot_path": output_path
        }
    except Exception as e:
        return {"success": False, "url": url, "error": str(e)}
    finally:
        try:
            if browser:
                await browser.close()
            if playwright:
                await playwright.stop()
        except Exception:
            pass


def capture_screenshot(url: str, output_path: str = None) -> Dict[str, Any]:
    """Synchronous wrapper for screenshot capture"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(capture_screenshot_async(url, output_path))


# ═══════════════════════════════════════════════════════════════════════════════
# VIDEO CAPTURE (Moltworker Skill)
# ═══════════════════════════════════════════════════════════════════════════════

async def capture_video_async(url: str, duration: int = 10, output_path: str = None) -> Dict[str, Any]:
    """Capture a video of a webpage interaction"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"success": False, "error": "Playwright not installed"}

    temp_dir = tempfile.gettempdir()
    if output_path is None:
        output_path = os.path.join(temp_dir, f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.webm")

    # Ensure directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    temp_video_dir = os.path.join(temp_dir, f"pw_video_{datetime.now().strftime('%f')}")

    browser = None
    playwright = None

    try:
        playwright = await async_playwright().start()

        # Try browserless container first
        ws_url = os.environ.get("PUPPETEER_CONNECT_URL", "")
        if ws_url and "browser" in ws_url:
            try:
                browser = await playwright.chromium.connect_over_cdp(
                    ws_url.replace("ws://", "http://"),
                    timeout=10000
                )
            except:
                pass

        if browser is None:
            browser = await playwright.chromium.launch(headless=True)

        # Create context with video recording enabled
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            record_video_dir=temp_video_dir,
            record_video_size={'width': 1280, 'height': 720}
        )

        page = await context.new_page()
        await page.goto(url, wait_until='networkidle', timeout=BROWSE_TIMEOUT * 1000)

        # Record for duration
        await asyncio.sleep(duration)

        # Close context to save video
        await context.close()

        # Find the video file and move it
        # Playwright names files with random hash, so we find the one file in the dir
        video_files = list(Path(temp_video_dir).glob("*.webm"))
        if video_files:
            video_file = video_files[0]
            video_file.rename(output_path)
            # Cleanup dir
            try:
                os.rmdir(temp_video_dir)
            except:
                pass

            return {
                "success": True,
                "url": url,
                "video_path": output_path
            }
        else:
            return {"success": False, "url": url, "error": "Video file not generated"}

    except Exception as e:
        return {"success": False, "url": url, "error": str(e)}
    finally:
        try:
            if browser:
                await browser.close()
            if playwright:
                await playwright.stop()
        except Exception:
            pass

def capture_video(url: str, duration: int = 10, output_path: str = None) -> Dict[str, Any]:
    """Synchronous wrapper for video capture"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(capture_video_async(url, duration, output_path))




# ═══════════════════════════════════════════════════════════════════════════════
# GOOGLE SEARCH SCRAPER (God Mode Fallback)
# ═══════════════════════════════════════════════════════════════════════════════

async def google_search_scrape_async(query: str, limit: int = 10) -> List[Dict[str, str]]:
    """
    Perform a direct Google Search using Playwright (Scraper).
    UPGRADED: Multiple selector strategies + better stealth.
    """
    results = []
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return []

    browser = None
    playwright = None

    try:
        playwright = await async_playwright().start()

        # Use existing logic for browser launch
        ws_url = os.environ.get("PUPPETEER_CONNECT_URL", "")
        if ws_url and "browser" in ws_url:
            try:
                browser = await playwright.chromium.connect_over_cdp(
                    ws_url.replace("ws://", "http://").replace(":3000", ":3000"),
                    timeout=10000
                )
            except:
                pass

        if browser is None:
            browser = await playwright.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox', 
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-infobars',
                    '--window-size=1920,1080'
                ]
            )

        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            ignore_https_errors=True,
            locale='en-US'
        )
        page = await context.new_page()

        # Stealth: Hide webdriver flag
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = { runtime: {} };
        """)

        # Go to Google
        encoded_query = quote_plus(query)
        await page.goto(
            f"https://www.google.com/search?q={encoded_query}&num={limit*2}&hl=en&gl=us",
            wait_until='domcontentloaded',
            timeout=30000
        )

        # Handle consent popups
        for btn_text in ["Reject all", "Accept all", "I agree"]:
            try:
                await page.click(f'button:has-text("{btn_text}")', timeout=1500)
                await page.wait_for_timeout(500)
            except:
                pass

        # Wait for any results to appear
        for selector in ['.g', '#search', '#rso', 'div[data-hveid]']:
            try:
                await page.wait_for_selector(selector, state='attached', timeout=3000)
                break
            except:
                continue

        # Extract Results - TRY MULTIPLE SELECTOR STRATEGIES
        results = await page.evaluate('''() => {
            const items = [];
            
            // Strategy 1: Classic .g selector
            document.querySelectorAll('.g').forEach(el => {
                const titleEl = el.querySelector('h3');
                const linkEl = el.querySelector('a[href^="http"]');
                if (titleEl && linkEl) {
                    let snippet = '';
                    // Try multiple snippet selectors (Google changes these often)
                    const snipSelectors = [
                        '.VwiC3b', '.IsZvec', '.aCOpRe', '.lEBKkf',
                        '[data-sncf]', '.st', 'span.hgKElc',
                        'div[style="-webkit-line-clamp:2"]',
                        'div[data-snf]'
                    ];
                    for (const sel of snipSelectors) {
                        const snipEl = el.querySelector(sel);
                        if (snipEl && snipEl.innerText.length > 10) {
                            snippet = snipEl.innerText;
                            break;
                        }
                    }
                    if (!snippet) {
                        // Fallback: get any text that's not the title
                        const allText = el.innerText.replace(titleEl.innerText, '').trim();
                        snippet = allText.slice(0, 200);
                    }
                    items.push({
                        title: titleEl.innerText,
                        url: linkEl.href,
                        snippet: snippet.slice(0, 300)
                    });
                }
            });
            
            // Strategy 2: If .g failed, try data-hveid divs
            if (items.length === 0) {
                document.querySelectorAll('div[data-hveid]').forEach(el => {
                    const h3 = el.querySelector('h3');
                    const a = el.querySelector('a[href^="http"]');
                    if (h3 && a && a.href.startsWith('http') && !a.href.includes('google.com')) {
                        items.push({
                            title: h3.innerText,
                            url: a.href,
                            snippet: el.innerText.replace(h3.innerText, '').trim().slice(0, 300)
                        });
                    }
                });
            }
            
            // Strategy 3: Last resort - any h3 with a parent link
            if (items.length === 0) {
                document.querySelectorAll('h3').forEach(h3 => {
                    const parent = h3.closest('a') || h3.parentElement?.querySelector('a');
                    if (parent && parent.href && parent.href.startsWith('http') && !parent.href.includes('google.com')) {
                        items.push({
                            title: h3.innerText,
                            url: parent.href,
                            snippet: ''
                        });
                    }
                });
            }
            
            // Deduplicate by URL
            const seen = new Set();
            return items.filter(item => {
                if (seen.has(item.url)) return false;
                seen.add(item.url);
                return true;
            });
        }''')

    except Exception as e:
        print(f"Google Scraper Error: {e}")
    finally:
        try:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        except: pass

    return results[:limit]


def google_search_scrape(query: str, limit: int = 5):
    """Synchronous wrapper for google_search_scrape_async"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        try:
            import nest_asyncio
            nest_asyncio.apply()
            return loop.run_until_complete(google_search_scrape_async(query, limit))
        except ImportError:
            return [] # Fail gracefully
    else:
        return loop.run_until_complete(google_search_scrape_async(query, limit))


# ═══════════════════════════════════════════════════════════════════════════════
# SKILL REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════════

def register_browser_ops_skills(TOOLS, tool_decorator):
    """Register Browser Operations tools"""
    
    @tool_decorator("browse_page", "Visit a URL and extract structured content with a specific goal")
    def _browse_page(url: str, goal: str = "extract page content"):
        return browse_and_extract(url, goal)
    
    @tool_decorator("quick_page", "Quick page fetch (no JavaScript, faster)")
    def _quick_page(url: str):
        return quick_fetch(url)
    
    @tool_decorator("screenshot", "Take a screenshot of a webpage")
    def _screenshot(url: str):
        return capture_screenshot(url)

    @tool_decorator("capture_video", "Record a video of a webpage")
    def _capture_video(url: str, duration: int = 10):
        return capture_video(url, duration)
    
    @tool_decorator("research_lead", "Research a lead's website for About Us, Contact info, and Business niche")
    def _research_lead(url: str):
        return research_lead(url)
    
    TOOLS["browse_page"] = {"func": _browse_page, "description": "Visit URL and extract content with goal"}
    TOOLS["quick_page"] = {"func": _quick_page, "description": "Quick page fetch"}
    TOOLS["screenshot"] = {"func": _screenshot, "description": "Screenshot a webpage"}
    TOOLS["capture_video"] = {"func": _capture_video, "description": "Record video of webpage"}
    TOOLS["research_lead"] = {"func": _research_lead, "description": "Research lead website"}
    TOOLS["google_scrape"] = {"func": google_search_scrape, "description": "Hard Fallback Google Search Scraper"}

    return TOOLS
