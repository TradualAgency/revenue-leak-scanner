import asyncio
from playwright.async_api import async_playwright
from app.config import settings

KEY = settings.OPERATOR_API_KEY
BASE = "http://localhost:5174"

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await b.new_page(viewport={"width": 1280, "height": 900})
        await page.add_init_script(f"sessionStorage.setItem('tradual_operator_key', {KEY!r})")
        page.on("console", lambda m: m.type == "error" and print("console error:", m.text[:200]))
        await page.goto(f"{BASE}/scans", wait_until="networkidle")
        await page.get_by_role("button", name="Agents ▾").first.click()
        await page.get_by_text("Funnel-agent").first.wait_for()
        await page.wait_for_timeout(800)
        await page.screenshot(path="/tmp/scans_dropdown.png")
        # start the funnel agent for the first audit
        row = page.locator("li", has_text="Funnel-agent").first
        await row.get_by_role("button", name="Start").click()
        await page.wait_for_timeout(1500)
        await row.get_by_role("link", name="Bevindingen →").click()
        await page.wait_for_url("**/agents/funnel**")
        print("url:", page.url)
        for i in range(70):
            await page.wait_for_timeout(5000)
            text = await page.locator("main").inner_text()
            if "bezig" not in text.lower():
                break
        await page.wait_for_timeout(2000)
        await page.screenshot(path="/tmp/agent_funnel.png", full_page=True)
        print((await page.locator("main").inner_text())[:1500])
        await b.close()

asyncio.run(main())
