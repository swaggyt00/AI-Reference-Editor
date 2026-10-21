"""Browser acceptance check against a running local server; generated media only."""
import argparse
from pathlib import Path
import shutil
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from test_web import make_video
from playwright.sync_api import sync_playwright, expect

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--url', default='http://127.0.0.1:8000')
parser.add_argument('--browser', default=shutil.which('chromium'))
args = parser.parse_args()
out = ROOT / 'output/browser-check'
out.mkdir(parents=True, exist_ok=True)
make_video(out / 'референс.mp4', 'orange', audio=True)
make_video(out / 'кадр первый.mp4', 'purple')
make_video(out / 'кадр второй.mp4', 'green')
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=args.browser, headless=True, args=['--no-sandbox'])
    page = browser.new_page(viewport={'width': 1440, 'height': 1080}, device_scale_factor=1)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(args.url)
    expect(page.locator('#connection')).to_have_text('Движок подключён')
    page.screenshot(path=str(out / 'desktop-empty.png'), full_page=True)
    page.locator('#run').click()
    expect(page.locator('#error')).to_contain_text('Выберите референс')
    page.locator('#reference').set_input_files(out / 'референс.mp4')
    page.locator('#sources').set_input_files([out / 'кадр первый.mp4', out / 'кадр второй.mp4'])
    expect(page.locator('#source-list li')).to_have_count(2)
    page.get_by_role('button', name='Поднять кадр второй.mp4').click()
    expect(page.locator('#source-list li').first).to_contain_text('кадр второй.mp4')
    page.locator('#brief').fill('звук: референс')
    page.locator('#run').click()
    expect(page.locator('#stage')).to_have_text('Готово', timeout=30000)
    expect(page.locator('#preview')).to_be_visible()
    expect(page.locator('#versions .version')).to_have_count(1)
    page.wait_for_function('() => document.querySelector("#preview").readyState >= 2')
    assert page.locator('#preview').evaluate('(v) => v.videoWidth') == 160
    page.locator('#preview').evaluate('(v) => { v.muted = true; return v.play(); }')
    page.wait_for_function('() => document.querySelector("#preview").currentTime > 0')
    page.locator('#preview').evaluate('(v) => v.pause()')
    with page.expect_download() as info:
        page.locator('#download').click()
    info.value.save_as(out / 'browser-download-v1.mp4')
    first_url = page.locator('#preview').get_attribute('src')
    page.reload()
    expect(page.locator('#stage')).to_have_text('Готово')
    expect(page.locator('#source-list li')).to_have_count(2)
    expect(page.locator('#brief')).to_have_value('звук: референс')
    page.locator('#brief').fill('звук: нет\nдлительность: 1')
    page.locator('#run').click()
    expect(page.locator('#versions .version')).to_have_count(2)
    expect(page.locator('#stage')).to_have_text('Готово', timeout=30000)
    expect(page.locator('#result-meta')).to_contain_text('Без звука')
    assert page.locator('#preview').get_attribute('src') != first_url
    page.get_by_role('button', name='Смотреть версию 1').click()
    expect(page.locator('#preview')).to_have_attribute('src', first_url)
    page.get_by_role('button', name='Убрать из монтажа кадр второй.mp4').click()
    page.get_by_role('button', name='Убрать из монтажа кадр первый.mp4').click()
    page.reload()
    expect(page.locator('#source-list li')).to_have_count(0)
    page.locator('#restore-sources').click()
    expect(page.locator('#source-list li')).to_have_count(2)
    page.screenshot(path=str(out / 'desktop-complete.png'), full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    page.screenshot(path=str(out / 'mobile-complete.png'), full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('#new-project').click()
    expect(page.locator('#source-list li')).to_have_count(0)
    expect(page.locator('#empty-preview')).to_be_visible()
    dropped = [False]
    def drop_first_reference_response(route):
        if 'role=reference' in route.request.url and not dropped[0]:
            response = route.fetch(post_data=(out / 'референс.mp4').read_bytes())
            assert response.status == 201, (response.status, response.text())
            dropped[0] = True
            route.abort('failed')
        else:
            route.continue_()
    page.route('**/media?**', drop_first_reference_response)
    page.locator('#reference').set_input_files(out / 'референс.mp4')
    page.locator('#sources').set_input_files(out / 'кадр первый.mp4')
    page.locator('#run').click()
    expect(page.locator('#error')).to_contain_text('Соединение прервалось', timeout=30000)
    page.locator('#run').click()
    expect(page.locator('#stage')).to_have_text('Готово', timeout=30000)
    expect(page.locator('#source-list li')).to_have_count(1)
    assert not errors, errors
    print('PASS: browser upload, ordering, render, playback, download, reload, revision, history, new project, 390px layout, empty selection restore, lost upload response retry; no JS errors')
    browser.close()
