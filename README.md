# AI 与科技每日简报（无需模型密钥）

每天北京时间07:00（UTC前一天23:00）由 GitHub Actions 触发，采集实际运行时刻之前24小时的 RSS/Atom 新闻，输出 `YYYY-MM-DD/briefing.html`、`briefing.md` 和 `sources.json`。不调用模型、翻译或付费搜索 API，不需要 `OPENAI_API_KEY`。

来源：OpenAI、Google AI、NVIDIA、Hugging Face、Microsoft Research、IT之家。配置位于 `scripts/generate.py` 的 `FEEDS`。只接收带时区的订阅发布时间，读取原文发布元数据再次筛选；不将更新时间当发布时间。对 URL 和规范化标题去重，最多6条，官方来源优先，其次按发布时间排序，不声称按实际影响排序。跨来源同一事件和报道/事件日期仍需人工核对。

版式保留紧凑标题、导语、编号新闻、加粗建议、原文链接、细分隔线和结尾。摘要与标题保留原文语言，趋势栏为明确标注的通用评估提示，不生成当日行业判断，也不保证2200—3200字。未经人工核验的图片不自动插入；渲染器支持后续人工添加横排图片组。`briefing-prompt.md` 保留原始编辑目标，不再作为模型提示词执行。

## 启用每日任务

将文件提交推送到默认分支，允许 GitHub Actions 运行和工作流写入仓库，再手动运行一次“AI 与科技每日简报”验证来源访问。无需添加模型密钥。定时工作流仅在默认分支生效，GitHub 可能延迟执行；分支保护可能阻止自动推送。当前本地文件未自动推送。

## 本地运行

```sh
cd /workspace/ai-daily-news
python3 -m venv /workspace/ai-daily-news-venv
/workspace/ai-daily-news-venv/bin/pip install -r requirements.txt
/workspace/ai-daily-news-venv/bin/python scripts/generate.py
/workspace/ai-daily-news-venv/bin/python -m unittest discover -s tests -v
```

默认保留当天已有简报。`--force` 会先把原文件备份到当天文件夹再重新采集。所有来源失败时以非零状态退出且不发布；部分失败会在简报和来源记录中说明。成功读取来源但没有合格报道时生成如实的空缺说明，不把采集范围等同于整个新闻世界。

云环境需要允许访问 `openai.com`、`blog.google`、`blogs.nvidia.com`、`huggingface.co`、`www.microsoft.com`、`www.ithome.com`；如原文重定向还需核实目标域名。GitHub Actions 使用独立网络，不继承此云环境策略。云任务不依赖常驻本地 cron。
