"""Live browser acceptance, no mocked provider responses. Requires playwright."""
import argparse
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright


async def verify(args):
    results = []
    args.output.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        options = dict(args=['--no-sandbox'])
        if args.chromium:
            options['executable_path'] = args.chromium
        browser = await playwright.chromium.launch(**options)
        context = await browser.new_context(viewport={'width': 1500, 'height': 1100})
        home = await context.new_page()
        await home.goto(args.url)
        await home.get_by_text('openbb_spy_history.py', exact=True).first.wait_for(timeout=60000)
        # Expand the real file-tree folder to expose the recovered collection.
        await home.get_by_text('collection', exact=True).first.click()
        await home.get_by_text('stage-simple_csv_rag.py', exact=True).wait_for(timeout=60000)
        await home.screenshot(path=str(args.output / 'studio-list.png'), full_page=True)
        for symbol in ('spy', 'qqq', 'aapl'):
            page = await context.new_page()
            await page.goto(args.url + ('&' if '?' in args.url else '?') + 'file=openbb_' + symbol + '_history.py')
            button = page.get_by_role('button', name='Fetch history and write catalog', exact=True)
            await button.wait_for(timeout=60000)
            await button.click()
            proof = page.locator('strong').filter(has_text='10 real bars')
            try:
                await proof.wait_for(timeout=90000)
                chart = page.locator('img[src^="data:image"]').first
                await chart.wait_for(timeout=30000)
                await chart.scroll_into_view_if_needed()
                await page.screenshot(path=str(args.output / (symbol + '-chart.png')))
                results.append(dict(symbol=symbol.upper(), live_form_submit=True, catalog_readback_rows=10, chart_rendered=True, url=args.url.split("?")[0] + "?file=openbb_" + symbol + "_history.py"))
            except Exception:
                (args.output / (symbol + '-failure.txt')).write_text(await page.locator('body').inner_text())
                await page.screenshot(path=str(args.output / (symbol + '-failure.png')), full_page=True)
                raise
            finally:
                (args.output / 'live-results.json').write_text(json.dumps(results, indent=2))
            await page.close()
        await browser.close()
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://100.82.57.72:8202/')
    parser.add_argument('--chromium')
    parser.add_argument('--output', type=Path, default=Path('artifacts/marimo-collection'))
    asyncio.run(verify(parser.parse_args()))
