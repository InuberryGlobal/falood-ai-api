from fastapi import FastAPI, WebSocket, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.security import OAuth2PasswordBearer
import session_service
import jwt_service
import jwt
import numpy as np
import time
import resampy  
from vad import VAD
from transcriber import Transcriber
from llm.llm_client import LLMClient
from llm.prompt_builder import InterviewContext
import uvicorn
import asyncio
import auth_service
import deps
import psycopg2
from typing import Dict
from dotenv import load_dotenv
import os
import httpx

load_dotenv()
active_websockets: Dict[str, WebSocket] = {}

def get_db_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

app = FastAPI()

@app.get("/health")
def health_check():
    return {"status": "ok"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TARGET_SAMPLE_RATE = 16000
ORIGINAL_SAMPLE_RATE = 48000  

frame_duration_ms = 30
frame_samples = int(ORIGINAL_SAMPLE_RATE * frame_duration_ms / 1000)
silence_timeout = 0.7 

vad = VAD(sample_rate=TARGET_SAMPLE_RATE, mode=3)
transcriber = Transcriber()
llm_client = LLMClient()
context = InterviewContext(
    role="OSP Engineer",
    company="Inuberry Global",
    skills=["Fiber Design", "Splicing", "Permitting", "AutoCAD", "OTDR Testing"]
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="sign-in")

class UserCreate(BaseModel):
    email: str
    password: str
    username: str

class UserSignIn(BaseModel):
    email: str
    password: str

class User(BaseModel):
    email: str
    username: str
    id: str

class SessionDetails(BaseModel):
    company: str
    position: str

@app.post("/auth/sign-up", status_code=status.HTTP_201_CREATED)
def signup(user: UserCreate):
    return auth_service.create_user(user.email, user.username, user.password)

@app.post("/session-details", status_code=status.HTTP_201_CREATED)
def create_or_update_session_details(session: SessionDetails, user_id: str = Depends(deps.current_user_id)):
    return session_service.upsert_session_details(user_id, session.company, session.position)

@app.get("/session-details")
def get_session_details(user_id: str = Depends(deps.current_user_id)):
    return session_service.get_session_details(user_id)

@app.get("/session-details/{session_id}")
def get_one_session_details(session_id: str, token: str = Depends(oauth2_scheme)):
    return session_service.get_one_session_details(session_id)

@app.get("/session")
def get_sessions(user_id: str = Depends(deps.current_user_id)):
    return session_service.get_all_sessions(user_id)

@app.post("/session")
def create_session(user_id: str = Depends(deps.current_user_id)):
    return session_service.create_session(user_id)

@app.post("/auth/sign-in", status_code=status.HTTP_200_OK)
def login(user: UserSignIn):
    return auth_service.sign_in(user.email, user.password)

@app.get("/auth/me", status_code=status.HTTP_200_OK)
def get_current_user(token: str = Depends(oauth2_scheme)):
    return auth_service.get_me(token)

@app.websocket("/ws/audio/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    
    if _session_is_ended(session_id) or not session_id:
        await websocket.close(code=1008)
        return

    active_websockets[session_id] = websocket

    audio_buffer = np.array([], dtype=np.float32)
    speech_audio = np.array([], dtype=np.float32)
    silence_start = None

    try:
        while True:
            data = await websocket.receive_bytes()
            chunk = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
            audio_buffer = np.concatenate([audio_buffer, chunk])

            while len(audio_buffer) >= frame_samples:
                frame = audio_buffer[:frame_samples]
                audio_buffer = audio_buffer[frame_samples:]

                frame_16k = resampy.resample(frame, ORIGINAL_SAMPLE_RATE, TARGET_SAMPLE_RATE)
                pcm_bytes = (frame_16k * 32768).astype(np.int16).tobytes()
                if len(pcm_bytes) != len(frame_16k) * 2:
                    continue

                if vad.is_speech(pcm_bytes):
                    print("[VAD] Detected speech")
                    speech_audio = np.concatenate([speech_audio, frame])
                    silence_start = None
                elif speech_audio.size > 0:
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start > silence_timeout:
                        full_audio = np.copy(speech_audio)
                        speech_audio = np.array([], dtype=np.float32)
                        silence_start = None

                        audio_16k = resampy.resample(full_audio, ORIGINAL_SAMPLE_RATE, TARGET_SAMPLE_RATE)
                        print(f"[TRANSCRIBE] Audio duration: {len(audio_16k)/TARGET_SAMPLE_RATE:.2f}s")

                        try:
                            transcript = transcriber.transcribe(audio_16k).strip()
                            print(f"[TRANSCRIPT] {transcript}")
                        except Exception as e:
                            print(f"[ERROR] Transcription failed: {e}")
                            transcript = ""

                        if transcript:
                            await websocket.send_json({
                                "transcription": transcript,
                                "ai_response_token": None
                            })

                            loop = asyncio.get_running_loop()
                            ai_chunks = [] 

                            async def push_token(token):
                                ai_chunks.append(token) 
                                await websocket.send_json({
                                    "transcription": None,
                                    "ai_response_token": token
                                })

                            def on_token(token):
                                asyncio.run_coroutine_threadsafe(push_token(token), loop)

                            llm_response = await asyncio.to_thread(
                                llm_client.generate_response, transcript, context, on_token=on_token
                            )

                            full_ai_text = llm_response or "".join(ai_chunks)

                            def _save_conversation():
                                with get_db_connection() as conn:
                                    with conn.cursor() as cur:
                                        cur.execute(
                                            """
                                            INSERT INTO session_conversations (session_id, question, response)
                                            VALUES (%s, %s, %s)
                                            """,
                                            (session_id, transcript, full_ai_text)
                                        )
                                        conn.commit()

                            await asyncio.to_thread(_save_conversation)

    except Exception as e:
        print(f"[WebSocket Error] {e}")
        await websocket.close()


@app.post("/session/{session_id}/stop")
async def stop_session(session_id: str):
    ws = active_websockets.get(session_id)
    if ws:
        try:
            await ws.close(code=1000)
        except Exception:
            pass
        finally:
            active_websockets.pop(session_id, None)

    def _mark_session_ended():
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE sessions SET ended_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (session_id,),
                )
                conn.commit()

    try:
        await asyncio.to_thread(_mark_session_ended)
    except Exception:
        raise HTTPException(status_code=500, detail="Database error")

    return {"ok": True}


def _session_is_ended(session_id: str) -> bool:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT ended_at FROM sessions WHERE id = %s", (session_id,))
            row = cur.fetchone()
            return bool(row and row[0] is not None)

# --- Self-ping to keep Render free tier alive ---
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")

@app.on_event("startup")
async def start_keep_alive():
    if RENDER_EXTERNAL_URL:
        asyncio.create_task(_keep_alive())

async def _keep_alive():
    while True:
        await asyncio.sleep(14 * 60)  # every 14 minutes
        try:
            async with httpx.AsyncClient() as client:
                await client.get(f"{RENDER_EXTERNAL_URL}/health")
                print("[KEEP-ALIVE] Pinged self")
        except Exception as e:
            print(f"[KEEP-ALIVE] Ping failed: {e}")

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
