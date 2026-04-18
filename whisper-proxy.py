"""Whisper Proxy - 內建 faster-whisper (CTranslate2) 的 STT 伺服器。

提供 OpenAI 相容的 /v1/audio/transcriptions 端點。
使用 faster-whisper + CUDA 取代 whisper.cpp，推論速度提升 ~8 倍。
"""

import os
import time
import tempfile
import asyncio
import uvicorn
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import PlainTextResponse, JSONResponse
from faster_whisper import WhisperModel

# 設定 CUDA DLL 路徑（pip 安裝的 nvidia-cublas-cu12 / nvidia-cudnn-cu12）
_site = os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Python", "Python313", "site-packages")
_cuda_paths = [
    os.path.join(_site, "nvidia", "cublas", "bin"),
    os.path.join(_site, "nvidia", "cudnn", "bin"),
]
_existing = os.environ.get("PATH", "")
for p in _cuda_paths:
    if os.path.isdir(p) and p not in _existing:
        os.environ["PATH"] = p + ";" + _existing
        _existing = os.environ["PATH"]

app = FastAPI(title="Whisper Proxy (faster-whisper)")

# 從環境變數讀取設定
MODEL_SIZE = os.environ.get("WHISPER_MODEL", "small")
DEVICE = os.environ.get("WHISPER_DEVICE", "cuda")
COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "float16")
LANGUAGE = os.environ.get("WHISPER_LANGUAGE", "zh")

# 預設中文 prompt — 長句繁體中文提升 bias，強制輸出繁體
DEFAULT_PROMPT = "以下是繁體中文的語音辨識結果，請使用繁體中文輸出。臺灣的科技產業發展迅速，許多國際企業在臺北設立辦公室。我們重視資訊安全與數位轉型的議題。"

# 全域模型實例（啟動時載入一次）
_model: WhisperModel | None = None


def get_model() -> WhisperModel:
    """取得或初始化 WhisperModel 單例。"""
    global _model
    if _model is None:
        print(f"載入 faster-whisper 模型: {MODEL_SIZE}, device={DEVICE}, compute_type={COMPUTE_TYPE}")
        t0 = time.time()
        _model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
        print(f"模型載入完成: {time.time() - t0:.1f}s")
    return _model


@app.on_event("startup")
async def startup():
    """啟動時預載模型。"""
    get_model()


@app.post("/v1/audio/transcriptions")
async def transcribe(
    file: UploadFile = File(...),
    model: str = Form(default="whisper-1"),
    language: str = Form(default=None),
    response_format: str = Form(default="json"),
    prompt: str = Form(default=None),
):
    """OpenAI 相容的 STT 端點。"""
    return await _do_transcribe(file, language, prompt)


@app.post("/inference")
async def inference(
    file: UploadFile = File(...),
    model: str = Form(default="whisper-1"),
    language: str = Form(default=None),
    response_format: str = Form(default="json"),
    prompt: str = Form(default=None),
    temperature: str = Form(default="0.0"),
    translate: str = Form(default=None),
):
    """相容舊的 /inference 端點（供 VoiceMode 內部使用）。"""
    return await _do_transcribe(file, language, prompt)


async def _do_transcribe(file: UploadFile, language: str | None, prompt: str | None):
    """核心轉錄邏輯：將上傳音訊存為暫存檔，用 faster-whisper 推論。"""
    audio_data = await file.read()
    lang = language or LANGUAGE
    # 永遠使用繁體中文 prompt（忽略客戶端傳入的 prompt）
    # 客戶端的 prompt 會導致簡體中文輸出
    stt_prompt = DEFAULT_PROMPT

    # 寫入暫存檔（faster-whisper 需要檔案路徑）
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_data)
        tmp_path = tmp.name

    try:
        t0 = time.time()
        # 在 executor 中執行同步的 transcribe（避免阻塞 asyncio event loop）
        text = await asyncio.get_event_loop().run_in_executor(
            None, _sync_transcribe, tmp_path, lang, stt_prompt
        )
        elapsed = time.time() - t0
        print(f"STT 完成: {elapsed:.1f}s → {text.strip()}")
        return PlainTextResponse(content=text)
    except Exception as e:
        print(f"STT 錯誤: {e}")
        return PlainTextResponse(content=f"Error: {e}", status_code=500)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _sync_transcribe(audio_path: str, language: str, prompt: str) -> str:
    """同步轉錄（在 executor thread 中執行）。"""
    model = get_model()
    segments, info = model.transcribe(
        audio_path,
        language=language,
        beam_size=1,
        best_of=1,
        initial_prompt=prompt,
    )
    return "".join(seg.text for seg in segments)


@app.get("/health")
async def health():
    """健康檢查。"""
    if _model is not None:
        return {"status": "ok", "engine": "faster-whisper", "model": MODEL_SIZE, "device": DEVICE}
    return {"status": "loading"}


if __name__ == "__main__":
    port = int(os.environ.get("WHISPER_PROXY_PORT", "2023"))
    print(f"Whisper Proxy (faster-whisper) 啟動在 port {port}")
    print(f"  模型: {MODEL_SIZE}, 裝置: {DEVICE}, 計算類型: {COMPUTE_TYPE}")
    uvicorn.run(app, host="127.0.0.1", port=port)
