"""Optional functional UI validation. Requires Playwright and a local Chromium.
Start npm --prefix web run preview -- --port 4173 first.
"""
import os
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:4173/',wait_until='networkidle')
    assert page.locator('nav button').count()==9
    page.get_by_role('button',name='Реестр наблюдений').click()
    count=page.locator('.observation').count()
    page.locator('#query').fill('несуществующийзапрос')
    assert page.get_by_text('По этим фильтрам нет данных',exact=True).count()==1
    page.locator('#query').fill('')
    assert page.locator('.observation').count()==count
    with page.expect_download() as d:page.get_by_role('button',name='Экспорт CSV').click()
    assert d.value.suggested_filename=='observations.csv'
    page.set_viewport_size({'width':390,'height':844})
    page.get_by_role('button',name='Обзор').click()
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    assert not errors
    browser.close()
print('UI smoke passed: navigation, live data, filters, CSV download, mobile layout, no JavaScript errors')
