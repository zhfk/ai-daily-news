"""Credential-free RSS collection and conservative template rendering."""
import json
import html
import argparse
import concurrent.futures
from urllib.parse import urlsplit, urlunsplit
from email.utils import parsedate_to_datetime
import feedparser
from bs4 import BeautifulSoup
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import bleach
import markdown

ROOT = Path(__file__).resolve().parents[1]
CSS = """body{max-width:900px;margin:32px auto;padding:0 20px;color:#20242c;
font:16px/1.85 system-ui,sans-serif}p{margin:12px 0}hr{border:0;border-top:1px solid #ddd;
margin:26px 0}.image-group{display:flex;gap:12px;align-items:flex-start;margin:14px 0}
figure{flex:1;min-width:0;margin:0}img{width:100%;height:auto;object-fit:contain}
figcaption{font-size:12px;color:#666;line-height:1.5}a{color:#165ca6}
@media(max-width:560px){.image-group{overflow-x:auto}figure{flex:0 0 80%}}
"""


def render(text):
    raw = markdown.markdown(text, extensions=['tables'])
    safe = bleach.clean(raw, tags=['p', 'strong', 'em', 'a', 'hr', 'br', 'div',
        'figure', 'img', 'figcaption', 'table', 'thead', 'tbody', 'tr', 'th', 'td',
        'ul', 'ol', 'li', 'blockquote'], attributes={'a': ['href'],
        'img': ['src', 'alt'], 'div': ['class']}, protocols=['https'], strip=True)
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8">' + \
        '<meta name="viewport" content="width=device-width,initial-scale=1">' + \
        '<title>AI 与科技每日简报</title><style>' + CSS + '</style><body>' + safe + '</body></html>'


FEEDS = [
    ('OpenAI', 'https://openai.com/news/rss.xml', True),
    ('Google AI', 'https://blog.google/technology/ai/rss/', True),
    ('NVIDIA', 'https://blogs.nvidia.com/feed/', True),
    ('Hugging Face', 'https://huggingface.co/blog/feed.xml', True),
    ('Microsoft Research', 'https://www.microsoft.com/en-us/research/feed/', True),
    ('IT之家', 'https://www.ithome.com/rss/', False),
]
KEYWORDS = re.compile(r'人工智能|大模型|机器人|芯片|算力|智能体|融资|AI\b|LLM|GPT|Claude|Gemini|robot|agent|GPU|model|inference', re.I)
RULES = [
    (r'芯片|GPU|算力|inference|NVIDIA', '算力与部署', '检查公开规格、供货时间、能耗和实际采购成本，使用自己的工作负载评估吞吐与延迟；不要直接沿用厂商性能结论。'),
    (r'robot|机器人|research|研究|论文', '科研与机器人', '先阅读论文和实验设置，区分预印本与同行评审；优先检查代码、数据和复现实验，确认结果是否适用于实际场景。'),
    (r'agent|智能体|语音|voice', 'Agent 与交互', '用小范围任务测试权限控制、错误恢复、延迟与人工接管，明确测试数据和真实业务数据的边界。'),
]


def fetch(url):
    if urlsplit(url).scheme != 'https':
        raise ValueError('只采集 HTTPS 来源')
    req = urllib.request.Request(url, headers={'User-Agent': 'AI-Daily-News/1.0 (RSS reader)'})
    with urllib.request.urlopen(req, timeout=25) as response:
        body = response.read(5_000_001)
        if len(body) > 5_000_000:
            raise ValueError('来源超过大小限制')
        return body, response.geturl()


def date_value(value):
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, TypeError):
        try:
            dt = parsedate_to_datetime(value)
        except (ValueError, TypeError):
            return None
    return dt if dt.tzinfo else None


def plain(value):
    soup = BeautifulSoup(value, 'html.parser')
    for element in soup(['script', 'style']):
        element.decompose()
    return re.sub(r'\s+', ' ', soup.get_text(' ', strip=True)).strip()


def collect(source, now):
    name, url, official = source
    records = []
    try:
        body, _ = fetch(url)
        feed = feedparser.parse(body)
        if not feed.entries and feed.bozo:
            raise ValueError('订阅源不可解析')
        for entry in feed.entries[:100]:
            # Never substitute updated timestamps for publication timestamps.
            published = date_value(entry.get('published', ''))
            title = plain(entry.get('title', ''))
            if not published or not now - timedelta(hours=24) < published <= now:
                continue
            if not KEYWORDS.search(title + ' ' + entry.get('summary', '')):
                continue
            link = entry.get('link', '')
            if urlsplit(link).hostname != urlsplit(url).hostname:
                continue
            try:
                page, final_url = fetch(link)
                soup = BeautifulSoup(page, 'html.parser')
                dates = [tag.get('content', '') for tag in soup.find_all('meta')
                    if tag.get('property') == 'article:published_time' or tag.get('name') in ('datePublished', 'pubdate')]
                for tag in soup.find_all('script', type='application/ld+json'):
                    try:
                        def walk(obj):
                            if isinstance(obj, dict):
                                if 'datePublished' in obj:
                                    dates.append(obj['datePublished'])
                                for value in obj.values(): walk(value)
                            elif isinstance(obj, list):
                                for value in obj: walk(value)
                        walk(json.loads(tag.string or tag.get_text()))
                    except (ValueError, TypeError):
                        pass
                valid = [date_value(d) for d in dates if isinstance(d, str)]
                valid = [d for d in valid if d]
                if not valid or not all(now - timedelta(hours=24) < d <= now for d in valid):
                    continue
                desc = soup.find('meta', attrs={'name': 'description'}) or soup.find('meta', property='og:description')
                excerpt = plain(desc.get('content', '')) if desc else plain(entry.get('summary', ''))
                if not excerpt:
                    continue
                category, advice = '模型与产品', '打开官方文档核对可用区域、许可、价格及上线状态，再用自己的样例做小规模评估；原文中的比较结果不等于独立测试。'
                for pattern, cat, action in RULES:
                    if re.search(pattern, title + ' ' + name, re.I):
                        category, advice = cat, action
                        break
                parts = urlsplit(final_url)
                canonical = urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip('/'), '', ''))
                records.append(dict(title=title, excerpt=excerpt[:600], url=canonical,
                    source=name, official=official, published=published.isoformat(),
                    page_published=[d.isoformat() for d in valid], category=category, advice=advice))
            except (OSError, ValueError) as error:
                continue
        return records, dict(source=name, url=url, status='ok', candidates=len(records))
    except (OSError, ValueError) as error:
        return [], dict(source=name, url=url, status='failed', error=str(error)[:180])


def compose(records, now, statuses):
    start = now - timedelta(hours=24)
    text = f'**AI 与科技每日简报｜{now.year}年{now.month}月{now.day}日**\n\n'
    text += f'本期从官方订阅源和科技媒体采集到 {len(records)} 条通过发布时间筛选的报道。**这是无模型的采集与模板排版版**，保留原文标题与摘要，不自动翻译英文材料，也不将来源摘要改写为独立查证的结论。下文按来源优先级整理，建议围绕产品可用性、技术条件和业务适配阅读原文；**分类提示属于通用评估建议，并非当日趋势分析**。\n\n'
    text += f'北京时间检索窗口：{start:%Y-%m-%d %H:%M}—{now:%Y-%m-%d %H:%M}；订阅与原文发布日期均须落在窗口内，报道时间不保证等于事件发生时间。\n\n'
    failures = [s['source'] for s in statuses if s['status'] == 'failed']
    if failures:
        text += '部分来源采集失败：' + '、'.join(failures) + '。覆盖不完整。\n\n'
    for i, item in enumerate(records, 1):
        title = html.escape(item['title']).replace('*', '&#42;').replace('[', '&#91;')
        text += f"**{i}. {item['source']}｜{title}**\n\n"
        text += '来源摘要（保留原文）：' + html.escape(item['excerpt']).replace('*', '&#42;').replace('[', '&#91;') + '\n\n'
        text += f"本条属于 **{item['category']}**。采集器已核对订阅时间和页面发布元数据，但不能自动核实事件是否首次发生、价格参数是否准确或性能是否可复现；相关结论以链接原文及后续人工核验为准。\n\n"
        text += '**趋势判断：**模板版不从单篇摘要推断行业趋势。阅读时应区分已上线能力、预览和计划，比较许可、可用范围与实际部署条件，避免把发布措辞当成独立验证。\n\n'
        text += '**行动建议：**' + item['advice'] + '\n\n'
        label = '官方发布' if item['official'] else '报道'
        text += f"[{item['source']} {label} ↗]({item['url']})\n\n---\n\n"
    if not records:
        text += '本次未采集到通过发布时间筛选的报道，不补入旧闻。该结果仅代表配置来源的采集情况，不代表过去24小时没有重要新闻。\n\n'
    text += '**今天最值得记住的一件事**\n\n本版提供可追溯的阅读入口，不自动生成跨事件的因果关系或当天核心趋势。订阅与页面时间筛选有助于排除明显旧文，但不能替代事件核验。对于准备采用新产品或技术的团队，先核对原文中的上线状态、许可与适用条件，再决定是否进入小规模测试。英文来源保留原文，图片未经人工核对不自动插入。\n\n未来24至72小时可关注相关产品的正式可用状态、文档与许可变化，以及独立复现结果；这些是通用观察方向，不是已确认的后续事件。\n'
    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--force', action='store_true', help='备份已有当天文件后重新采集')
    args = parser.parse_args()
    now = datetime.now(ZoneInfo('Asia/Shanghai'))
    folder = ROOT / now.strftime('%Y-%m-%d')
    if (folder / 'briefing.md').exists() and not args.force:
        print('当天简报已存在，保留原文件。')
        return
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda source: collect(source, now), FEEDS))
    statuses = [status for _, status in results]
    records = [record for items, _ in results for record in items]
    seen, selected = set(), []
    records.sort(key=lambda item: (not item['official'], -datetime.fromisoformat(item['published']).timestamp()))
    for item in records:
        key = re.sub(r'\W+', '', item['title']).lower()
        if item['url'] in seen or key in seen: continue
        seen.update([item['url'], key])
        selected.append(item)
        if len(selected) == 6: break
    # Transport failure is not a legitimate empty news day.
    if all(status['status'] == 'failed' for status in statuses):
        for status in statuses: print(status['source'] + ': ' + status['error'])
        raise SystemExit('全部来源采集失败，未生成简报。请检查网络访问设置。')
    text = compose(selected, now, statuses)
    folder.mkdir(exist_ok=True)
    if args.force:
        backup = folder / ('backup-' + now.strftime('%H%M%S%f'))
        existing = [folder / name for name in ['briefing.md', 'briefing.html', 'sources.json'] if (folder / name).exists()]
        if existing:
            backup.mkdir()
            for path in existing: path.rename(backup / path.name)
    data = {'mode': 'rss-template', 'cutoff': now.isoformat(), 'sources': statuses, 'articles': selected}
    for name, content in [('briefing.html', render(text)), ('sources.json', json.dumps(data, ensure_ascii=False, indent=2)), ('briefing.md', text)]:
        temp = folder / (name + '.tmp')
        temp.write_text(content, encoding='utf-8')
        temp.replace(folder / name)
    print(f'已生成 {folder.relative_to(ROOT)}：{len(selected)} 条，{len(statuses) - sum(s["status"] == "failed" for s in statuses)} 个来源可用。')


if __name__ == '__main__':
    main()
