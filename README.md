# VeriFin Website

VeriFin 的产品网站与在线核验入口。页面服务复用独立 VeriFin 项目中的检索、证据校验和定位运行时。

## Local development

```bash
cd /Users/shihao/WorkBuddy/2026-09-26-23-35-42/verifin-site
VERIFIN_ROOT=/Users/shihao/WorkBuddy/2026-09-19-02-37-19 \
  /Users/shihao/WorkBuddy/2026-09-19-02-37-19/.venv/bin/python \
  -m uvicorn server:app --host 127.0.0.1 --port 8951
```

## Deploy to i5

The i5 checkout lives at `/Users/zhushihao/Services/verifin-site`. After changes are pushed to `main`, update and restart the remote service with:

```bash
ssh i5 '/Users/zhushihao/Services/verifin-site/deploy/i5-update.sh'
```

The script performs a fast-forward-only pull, restarts the service on port `8951`, and waits for `/api/health` to pass.
