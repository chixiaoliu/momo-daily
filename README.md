---
title: momo-daily
emoji: 📖
colorFrom: indigo
colorTo: teal
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# momo·daily

把墨墨背单词里「今天要过的词」写成一篇可读的故事。

每个访客在「设置」里填自己的墨墨 Token 和模型 Key，数据只存在属于你这次访问的空间里。

- 取词：墨墨官方开放 API（今日新学 + 复习）
- 生成：任意 OpenAI 兼容模型（默认 DeepSeek）
- 阅读：生词高亮、点词查义、朗读、挖空自测、全文翻译
- 导出：单篇 PDF / Markdown，批量 ZIP

> 部署在 Hugging Face Spaces 的免费 CPU 档，闲置会休眠，首次打开需要等一会儿唤醒。
