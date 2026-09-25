"""FastAPI 入口：提供页面与对齐接口。"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .align import GAP_COST, OP_MATCH, OP_SCRIPT_ONLY, OP_SRT_ONLY, align, match_cost
from .parsing import parse_script, parse_srt

MAX_ITEMS = 4000  # 单侧条目上限，防止 DP 规模失控

app = FastAPI(title="字幕校稿对齐工具")
STATIC_DIR = Path(__file__).resolve().parent / "static"


class AlignRequest(BaseModel):
    script: str = ""
    srt: str = ""
    gap_cost: float = Field(default=GAP_COST, gt=0, le=1)


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/align")
def api_align(req: AlignRequest):
    script_items = parse_script(req.script)
    srt_items = parse_srt(req.srt)
    if not script_items:
        raise HTTPException(status_code=400, detail="对白稿为空：请粘贴逐行对白文本。")
    if not srt_items:
        raise HTTPException(status_code=400, detail="未解析到任何 SRT 字幕块：请检查字幕格式。")
    if len(script_items) > MAX_ITEMS or len(srt_items) > MAX_ITEMS:
        raise HTTPException(
            status_code=400,
            detail=f"条目过多：剧本 {len(script_items)} 条、字幕 {len(srt_items)} 条，上限各 {MAX_ITEMS} 条。",
        )

    ops, total = align(
        [s.norm for s in script_items],
        [s.norm for s in srt_items],
        gap=req.gap_cost,
    )

    rows = []
    n_match = n_script_only = n_srt_only = 0
    cost_sum = 0.0
    for op, i, j in ops:
        if op == OP_MATCH:
            s, t = script_items[i], srt_items[j]
            cost = match_cost(s.norm, t.norm)
            cost_sum += cost
            n_match += 1
            rows.append({
                "status": "match",
                "script_line": s.line_no, "script_text": s.text, "script_norm": s.norm,
                "srt_index": t.index, "srt_text": t.text, "srt_norm": t.norm,
                "start": t.start, "end": t.end,
                "cost": round(cost, 4),
            })
        elif op == OP_SCRIPT_ONLY:
            s = script_items[i]
            n_script_only += 1
            rows.append({
                "status": "script_only",
                "script_line": s.line_no, "script_text": s.text, "script_norm": s.norm,
                "srt_index": None, "srt_text": "", "srt_norm": "",
                "start": "", "end": "",
                "cost": None,
            })
        else:  # OP_SRT_ONLY
            t = srt_items[j]
            n_srt_only += 1
            rows.append({
                "status": "srt_only",
                "script_line": None, "script_text": "", "script_norm": "",
                "srt_index": t.index, "srt_text": t.text, "srt_norm": t.norm,
                "start": t.start, "end": t.end,
                "cost": None,
            })

    return {
        "rows": rows,
        "stats": {
            "script_count": len(script_items),
            "srt_count": len(srt_items),
            "match": n_match,
            "script_only": n_script_only,
            "srt_only": n_srt_only,
            "total_cost": round(total, 4),
            "avg_match_cost": round(cost_sum / n_match, 4) if n_match else 0.0,
            "gap_cost": req.gap_cost,
        },
    }
