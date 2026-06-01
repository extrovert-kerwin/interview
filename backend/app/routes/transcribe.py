"""语音转写。

当前后端不内置 ASR——所有语音转写走前端浏览器原生 Web Speech API（webkitSpeechRecognition）。
保留此端点是为了前端在调用时能感知"后端无 STT"，从而走降级路径。
"""

from __future__ import annotations

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse

router = APIRouter()


@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    # 读取以消费请求体，但不做任何处理
    await audio.read()
    return JSONResponse(
        status_code=200,
        content={
            "error": "no_stt_key",
            "message": "后端未启用 ASR，请前端降级到浏览器 Web Speech API",
        },
    )
