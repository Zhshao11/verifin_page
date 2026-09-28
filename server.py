"""VeriFin 官网服务。

不是静态站 —— 页面上的「核验」按钮会真的去跑 VeriFin 的确定性链路：

    四路召回 → RRF 融合 → span 硬校验 → PyMuPDF 坐标定位 → 六元组 / 拒答

做法上刻意**不复制任何业务逻辑**：直接 import VeriFin 自己的 `web.server`，
复用它的 `BUNDLES`（启动期一次性装配的报告运行时）与全部端点函数。
另起一套必然漂移 —— 那时网页上跑到的就不是评测里跑的那个系统了。

只有一处必要的适配：VeriFin 把证据特写图写进它自己的 `web/assets/`，
这里把返回给前端的图片 URL 从 `/assets/xxx.png` 改写成 `/evidence/xxx.png`，
避免与本站自己的静态资源（CSS / 字体）路径打架。**图片本身是真的，没有重画。**

启动:
    <VeriFin>/.venv/bin/python verifin-site/server.py
"""

from __future__ import annotations

import re
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # verifin-site/
SITE_DIR = HERE / "site"                        # 静态站点
VERIFIN_ROOT = Path(
    os.environ.get(
        "VERIFIN_ROOT",
        "/Users/shihao/WorkBuddy/2026-09-19-02-37-19",
    )
).expanduser().resolve()

# 让 `import web.server` 与它的 `from verifin... import` 都能解析到 VeriFin。
sys.path.insert(0, str(VERIFIN_ROOT))

import web.server as vs  # noqa: E402  ← 导入即完成 BUNDLES 装载（这是我们要的效果）

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse  # noqa: E402

app = FastAPI(title="VeriFin Site", version="1.0.0")

ASSETS_DIR = (SITE_DIR / "assets").resolve()

#: HTML 与 CSS 都走「每次重验证」而不是启发式强缓存。
#: 默认的 FileResponse 不带 Cache-Control，浏览器会按启发式规则把一个旧 CSS
#: 缓存住不再回源 —— 结果就是新样式发上去了、访客看到的还是老版面。
#: no-cache 不是「不缓存」，而是「用 ETag 回源确认」，未变时仍是 304，开销极小。
_NO_CACHE = {"Cache-Control": "no-cache, must-revalidate"}

#: 字体等二进制资源一年内不回源。默认的 FileResponse 不带 Cache-Control，
#: 等于把「要不要缓存」交给浏览器的启发式规则，反而多出一次不必要的条件请求。
#: ⚠️ 代价：字体文件名里没有内容哈希，**换字体时必须同时改名**（或改用带 hash
#: 的文件名），否则老访客会一直用缓存里的旧字体。
_IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}

#: 站点自己带的内容版本。改动 HTML/CSS 时同步 +1，让线上立刻换新而不是等过期。
SITE_VERSION = "4"


def _page(path: Path) -> HTMLResponse:
    """读一份页面 HTML，并把 CSS 引用统一打上版本号。

    用正则同时覆盖「还没版本号」和「版本号已过期」两种情况，
    否则改了 SITE_VERSION 而 HTML 里已经写死旧版本号时不会被更新。
    """
    html = path.read_text(encoding="utf-8")
    for asset in ("assets/style.css", "assets/figures.css"):
        html = re.sub(
            r'href="' + re.escape(asset) + r'(\?v=[^"]*)?"',
            f'href="{asset}?v={SITE_VERSION}"',
            html,
        )
    return HTMLResponse(html, headers=_NO_CACHE)


# --------------------------------------------------------------------------
# 静态站点
# --------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return _page(SITE_DIR / "index.html")


#: 允许直接访问的页面白名单 —— 用固定映射而不是把 path 拼进文件系统，
#: 这样"用户可以访问哪些页面"是一个显式的、可审计的清单。
PAGES: dict[str, str] = {
    "/tech": "tech.html",
    "/tech.html": "tech.html",
    "/index.html": "index.html",
}


@app.get("/{page}", response_class=HTMLResponse)
def page(page: str) -> HTMLResponse:
    """伺服白名单内的页面（如技术子页）。不在白名单内一律 404。"""
    name = PAGES.get("/" + page)
    if name is None:
        raise HTTPException(status_code=404, detail="页面不存在")
    return _page(SITE_DIR / name)


@app.get("/assets/{path:path}")
def site_asset(path: str) -> FileResponse:
    """本站自己的资源（style.css / app 逻辑内联 / fonts/*）。

    做路径穿越防护：解析后的真实路径必须落在 assets/ 内，
    否则 `../../.ssh/id_rsa` 这类请求会读到仓库外的文件。
    """
    target = (ASSETS_DIR / path).resolve()
    if not str(target).startswith(str(ASSETS_DIR) + "/"):
        raise HTTPException(status_code=404, detail="资源不存在")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="资源不存在")
    # CSS/JS 走 ETag 回源重验证（旧样式滞留过一次，见 _NO_CACHE 注释）；
    # 字体走长缓存，换字体时记得同步改名。
    headers = _NO_CACHE if target.suffix.lower() in {".css", ".js"} else _IMMUTABLE
    return FileResponse(target, headers=headers)


@app.get("/evidence/{name:path}")
def evidence(name: str) -> FileResponse:
    """从 PDF 现场裁剪出来的证据特写图（由 VeriFin 的定位层真实渲染）。"""
    base = Path(vs.ASSET_DIR).resolve()
    target = (base / name).resolve()
    if not str(target).startswith(str(base) + "/"):
        raise HTTPException(status_code=404, detail="证据图不存在")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="证据图不存在")
    return FileResponse(target)


# --------------------------------------------------------------------------
# API —— 薄转发到 VeriFin 自己的端点函数，不重写任何判定
# --------------------------------------------------------------------------


def _rehost_evidence(payload: dict) -> dict:
    """把证据图 URL 从 VeriFin 的 /assets/ 改写到本站的 /evidence/。"""
    geo = payload.get("geometry")
    if isinstance(geo, dict) and geo.get("image"):
        geo["image"] = geo["image"].replace("/assets/", "/evidence/", 1)
    return payload


@app.post("/api/ask")
def api_ask(req: vs.AskRequest) -> JSONResponse:
    return JSONResponse(_rehost_evidence(vs.ask(req)))


@app.post("/api/guard")
def api_guard(req: vs.GuardRequest) -> JSONResponse:
    return JSONResponse(vs.guard(req))


@app.post("/api/identity")
def api_identity(period: str = "current", doc: str = vs.DEFAULT_DOC) -> JSONResponse:
    return JSONResponse(vs.identity(period=period, doc=doc))


@app.get("/api/meta")
def api_meta(doc: str = vs.DEFAULT_DOC) -> JSONResponse:
    return JSONResponse(vs.meta(doc=doc))


@app.post("/api/agent")
def api_agent(req: vs.AskRequest, planner: str = "policy") -> JSONResponse:
    return JSONResponse(vs.agent_run(req, planner=planner))


@app.get("/api/agent/runs")
def api_agent_runs(limit: int = 10) -> JSONResponse:
    return JSONResponse(vs.agent_runs(limit=limit))


@app.get("/api/health")
def health() -> JSONResponse:
    """健康检查：把装载到的报告与 chunk 数一并回出来，便于确认不是空壳。"""
    return JSONResponse({
        "ok": True,
        "docs": [
            {
                "id": doc_id,
                "company": rt.constraints.company or "（发行人未识别）",
                "chunks": len(rt.chunks),
            }
            for doc_id, rt in vs.BUNDLES.items()
        ],
    })


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8951, log_level="info")
