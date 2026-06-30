#!/usr/bin/env python3
"""
temp_voice_bridge.py — Bridge between Rust songbird voice receiver and gemma12b.

Spawns the Rust voice_receiver binary, reads decoded PCM audio from stdout,
and feeds it into a minimal audio pipeline for transcription + LLM response.

Usage:
    python temp_voice_bridge.py --guild-id G --channel-id C [--token TOKEN]

The Rust binary is built with: cargo build --release (in temp_voice_test/)
"""
import argparse
import asyncio
import base64
import io
import os
import queue
import struct
import subprocess
import sys
import threading
import wave
from datetime import datetime
from typing import Dict, Optional

import numpy as np


# ─── Minimal audio processor ────────────────────────────────────────────────

class MinimalAudioProcessor:
    """Buffers PCM per-user, detects silence, sends to gemma12b."""

    def __init__(self, gemma_url: str = "http://localhost:8080"):
        self.gemma_url = gemma_url
        self.user_buffers: Dict[str, bytearray] = {}
        self.user_silence_frames: Dict[str, int] = {}
        self.currently_speaking: set = set()
        self.VAD_THRESHOLD = 500
        self.FRAMES_PER_SECOND = 50
        self.SILENCE_FRAMES_THRESHOLD = int(1.5 * self.FRAMES_PER_SECOND)
        self.usernames: Dict[str, str] = {}
        self.stats = {'chunks': 0, 'vad': 0, 'silence': 0, 'transcriptions': 0}

    def set_username(self, user_id: str, username: str):
        self.usernames[user_id] = username

    def feed(self, user_id: str, guild_id: str, channel_id: str, pcm: bytes):
        self.stats['chunks'] += 1
        username = self.usernames.get(user_id, f"user_{user_id}")

        if user_id not in self.user_buffers:
            self.user_buffers[user_id] = bytearray()
            self.user_silence_frames[user_id] = 0

        is_voice = False
        try:
            arr = np.frombuffer(pcm, dtype=np.int16)
            if len(arr) > 0:
                rms = float(np.sqrt(np.mean(arr.astype(np.float32) ** 2)))
                is_voice = rms > self.VAD_THRESHOLD
        except Exception:
            pass

        if is_voice:
            self.user_buffers[user_id].extend(pcm)
            self.user_silence_frames[user_id] = 0
            if user_id not in self.currently_speaking:
                self.currently_speaking.add(user_id)
                self.stats['vad'] += 1
                print(f" {username} started speaking", flush=True)
        else:
            if user_id in self.currently_speaking:
                self.user_silence_frames[user_id] += 1
                if self.user_silence_frames[user_id] >= self.SILENCE_FRAMES_THRESHOLD:
                    buf = self.user_buffers.get(user_id)
                    if buf and len(buf) >= 96000:
                        audio = bytes(buf)
                        print(f" Utterance from {username}: {len(audio)} bytes", flush=True)
                        asyncio.create_task(self._transcribe(audio, user_id, username, guild_id, channel_id))
                    self.currently_speaking.discard(user_id)
                    self.user_silence_frames[user_id] = 0
                    self.user_buffers[user_id] = bytearray()
                    self.stats['silence'] += 1
            else:
                self.user_buffers[user_id] = bytearray()

    async def _transcribe(self, audio: bytes, user_id: str, username: str, guild_id: str, channel_id: str):
        try:
            import httpx
            wav_b64 = self._pcm_to_wav_b64(audio)

            messages = [{
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': f'Transcribe exactly what {username} said. Output only the transcription.'},
                    {'type': 'input_audio', 'input_audio': {'data': wav_b64, 'format': 'wav'}},
                ],
            }]

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(f"{self.gemma_url}/v1/chat/completions", json={
                    'model': 'gemma12b', 'messages': messages,
                    'max_tokens': 300, 'temperature': 0.0,
                })
                resp.raise_for_status()
                transcription = resp.json()['choices'][0]['message']['content'].strip().strip('"\'')

            if transcription:
                self.stats['transcriptions'] += 1
                print(f" TRANSCRIBED [{username}]: {transcription}", flush=True)
                await self._respond(transcription, username)
            else:
                print(f" Empty transcription from {username}", flush=True)
        except Exception as e:
            print(f" Transcription error: {e}", flush=True)

    async def _respond(self, text: str, username: str):
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(f"{self.gemma_url}/v1/chat/completions", json={
                    'model': 'gemma12b',
                    'messages': [
                        {'role': 'system', 'content': 'You are a helpful AI assistant in a Discord voice channel. Respond concisely.'},
                        {'role': 'user', 'content': f'{username} said: "{text}"'},
                    ],
                    'max_tokens': 200, 'temperature': 0.7,
                })
                resp.raise_for_status()
                reply = resp.json()['choices'][0]['message']['content'].strip()
            if reply:
                print(f" GEMMA RESPONSE: {reply}", flush=True)
        except Exception as e:
            print(f" Response error: {e}", flush=True)

    @staticmethod
    def _pcm_to_wav_b64(audio_data: bytes, sample_rate: int = 16000) -> str:
        arr = np.frombuffer(audio_data, dtype=np.int16)
        if len(arr) % 2 == 0:
            mono = arr[::2]
        else:
            mono = arr
        ratio = 48000 / sample_rate
        target_len = int(len(mono) / ratio)
        indices = np.linspace(0, len(mono) - 1, target_len)
        mono = np.interp(indices, np.arange(len(mono)), mono).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            w.writeframes(mono.tobytes())
        return base64.b64encode(buf.getvalue()).decode('ascii')


# ─── Stdout reader thread ───────────────────────────────────────────────────

class StdoutReader:
    """Reads binary protocol from Rust process stdout in a background thread.

    Protocol:
        AUDIO:{user_id}:{pcm_len}\n{pcm_bytes}
        JOIN:{user_id}\n
        LEAVE:{user_id}\n
        READY:{bot_name}\n
        CONNECTED\n
        etc.
    """

    def __init__(self, proc: subprocess.Popen):
        self.proc = proc
        self.events: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        stdout = self.proc.stdout
        assert stdout is not None
        buf = bytearray()

        while True:
            chunk = stdout.read(8192)
            if not chunk:
                self.events.put(None)  # sentinel
                break

            buf.extend(chunk)

            while True:
                nl = buf.find(b'\n')
                if nl < 0:
                    break

                line_bytes = bytes(buf[:nl])
                del buf[:nl + 1]

                try:
                    line = line_bytes.decode('utf-8')
                except UnicodeDecodeError:
                    continue

                if line.startswith('AUDIO:'):
                    parts = line.split(':')
                    if len(parts) >= 3:
                        user_id = parts[1]
                        pcm_len = int(parts[2])
                        # Read exact PCM bytes
                        while len(buf) < pcm_len:
                            extra = stdout.read(pcm_len - len(buf))
                            if not extra:
                                break
                            buf.extend(extra)
                        pcm = bytes(buf[:pcm_len])
                        del buf[:pcm_len]
                        self.events.put(('audio', user_id, pcm))
                elif line.startswith('JOIN:'):
                    self.events.put(('join', line.split(':')[1]))
                elif line.startswith('LEAVE:'):
                    self.events.put(('leave', line.split(':')[1]))
                else:
                    self.events.put(('log', line))

    def get(self, timeout: float = 0.5):
        try:
            return self.events.get(timeout=timeout)
        except queue.Empty:
            return None


# ─── Main ───────────────────────────────────────────────────────────────────

async def run_bridge(args):
    token = args.token
    if not token:
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.strip().startswith('DISCORD_TOKEN='):
                        token = line.strip().split('=', 1)[1]
                        break
    if not token:
        print(" No token. Pass --token or set DISCORD_TOKEN in .env", flush=True)
        return

    bin_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'target', 'release', 'voice_receiver')
    if not os.path.exists(bin_path):
        print(f" Binary not found at {bin_path}", flush=True)
        print("   Run: cd temp_voice_test && cargo build --release", flush=True)
        return

    print(f" Starting Rust voice receiver...", flush=True)
    print(f"   Guild: {args.guild_id}, Channel: {args.channel_id}", flush=True)

    proc = subprocess.Popen(
        [bin_path, '--token', token, '--guild-id', str(args.guild_id), '--channel-id', str(args.channel_id)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        bufsize=0,
    )

    processor = MinimalAudioProcessor(gemma_url=args.gemma_url)
    reader = StdoutReader(proc)

    # Read stderr in background (blocking I/O in a thread, not async)
    def stderr_thread():
        import io as _io
        try:
            stderr_text = _io.TextIOWrapper(proc.stderr, encoding='utf-8', errors='replace', line_buffering=True)  # type: ignore
            while True:
                line = stderr_text.readline()
                if not line:
                    break
                print(f"   [rust] {line.rstrip()}", flush=True)
        except Exception as e:
            print(f"   [stderr] Error: {e}", flush=True)

    threading.Thread(target=stderr_thread, daemon=True).start()

    print("⏳ Listening for audio... (join a voice channel and speak)", flush=True)

    while proc.poll() is None:
        event = reader.get(timeout=1.0)
        if event is None:
            continue

        if event[0] == 'audio':
            _, user_id, pcm = event
            processor.feed(
                user_id=user_id,
                guild_id=str(args.guild_id),
                channel_id=str(args.channel_id),
                pcm=pcm,
            )
        elif event[0] == 'join':
            print(f" User joined: {event[1]}", flush=True)
        elif event[0] == 'leave':
            print(f" User left: {event[1]}", flush=True)
        elif event[0] == 'log':
            msg = event[1]
            if 'READY' in msg:
                print(f" Connected as: {msg.split(':', 1)[-1] if ':' in msg else msg}", flush=True)
            elif 'CONNECTED' in msg:
                print("🔗 Voice channel joined!", flush=True)
            elif 'JOINING' in msg:
                print("🔗 Joining voice channel...", flush=True)
            elif 'EVENTS_REGISTERED' in msg:
                print("🎧 Voice events registered", flush=True)
            elif 'SONGBIRD_OK' in msg:
                print(" Songbird initialized", flush=True)
            else:
                print(f"   [rust] {msg}", flush=True)

    print(f"\n Stats: {processor.stats}", flush=True)
    proc.terminate()


def main():
    parser = argparse.ArgumentParser(description='Bridge: Rust voice receiver → gemma12b')
    parser.add_argument('--guild-id', type=int, required=True)
    parser.add_argument('--channel-id', type=int, required=True)
    parser.add_argument('--token', type=str, default=None)
    parser.add_argument('--gemma-url', type=str, default='http://localhost:8080')
    args = parser.parse_args()
    asyncio.run(run_bridge(args))


if __name__ == '__main__':
    main()
