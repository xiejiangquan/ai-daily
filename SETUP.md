# AI Daily News Backend — 部署指南

## 快速开始

### 1. 创建 GitHub 仓库

```bash
# 把这个文件夹推到你的 GitHub 仓库
cd ai-daily-backend
git init
git add .
git commit -m "init ai daily backend"
git remote add origin https://github.com/你的用户名/ai-daily.git
git branch -M main
git push -u origin main
```

### 2. 配置 API Keys

去仓库 **Settings → Secrets and variables → Actions → New repository secret**，添加：

| Secret 名称 | 必填 | 说明 |
|---|---|---|
| `NEWSAPI_KEY` | 推荐 | https://newsapi.org 注册，免费版每天 100 次 |
| `OPENAI_API_KEY` | 二选一 | OpenAI API key |
| `ANTHROPIC_API_KEY` | 二选一 | Anthropic Claude API key |
| `X_BEARER_TOKEN` | 可选 | X API v2 Bearer Token（没有也能跑） |

至少需要一个 AI API key（OpenAI 或 Anthropic）。

### 3. 启用 GitHub Pages

1. 仓库 **Settings → Pages**
2. Source 选 **Deploy from a branch**
3. Branch 选 `main`，文件夹选 `/docs`
4. 保存

几分钟后你的 JSON 接口就可以通过以下地址访问：

```
https://你的用户名.github.io/ai-daily/news.json
```

### 4. 手动触发测试

1. 仓库 **Actions** 页面
2. 左侧选 **Daily AI News**
3. 点 **Run workflow** 手动触发一次
4. 等待运行完毕，检查 `docs/news.json` 是否生成

### 5. 本地测试

```bash
# 设置环境变量
export NEWSAPI_KEY="你的key"
export OPENAI_API_KEY="你的key"

# 运行
pip install requests
python generate_news.py

# 查看结果
cat docs/news.json
```

## JSON 输出格式

iOS App 从 `news.json` 拿到的数据结构：

```json
{
  "last_updated": "2026-04-07T09:00:00+08:00",
  "total_days": 7,
  "days": [
    {
      "date": "2026-04-07",
      "headline": "一句话总结今天最重要的 AI 事件",
      "sections": [
        {
          "title": "模型发布",
          "items": [
            {
              "title": "新闻标题",
              "summary": "中文摘要",
              "source": "来源",
              "url": "链接",
              "tags": ["GPT", "LLM"]
            }
          ]
        }
      ],
      "x_highlights": [
        {
          "topic": "X 热门话题",
          "summary": "讨论内容摘要"
        }
      ]
    }
  ]
}
```

## 费用估算

- GitHub Actions: 免费（每月 2000 分钟，每次运行约 1 分钟）
- GitHub Pages: 免费
- NewsAPI: 免费版足够
- OpenAI gpt-4o-mini: 约 $0.01/天
- **总计: 基本为零**
