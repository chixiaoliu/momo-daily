# 部署到 Render（让别人用自己的 Token 使用）

这个文件夹是给公网用的**精简副本**：只有代码和样例文章，不含任何个人 Token、你的文章、缓存。

## 一、推到 GitHub（2 分钟）

1. 打开 <https://github.com/new>，仓库名 `momo-daily`，Private 或 Public 都行，**不要**勾选任何初始化文件
2. 在这个文件夹里执行：

```powershell
git init
git add .
git commit -m "momo-daily"
git branch -M main
git remote add origin https://github.com/你的用户名/momo-daily.git
git push -u origin main
```

推送前可以确认一眼：`git status` 里不应该出现 `.env`、`output/`、`data/`。

## 二、Render 部署（2 分钟）

1. <https://render.com> → 用 GitHub 登录
2. **New** → **Blueprint** → 选 `momo-daily` 仓库 → **Apply**
3. `render.yaml` 会自动配好：`MOMO_PUBLIC=1`（每个访客自带 Token）、`MOMO_CORS=*`
4. 等 2~3 分钟，拿到 `https://xxx.onrender.com`

打开它 → 「设置」→ 填你自己的墨墨 Token 和模型 Key → 保存 → 回首页生成。

## 三、确认隔离（重要）

- 开一个**无痕窗口**访问同一个网址：应该显示「还没填墨墨 Token」
- 你填的配置只落在 `prototype/data/sessions/<随机 id>/config.json`
- 服务端**完全不读** `.env`，也就是说站长自己的 Token 根本没进这个进程

## 四、固定网址 + 更快打开（可选）

把 `web/` 上传到 Cloudflare Pages，并在 `web/config.js` 里填 Render 地址：

```js
window.MOMO_API = "https://xxx.onrender.com";
```

这样页面秒开（静态），只有生成和查词才走后端。

## 三个已知限制（免费档的代价）

| 限制 | 表现 | 缓解 |
|---|---|---|
| 15 分钟无人访问休眠 | 第一次打开慢 30~60 秒 | 前端提示「正在唤醒后端」 |
| 磁盘临时 | 重启后所有人要重新填 Token，文章也会丢 | 升级付费盘，或只当体验用 |
| 单实例 512 MB | 多人同时生成会排队 | 一次只跑一个任务，代码里已有锁 |

## 不要做的事

- 不要在这个仓库里提交 `.env`
- 不要把 `prototype/output/`（你的文章）和 `data/`（访客会话）提交上去
- 不要把 `MOMO_CORS` 长期留成 `*`，上线后改成你的 Pages 域名
