# JSON 舆情报告目录

新报告以 `*.json` 保存在此目录，由根目录的 `report-viewer.html` 统一展示。

在 `data/catalog.json` 的语言报告项中使用：

```json
{
  "status": "ready",
  "data_source": "data/reports/游戏-版本-阶段-语言.json",
  "download_name": "游戏-版本-阶段-语言_舆情分析报告.html"
}
```

- “查看”会打开固定报告模板并载入 JSON。
- “下载”会在浏览器中把模板和 JSON 合成为可离线打开的独立 HTML。
- 旧报告继续使用 `href`，无需移动、改名或改写。
- 管理员在查看地址末尾加入 `&admin=1`，可用仅限本仓库的 GitHub 细粒度 Token 发布人工修订。
- Token 不得写入仓库、JSON、浏览器存储或聊天记录。
