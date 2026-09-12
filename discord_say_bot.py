#!/usr/bin/env python3
"""Discord say bot — slash command
`/say text:<ข้อความ> | file:<x.txt> [mood:<preset>] [export_tts:true] [save_local:true]`

`text` = ข้อความบรรทัดเดียว, `file` = `.txt` attachment สำหรับข้อความหลายบรรทัด
(ต้องระบุอย่างใดอย่างหนึ่ง — XOR)

ให้บอทเข้า voice channel ที่ผู้สั่งอยู่ สร้างเสียงด้วย qwen3-tts (เสียงโคลน — ไม่ระบุ
`voice:` = ใช้ default voice ที่ตั้งไว้ผ่าน `/voice-clone set-default`, fallback
`Liino` ถ้ายังไม่เคยตั้ง) ผ่าน tts_daemon fast path เท่านั้น (ไม่ fallback โหลดโมเดลเอง
ถ้า daemon ล่ม — ดู Decision ใน obsidian/kanban/tasks/TTS-1001.md) แล้วเล่นในห้องตามคิวต่อ guild

`export_tts:true` = ส่งออกเป็นไฟล์ `.wav` แนบในแชทแทนการเล่นเสียง — ไม่ต้องเข้า
voice channel (หลายบรรทัด/segment จะถูก concat ด้วย ffmpeg เป็นไฟล์เดียวก่อนแนบ)

`is_transcript:true` (ต้องคู่กับ `export_tts:true`) = แนบ `transcript.json` เพิ่มมา
อีกไฟล์ — timeline start/end คำนวณจากความยาว (ffprobe) ของแต่ละบรรทัด wav ที่ต่อกัน
เป็น export_path จริง (ไม่ใช้ STT/Whisper — ข้อความรู้อยู่แล้วจากที่สั่งพูด) schema
เดียวกับ hyperframes transcribe (flat array [{id, text, start, end}])

`save_local:true` (ต้องคู่กับ `export_tts:true`) = นอกจากแนบไฟล์ในแชทแล้ว
copy `.wav` (+ `.transcript.json` ถ้ามี `is_transcript:true`) เก็บไว้ในโปรเจกต์ที่
`outputs/say/<YYYYMMDD_HHMMSS>_<guild_id>.wav` ด้วย — เก็บไฟล์เสียงไว้ใช้ต่อโดยไม่ต้อง
ไปโหลดจาก Discord attachment

คำสั่งอื่นในบอทนี้:
`/transcribe file:<เสียง>` = ถอดเสียงเป็นข้อความ + emoji mood พร้อมวางใน `/say`
`/translate file:<transcript.json> source:<ja|en|th> target:<en|th> [mood] [voice] [save_local:true]` =
  แปล transcript.json (จาก `/transcribe`) เป็นภาษาอื่นด้วย MyMemory (deep_translator,
  ไม่ใช้ API key — สลับมาจาก GoogleTranslator เพราะ Google เว็บฟรีบล็อก IP ง่ายเกินไป;
  MyMemory ต้องระบุ source ชัดเจน เดา "auto" ไม่ได้) แล้ว gen เสียงใหม่ทับ +
  แนบ .wav/.txt/transcript.json ที่แปลแล้วกลับมาเสมอ (ไม่เล่นใน voice channel)
  แต่ละ entry ใน transcript.json ใส่ `mood` field เองได้ (เช่น "excited") จะเปลี่ยน
  โทนเสียงเฉพาะบรรทัดนั้น — ไม่ใส่ = ใช้ mood: param ของคำสั่ง หรือ default ของ voice
`/txt-to-json file:<x.txt> [mood]` = แปลงไฟล์ .txt (1 บรรทัด = 1 ประโยค) เป็น
  transcript.json schema เดียวกับ /transcribe ([{id, text, mood?}], ไม่มี start/end
  เพราะไม่มีเสียงจริง) — mood ต่อบรรทัดมาจาก [mood:xxx] tag/emoji ในบรรทัดนั้น (แบบ
  เดียวกับ /say) ไม่งั้นเดาจากคำ (detect_mood เหมือน /transcribe); mood: param ถ้าใส่
  จะบังคับทับทุกบรรทัด
`/voice-clone` (group) = สร้าง/จัดการเสียงโคลนใน voices/ (list/set-default/create/edit/delete/test)
`/voice-design description:<คำบรรยาย> text:<ตัวอย่าง> [save_as:<ชื่อ>] [overwrite:<bool>]` =
  สร้างเสียงใหม่จากคำบรรยายข้อความ (instruct) ด้วยโมเดล VoiceDesign ที่โหลดใน process
  ของบอทเอง (lazy singleton — ADR-0001, ไม่แตะ tts_daemon) แล้วแนบไฟล์ .wav กลับเสมอ
  (ไม่เล่นใน voice channel); `save_as` = บันทึกผลเป็น Voice ถาวรใหม่ใน voices/
  (trim/reformat เป็น reference clip + STT transcript + เก็บ description เป็น default instruct)

Usage:
    .venv/bin/python discord_say_bot.py

ต้อง export DISCORD_BOT_TOKEN เป็น process env var ก่อนรัน (โปรเจกต์นี้ไม่มีการโหลด
.env อัตโนมัติ — ไฟล์ .env ที่มีอยู่ใน repo root ใช้สำหรับ NOTION_API_TOKEN ของ
kanban tooling เท่านั้น ไม่เกี่ยวกับ script นี้)

`/say` เป็น application slash command ไม่ต้องเปิด privileged "Message Content Intent"
ใน Developer Portal อีกต่อไป แต่ invite URL ของบอทต้องมี scope `applications.commands`
ไม่งั้น command จะไม่ถูก register

Env vars:
    DISCORD_BOT_TOKEN     (required, secret) Discord bot token — ห้าม hardcode
    DISCORD_GUILD_ID      (optional) ถ้าตั้ง = register /say เฉพาะ guild นี้ (เห็นทันที);
                          ไม่ตั้ง = global registration (ครั้งแรกรอ propagate ได้ถึง ~1 ชม.)
    VC_IDLE_TIMEOUT_S     (default 60) วินาทีที่รอก่อนออกจาก VC หลังคิวเล่นเสียงว่าง
    SAY_SENTENCE_GAP_S   (default 1) วินาทีเว้นเงียบหลังจบแต่ละประโยค — ทั้งตอนเล่นใน VC
                          และตอน export_tts (concat เติม silence ท้ายทุกบรรทัด). 0 = ปิด;
                          ค่าอื่นถูกบังคับขั้นต่ำ 0.5s ตอน export กันคำท้ายประโยคโดนตัด
    TRANSCRIBE_WHISPER_MODEL  (default mlx-community/whisper-large-v3-turbo) โมเดล Whisper
                          ที่ /transcribe ใช้ถอดเสียง — โหลดครั้งแรก ~1.6 GB ลง HF cache
"""
import asyncio
import io
import json
import os
import sys
import tempfile
import time

import discord
from discord import app_commands

PROJ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJ)

# reuse ของเดิมจาก qwen_clone_tts.py ทั้งหมด — ห้าม duplicate ค่า/logic
from qwen_clone_tts import LANG_CODES, MAX_CHARS, MOOD_PRESETS, _try_daemon, resolve_instruct  # noqa: E402
from say_moods import MOOD_EMOJI, extract_mood, first_line_over_limit, parse_lines  # noqa: E402
from stt_transcribe import WHISPER_MODEL, probe_duration, transcribe as run_stt  # noqa: E402
from transcribe_mood import detect_mood  # noqa: E402
import voice_store  # noqa: E402
from voice_store import VoiceStoreError  # noqa: E402

DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
DISCORD_GUILD_ID = os.environ.get("DISCORD_GUILD_ID")
VC_IDLE_TIMEOUT_S = float(os.environ.get("VC_IDLE_TIMEOUT_S", "60"))
SAY_SENTENCE_GAP_S = float(os.environ.get("SAY_SENTENCE_GAP_S", "1"))

# /transcribe limits (TTS-1005)
TRANSCRIBE_MAX_BYTES = 20 * 1024 * 1024
TRANSCRIBE_MAX_DURATION_S = 600
TRANSCRIBE_INLINE_MAX = 1800  # ยาวกว่านี้ -> ส่งเฉพาะไฟล์แนบ ไม่ preview ในแชท

# /translate limits — transcript.json เป็น text ล้วน ไม่มีทางใหญ่เท่าไฟล์เสียง
TRANSLATE_MAX_BYTES = 1024 * 1024
TRANSLATE_TARGETS = ("en", "th")
# MyMemoryTranslator (deep_translator) ต้อง locale-qualified code เสมอ ไม่รับ
# "auto" เป็น source (ต่างจาก GoogleTranslator) — ต้องรู้ source language ชัดเจน
TRANSLATE_LOCALE = {"ja": "ja-JP", "en": "en-GB", "th": "th-TH"}

# /voice-clone limits (TTS-1009)
VOICE_CLONE_MAX_BYTES = 25 * 1024 * 1024
VOICE_CLONE_EXTS = (".mp3", ".wav", ".m4a", ".ogg")
VOICE_CLONE_TEST_TEXT = "สวัสดีค่ะ นี่คือตัวอย่างเสียงพูดจากเสียงโคลนนี้"

# /voice-design — โมเดล VoiceDesign (instruct = คำบรรยายเสียงเป็น text แทน ref audio)
# โหลดใน process ของบอทเองแบบ lazy singleton (ADR-0001) ไม่ยัดเข้า tts_daemon
VOICE_DESIGN_MODEL_PATH = os.path.join(
    PROJ, "models", "Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit")

# slash command ไม่ต้องอ่านเนื้อความ -> ใช้ default intents (มี voice_states ที่ต้องใช้
# อ่าน interaction.user.voice อยู่แล้ว) ห้ามเปิด message_content
intents = discord.Intents.default()

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


class GuildPlayback:
    """คิวเล่นเสียงใน VC ต่อ guild (แยกจากคิว generate ของ tts_daemon)

    worker task เล่นทีละไฟล์ผ่าน discord.FFmpegPCMAudio แล้วรอ `after` callback
    ก่อนเล่นตัวถัดไป — กันไม่ให้คำสั่งซ้อนกันเล่นทับกัน (AC: เล่นเรียงคิว)
    หลังคิวว่างและเล่นจบ เริ่ม countdown VC_IDLE_TIMEOUT_S แล้วค่อยออกจากห้อง
    ถ้ามีงานใหม่เข้าคิวก่อนครบเวลาจะ cancel countdown อัตโนมัติ
    """

    def __init__(self, guild: discord.Guild):
        self.guild = guild
        self.queue: "asyncio.Queue[tuple[discord.VoiceChannel, discord.abc.Messageable, str]]" = asyncio.Queue()
        self.worker_task: asyncio.Task | None = None
        self.idle_task: asyncio.Task | None = None

    def ensure_worker(self) -> None:
        if self.worker_task is None or self.worker_task.done():
            self.worker_task = asyncio.create_task(self._worker())

    def _cancel_idle(self) -> None:
        if self.idle_task is not None and not self.idle_task.done():
            self.idle_task.cancel()
        self.idle_task = None

    def _schedule_idle_leave(self, voice_client: discord.VoiceClient) -> None:
        self._cancel_idle()
        self.idle_task = asyncio.create_task(self._idle_leave(voice_client))

    async def _idle_leave(self, voice_client: discord.VoiceClient) -> None:
        try:
            await asyncio.sleep(VC_IDLE_TIMEOUT_S)
        except asyncio.CancelledError:
            return
        if voice_client.is_connected() and not voice_client.is_playing() \
                and self.queue.empty():
            await voice_client.disconnect()

    async def _worker(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            voice_channel, reply_to, wav_path = await self.queue.get()
            self._cancel_idle()
            try:
                voice_client = self.guild.voice_client
                if voice_client is None:
                    voice_client = await voice_channel.connect()
                elif voice_client.channel.id != voice_channel.id:
                    await voice_client.move_to(voice_channel)

                done = asyncio.Event()

                def _after(error: Exception | None) -> None:
                    if error is not None:
                        print(f"discord_say_bot: playback error: {error}",
                              file=sys.stderr, flush=True)
                    loop.call_soon_threadsafe(done.set)

                source = discord.FFmpegPCMAudio(wav_path)
                voice_client.play(source, after=_after)
                await done.wait()
                # เว้นเงียบสั้น ๆ หลังจบประโยค ก่อนเล่นบรรทัดถัดไป (TTS-1002)
                if SAY_SENTENCE_GAP_S > 0:
                    await asyncio.sleep(SAY_SENTENCE_GAP_S)
            except Exception as e:  # noqa: BLE001
                print(f"discord_say_bot: worker error: {e}", file=sys.stderr,
                      flush=True)
                try:
                    await reply_to.send(f"⚠️ เล่นเสียงไม่สำเร็จ: {e}")
                except discord.DiscordException:
                    pass
            finally:
                try:
                    os.remove(wav_path)
                except OSError:
                    pass
                self.queue.task_done()
                voice_client = self.guild.voice_client
                if self.queue.empty() and voice_client is not None:
                    self._schedule_idle_leave(voice_client)


_playback: dict[int, GuildPlayback] = {}


def _get_playback(guild: discord.Guild) -> GuildPlayback:
    pb = _playback.get(guild.id)
    if pb is None:
        pb = GuildPlayback(guild)
        _playback[guild.id] = pb
    return pb


@client.event
async def on_ready() -> None:
    try:
        if DISCORD_GUILD_ID:
            guild = discord.Object(id=int(DISCORD_GUILD_ID))
            tree.copy_global_to(guild=guild)
            synced = await tree.sync(guild=guild)
        else:
            synced = await tree.sync()
        print(f"discord_say_bot: logged in as {client.user} "
              f"(slash cmds synced={len(synced)}, "
              f"guild={DISCORD_GUILD_ID or 'global'}, "
              f"idle_timeout={VC_IDLE_TIMEOUT_S:.0f}s)",
              file=sys.stderr, flush=True)
    except Exception as e:
        # sync ล้ม (timeout/rate-limit ฝั่ง Discord) ไม่ควร crash บอท —
        # คำสั่งเก่าที่ sync ไว้รอบก่อนยังใช้งานได้ปกติ
        print(f"discord_say_bot: slash cmd sync failed ({e!r}), "
              f"logged in as {client.user} anyway",
              file=sys.stderr, flush=True)


async def _voice_autocomplete(
        interaction: discord.Interaction,
        current: str) -> list[app_commands.Choice[str]]:
    """dynamic autocomplete แทน static Choice list — กันเกิน 25 รายการ (Discord
    limit) เมื่อมีเสียงเยอะ; filter ด้วย substring ของ current"""
    current = (current or "").strip().lower()
    names = [v["name"] for v in voice_store.list_voices()]
    matched = [n for n in names if current in n][:25]
    return [app_commands.Choice(name=n, value=n) for n in matched]


async def _mood_autocomplete(
        interaction: discord.Interaction,
        current: str) -> list[app_commands.Choice[str]]:
    """dynamic autocomplete แทน static Choice list — MOOD_PRESETS เกิน 25 รายการ
    (Discord limit) แล้ว; filter ด้วย substring ของ current"""
    current = (current or "").strip().lower()
    matched = [m for m in sorted(MOOD_PRESETS) if current in m][:25]
    return [app_commands.Choice(name=m, value=m) for m in matched]


class DeleteMessageView(discord.ui.View):
    """ปุ่ม "ลบข้อความ" แนบมากับ message ที่มีไฟล์แนบ (/say export_tts, /transcribe) —
    ให้คนที่สั่งคำสั่งกดลบเองได้หลังโหลดไฟล์เสร็จ โดยไม่ต้องรอ mod ลบให้"""

    def __init__(self, author_id: int, *, timeout: float | None = 600) -> None:
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "ลบได้เฉพาะคนที่สั่งคำสั่งนี้เท่านั้น", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        if self.message is not None:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="ลบข้อความ", emoji="🗑️",
                        style=discord.ButtonStyle.danger)
    async def delete(self, interaction: discord.Interaction,
                      button: discord.ui.Button) -> None:
        await interaction.message.delete()


class ExportError(Exception):
    """ffmpeg ไม่มี/ล้มเหลวตอนต่อ wav — ผู้เรียก catch เอง ข้อความ (str(e)) พร้อมส่ง
    followup ตรงๆ ได้เลย (ไม่มี prefix ⚠️ ผู้เรียกเป็นคนเติม)"""


async def _concat_wavs(wav_paths: list[str], gap_s: float) -> tuple[str, str | None]:
    """ต่อ wav หลายไฟล์เป็นไฟล์เดียวด้วย ffmpeg + เติมช่องเงียบ gap_s ท้ายทุกไฟล์
    (กันคำท้ายประโยคโดนตัดตอน concat) คืน (export_path, tmpdir) — tmpdir=None ถ้า
    ไม่ได้สร้าง (กรณีไฟล์เดียว + ไม่มี gap คืน wav_paths[0] ตรงๆ) ผู้เรียกต้อง
    shutil.rmtree(tmpdir) เองหลังใช้ export_path เสร็จ ถ้า tmpdir ไม่ None"""
    need_ffmpeg = len(wav_paths) > 1 or gap_s > 0
    if not need_ffmpeg:
        return wav_paths[0], None

    import shutil
    import subprocess
    if shutil.which("ffmpeg") is None:
        raise ExportError("ต้องมี ffmpeg เพื่อรวมไฟล์/เติมช่องเงียบท้ายประโยค")

    tmpdir = tempfile.mkdtemp(prefix="qwen_export_")
    silence_path = None
    if gap_s > 0:
        silence_path = os.path.join(tmpdir, "gap.wav")
        sr = await asyncio.to_thread(
            subprocess.run,
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
             "-t", f"{gap_s}", "-c:a", "pcm_s16le", silence_path],
            capture_output=True, text=True)
        if sr.returncode != 0 or not os.path.exists(silence_path):
            shutil.rmtree(tmpdir, ignore_errors=True)
            raise ExportError(f"สร้างช่องเงียบไม่สำเร็จ: {sr.stderr}")

    list_file = os.path.join(tmpdir, "list.txt")
    with open(list_file, "w", encoding="utf-8") as f:
        for p in wav_paths:
            f.write(f"file '{p}'\n")
            if silence_path is not None:
                f.write(f"file '{silence_path}'\n")
    export_path = os.path.join(tmpdir, "export.wav")
    r = await asyncio.to_thread(
        subprocess.run,
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "concat", "-safe", "0", "-i", list_file,
         "-ar", "24000", "-ac", "1", export_path],
        capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(export_path):
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise ExportError(f"รวมไฟล์เสียงไม่สำเร็จ: {r.stderr}")
    return export_path, tmpdir


async def _build_transcript(wav_paths: list[str], texts: list[str], gap_s: float,
                            moods: list[str | None] | None = None) -> list[dict]:
    """สร้าง transcript entries [{id, text, start, end, mood?}] จากความยาว wav
    จริงต่อบรรทัด (ffprobe) ไม่ใช้ STT — ข้อความรู้อยู่แล้วจากที่ส่งเข้า TTS (index
    ตรงกับ wav_paths) เหมือน hyperframes transcribe schema

    `moods[idx]` ใส่คีย์ "mood" ต่อ entry เฉพาะตัวที่ไม่ใช่ None — mood field เป็น
    optional เสมอ (ทั้ง /transcribe และ /translate อ่านมันแบบ entry.get("mood"))
    เพื่อให้ round-trip ผ่าน /transcribe -> /say -> /translate เก็บโทนเสียงไว้ได้"""
    durations = [await asyncio.to_thread(probe_duration, p) for p in wav_paths]
    entries = []
    t = 0.0
    for idx, text in enumerate(texts):
        d = durations[idx]
        entry = {"id": f"w{idx}", "text": text,
                 "start": round(t, 3), "end": round(t + d, 3)}
        if moods is not None and moods[idx] is not None:
            entry["mood"] = moods[idx]
        entries.append(entry)
        t += d + gap_s
    return entries


def _translate_batch(texts: list[str], source: str, target: str) -> list[str]:
    """แปลหลายบรรทัดผ่าน MyMemory (deep_translator, ไม่ใช้ API key) — เลือกใช้ตัวนี้
    แทน GoogleTranslator เพราะ Google เว็บฟรี (translate.google.com/translate_a)
    บล็อก IP ง่ายมาก (bot-detection "unusual traffic") เจอจริงทั้ง dev sandbox และ
    เครื่องจริงของผู้ใช้ — ตอบ error page เป็น "ข้อความแปล" เฉยๆ ไม่ raise เอง

    MyMemory ไม่รับ source="auto" (ต้องรู้ภาษาต้นทางชัดเจน ผ่าน TRANSLATE_LOCALE)
    และไม่มี API key ให้ยิงเยอะ (quota free ~5000 ตัวอักษร/วันต่อ IP) — เช็ค marker
    string ของ error response (มาเป็น text ปกติเหมือน Google ไม่ raise เอง) กัน
    หลุดไปเข้า TTS เป็นเสียงอ่าน error message ให้ผู้ใช้แทน"""
    from deep_translator import MyMemoryTranslator
    result = MyMemoryTranslator(
        source=TRANSLATE_LOCALE[source], target=TRANSLATE_LOCALE[target],
    ).translate_batch(texts)
    for text in result:
        if not text or "INVALID SOURCE LANGUAGE" in text.upper() or \
                "INVALID TARGET LANGUAGE" in text.upper() or \
                "QUERY LENGTH LIMIT" in text.upper() or \
                "MYMEMORY WARNING" in text.upper():
            raise RuntimeError(
                f"MyMemory ปฏิเสธคำขอ: {text} — ลองใหม่อีกครั้งในอีกสักพัก "
                "(quota ฟรี ~5000 ตัวอักษร/วัน อาจเต็ม)")
    return result


@tree.command(name="say",
              description="ให้บอทพูดข้อความใน voice channel ด้วยเสียงโคลน")
@app_commands.guild_only()
@app_commands.describe(
    text="ข้อความบรรทัดเดียว (หลายบรรทัดให้ใช้ file:)",
    mood="โทนเสียง (ไม่เลือก = auto จาก emoji หรือปกติ)",
    language="ภาษาที่โมเดลออกเสียง (ไม่เลือก = auto เดาจากข้อความ; ไทยใช้ auto)",
    file="ไฟล์ .txt สำหรับข้อความหลายบรรทัด (1 บรรทัด = 1 ประโยค, UTF-8, ≤100 KB)",
    voice="เสียงที่จะใช้ (ไม่เลือก = default voice ที่ตั้งไว้ผ่าน /voice-clone set-default)",
    export_tts="ส่งออกเป็นไฟล์เสียง .wav แนบในแชทแทนการเล่นใน voice channel "
                "(ไม่ต้องเข้า VC)",
    is_transcript="แนบ transcript.json (start/end ต่อบรรทัด คำนวณจากความยาว wav จริง "
                  "แบบ hyperframes transcribe) คู่กับไฟล์เสียง — ต้องใช้กับ export_tts:true",
    save_local="นอกจากแนบในแชท ให้ copy ไฟล์เสียงเก็บไว้ที่ outputs/say/ ในโปรเจกต์ด้วย "
               "— ต้องใช้กับ export_tts:true")
@app_commands.choices(
    language=[app_commands.Choice(name=c, value=c)
              for c in LANG_CODES if c != "auto"])
@app_commands.autocomplete(voice=_voice_autocomplete, mood=_mood_autocomplete)
async def say(interaction: discord.Interaction, text: str | None = None,
              mood: str | None = None,
              language: str | None = None,
              file: discord.Attachment | None = None,
              voice: str | None = None,
              export_tts: bool = False,
              is_transcript: bool = False,
              save_local: bool = False) -> None:
    explicit_mood = mood  # ชื่อ preset ที่เลือกจาก dropdown หรือ None
    lang = language or "auto"  # ไม่เลือก = auto (choice list ไม่มี auto)

    # ต้องระบุ text หรือ file อย่างใดอย่างหนึ่ง (XOR) — เช็คก่อน defer
    if (text is None) == (file is None):
        await interaction.response.send_message(
            "ใช้: `/say text:<ข้อความ>` (บรรทัดเดียว) หรือ `/say file:<x.txt>` "
            "(หลายบรรทัด) — เลือกอย่างใดอย่างหนึ่ง", ephemeral=True)
        return

    if is_transcript and not export_tts:
        await interaction.response.send_message(
            "`is_transcript:true` ต้องใช้คู่กับ `export_tts:true` — transcript.json "
            "ถอดจากไฟล์เสียงที่ export เท่านั้น", ephemeral=True)
        return

    if save_local and not export_tts:
        await interaction.response.send_message(
            "`save_local:true` ต้องใช้คู่กับ `export_tts:true` — save ไฟล์ที่ export "
            "ลงเครื่องเท่านั้น", ephemeral=True)
        return

    # เลือกเสียง: ระบุ voice: ต้องมีอยู่จริง, ไม่ระบุ = default voice ปัจจุบัน
    if voice is not None:
        try:
            voice_clean = voice_store.sanitize_name(voice)
        except VoiceStoreError as e:
            await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
            return
        if not voice_store.voice_exists(voice_clean):
            await interaction.response.send_message(
                f"⚠️ ไม่พบเสียง `{voice_clean}`", ephemeral=True)
            return
    else:
        voice_clean = voice_store.get_default_voice()
    voice_instruct = voice_store.read_instruction(voice_clean)

    if file is not None:
        # type/size เช็คได้ก่อน download; .txt = content_type ขึ้นต้น text/ หรือ
        # filename ลงท้าย .txt (Discord ส่ง content_type เป็น None ได้สำหรับ .txt)
        name_ok = file.filename.lower().endswith(".txt")
        type_ok = (file.content_type or "").startswith("text/")
        if not (name_ok or type_ok):
            await interaction.response.send_message(
                "ไฟล์ต้องเป็น `.txt` (UTF-8 text)", ephemeral=True)
            return
        if file.size > 100_000:
            await interaction.response.send_message(
                "ไฟล์ใหญ่เกิน 100 KB", ephemeral=True)
            return
        # ไฟล์ ≤100 KB จาก Discord CDN โหลดเร็ว -> read + decode ก่อน defer ได้
        # (error ทุกจุดตอนนี้ยังเป็น response.send_message เหมือน path อื่น)
        try:
            raw = await file.read()
        except discord.DiscordException as e:  # noqa: BLE001
            await interaction.response.send_message(
                f"อ่านไฟล์ไม่สำเร็จ: {e}", ephemeral=True)
            return
        try:
            source_text = raw.decode("utf-8-sig")  # -sig = กิน BOM ถ้ามี
        except UnicodeDecodeError:
            await interaction.response.send_message(
                "ไฟล์ต้องเป็น UTF-8 text", ephemeral=True)
            return
        src = "file"
    else:
        source_text = text
        src = "text"

    lines = parse_lines(source_text)
    if not lines:
        await interaction.response.send_message(
            f"ไม่มีข้อความให้พูด — ใช้ `/say text:<ข้อความ>` หรือ `/say file:<x.txt>` "
            f"(1 บรรทัด = 1 ประโยค ไม่เกิน {MAX_CHARS} ตัวอักษรต่อบรรทัด)",
            ephemeral=True)
        return

    # (spoken_text, mood ที่จะใช้จริง) ต่อบรรทัด — explicit mood ชนะ emoji เสมอ
    prepared: list[tuple[str, str | None]] = []
    for line in lines:
        spoken, auto_mood = extract_mood(line)
        if not spoken:
            continue  # บรรทัดที่เหลือแต่ emoji/ว่าง -> ข้าม
        prepared.append((spoken, explicit_mood or auto_mood))
    if not prepared:
        await interaction.response.send_message(
            "ไม่มีข้อความให้พูด (บรรทัดว่าง/มีแต่ emoji ทั้งหมด)", ephemeral=True)
        return

    # เช็คลิมิต per-line (TTS-1003): แต่ละบรรทัด (หลังตัด emoji/trim) ≤ MAX_CHARS
    # ไม่จำกัดจำนวนบรรทัดและไม่รวมความยาวทุกบรรทัด — daemon reject ที่ MAX_CHARS
    # ต่อ request อยู่แล้ว บรรทัดใดเกิน -> reject ทั้ง batch ระบุเลขบรรทัด
    over = first_line_over_limit((spoken for spoken, _ in prepared), MAX_CHARS)
    if over is not None:
        line_no, line_len = over
        await interaction.response.send_message(
            f"⚠️ บรรทัดที่ {line_no} ยาวเกินไป ({line_len} ตัวอักษร หลังตัด emoji) "
            f"— จำกัดไม่เกิน {MAX_CHARS} ตัวอักษรต่อบรรทัด", ephemeral=True)
        return
    total_chars = sum(len(spoken) for spoken, _ in prepared)

    # resolve instruct ทุกบรรทัดก่อน (mood ผิด -> reject ทั้ง batch; ปกติ dropdown
    # จะเลือกผิดไม่ได้ แต่กันไว้เผื่อ client ส่งค่านอก choices มา)
    jobs_meta: list[tuple[str, str | None, str | None]] = []  # (spoken, mood, instruct)
    for spoken, m in prepared:
        try:
            instruct = resolve_instruct(m, None, voice_instruct)
        except ValueError as e:
            await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
            return
        jobs_meta.append((spoken, m, instruct))

    voice_channel = None
    if not export_tts:
        author_voice = getattr(interaction.user, "voice", None)
        if author_voice is None or author_voice.channel is None:
            await interaction.response.send_message(
                "ต้องเข้า voice channel ก่อนถึงจะใช้คำสั่งนี้ได้ "
                "(หรือใช้ `export_tts:true` เพื่อส่งออกเป็นไฟล์แทน)", ephemeral=True)
            return
        voice_channel = author_voice.channel

    # ผ่าน validation หมดแล้ว — gen ช้ากว่า 3 วิ ต้อง defer ก่อน (spinner เห็นเฉพาะคนสั่ง)
    await interaction.response.defer(ephemeral=True, thinking=True)

    # generate ครบทุกบรรทัดก่อน queue — บรรทัดใด fail -> ลบไฟล์ทั้ง batch, ไม่ queue
    t0 = time.time()
    wav_paths: list[str] = []
    for idx, (spoken, _mood, instruct) in enumerate(jobs_meta):
        wav_path = os.path.join(
            tempfile.gettempdir(),
            f"qwen_say_{os.getpid()}_{int(time.time()*1000)}_{idx}.wav")
        ok = await asyncio.to_thread(
            _try_daemon, spoken, wav_path, instruct, voice_clean, "wav", lang)
        if not ok:
            for p in wav_paths:
                try:
                    os.remove(p)
                except OSError:
                    pass
            try:
                os.remove(wav_path)
            except OSError:
                pass
            # Decision (ดู TTS-1001 plan): daemon ล่ม/ตอบ error -> แจ้งทันที
            # ไม่ fallback ไปโหลดโมเดลเองในบอท; batch เป็น atomic
            await interaction.followup.send(
                "⚠️ TTS daemon ไม่พร้อมใช้งาน (ล่ม/ยังไม่ได้รัน หรือสร้างเสียงไม่สำเร็จ) "
                "— ไม่มีบรรทัดไหนถูกเล่น ตรวจ log ของบอท แล้วลองสตาร์ท `tts_daemon.py` ใหม่",
                ephemeral=True)
            return
        wav_paths.append(wav_path)
    gen_s = time.time() - t0

    if export_tts:
        # ช่องเงียบท้ายทุกประโยค (เหมือน playback ที่ sleep SAY_SENTENCE_GAP_S)
        # กัน ffmpeg concat ต่อไฟล์ชนกันจนคำท้ายประโยคฟังเหมือนโดนตัดหาย
        # 0 = ปิดชัดเจน; ไม่งั้นบังคับขั้นต่ำ 0.5s เสมอ กันคำท้ายประโยคหาย
        gap_s = max(SAY_SENTENCE_GAP_S, 0.5) if SAY_SENTENCE_GAP_S > 0 else 0.0
        try:
            export_path, tmpdir = await _concat_wavs(wav_paths, gap_s)
        except ExportError as e:
            for p in wav_paths:
                try:
                    os.remove(p)
                except OSError:
                    pass
            await interaction.followup.send(f"⚠️ {e}", ephemeral=True)
            return

        transcript_path = None
        if is_transcript:
            try:
                entries = await _build_transcript(
                    wav_paths, [spoken for spoken, _mood, _instruct in jobs_meta],
                    gap_s, [m for _spoken, m, _instruct in jobs_meta])
                transcript_path = f"{export_path}.transcript.json"
                with open(transcript_path, "w", encoding="utf-8") as f:
                    json.dump(entries, f, ensure_ascii=False, indent=2)
            except Exception as e:  # noqa: BLE001 — ffprobe ล้มเหลว ไม่ทำให้ export เสียงพัง
                transcript_path = None
                await interaction.followup.send(
                    f"⚠️ สร้าง transcript.json ไม่สำเร็จ ({e}) — ส่งเฉพาะไฟล์เสียง",
                    ephemeral=True)

        saved_path = None
        if save_local:
            # copy ก่อนถึง finally ด้านล่างที่ลบ export_path/transcript_path ทิ้ง —
            # ไม่ move เพราะยังต้องใช้ export_path ส่งแนบแชทต่อ
            try:
                import shutil as _shutil_local
                save_dir = os.path.join(PROJ, "outputs", "say")
                os.makedirs(save_dir, exist_ok=True)
                stamp = time.strftime("%Y%m%d_%H%M%S")
                saved_path = os.path.join(save_dir, f"{stamp}_{interaction.guild.id}.wav")
                _shutil_local.copy2(export_path, saved_path)
                if transcript_path is not None:
                    _shutil_local.copy2(transcript_path, f"{saved_path}.transcript.json")
                print(f"discord_say_bot: save_local ok guild={interaction.guild.id} "
                      f"saved_path={saved_path}", file=sys.stderr, flush=True)
            except OSError as e:
                saved_path = None
                print(f"discord_say_bot: save_local error guild={interaction.guild.id} "
                      f"err={e}", file=sys.stderr, flush=True)
                await interaction.followup.send(
                    f"⚠️ save_local ไม่สำเร็จ ({e}) — ยังส่งไฟล์เสียงในแชทตามปกติ",
                    ephemeral=True)

        try:
            files = [discord.File(export_path, filename="narration.wav")]
            if transcript_path is not None:
                files.append(discord.File(transcript_path, filename="transcript.json"))
            view = DeleteMessageView(interaction.user.id)
            sent_msg = await interaction.channel.send(
                f"🔊 ส่งออกเสียงแล้ว ({len(wav_paths)} บรรทัด)", files=files,
                view=view)
            view.message = sent_msg
        finally:
            for p in wav_paths:
                try:
                    os.remove(p)
                except OSError:
                    pass
            if transcript_path is not None:
                try:
                    os.remove(transcript_path)
                except OSError:
                    pass
            if tmpdir is not None:
                import shutil as _shutil
                _shutil.rmtree(tmpdir, ignore_errors=True)

        ok_msg = "✅ ส่งออกไฟล์เสียงแล้ว"
        if saved_path is not None:
            ok_msg += f" (บันทึกไว้ที่ `{os.path.relpath(saved_path, PROJ)}`)"
        await interaction.followup.send(ok_msg, ephemeral=True)
        print(f"discord_say_bot: exported say guild={interaction.guild.id} "
              f"src={src} lines={len(wav_paths)} gen_s={gen_s:.2f} "
              f"explicit_mood={explicit_mood} lang={lang} chars={total_chars} "
              f"voice={voice_clean} is_transcript={is_transcript} "
              f"save_local={save_local} saved_path={saved_path}",
              file=sys.stderr, flush=True)
        return

    playback = _get_playback(interaction.guild)
    playback.ensure_worker()
    for wav_path in wav_paths:
        await playback.queue.put((voice_channel, interaction.channel, wav_path))

    # success: แจ้ง channel ปกติ + เคลียร์ spinner ephemeral ของคนสั่ง
    await interaction.channel.send(f"🔊 เข้าคิวแล้ว {len(wav_paths)} บรรทัด")
    await interaction.followup.send("✅ เข้าคิวแล้ว", ephemeral=True)
    print(f"discord_say_bot: queued say guild={interaction.guild.id} "
          f"src={src} lines={len(wav_paths)} gen_s={gen_s:.2f} "
          f"explicit_mood={explicit_mood} lang={lang} chars={total_chars} "
          f"voice={voice_clean}",
          file=sys.stderr, flush=True)


@tree.command(
    name="transcribe",
    description="ถอดเสียงไฟล์เสียงเป็นข้อความ + emoji mood พร้อมใช้กับ /say")
@app_commands.guild_only()
@app_commands.describe(
    file="ไฟล์เสียง .mp3 หรือ .wav (≤ 20 MB, ≤ 10 นาที)",
    mood="บังคับ mood ทุกบรรทัด (ไม่เลือก = auto จากข้อความ)",
    language="ภาษาของเสียง (ไม่เลือก = ตรวจอัตโนมัติ, ใช้ภาษาเดียวทั้งไฟล์)")
@app_commands.choices(
    language=[
        app_commands.Choice(name="ไทย", value="th"),
        app_commands.Choice(name="ญี่ปุ่น", value="ja"),
        app_commands.Choice(name="อังกฤษ", value="en"),
    ])
@app_commands.autocomplete(mood=_mood_autocomplete)
async def transcribe(interaction: discord.Interaction,
                     file: discord.Attachment,
                     mood: str | None = None,
                     language: str | None = None) -> None:
    # pre-defer validation — error ทุกจุดตรงนี้เป็น ephemeral, ไม่โพสต์ลงแชท
    if not file.filename.lower().endswith((".mp3", ".wav")):
        await interaction.response.send_message(
            "ไฟล์ต้องเป็น `.mp3` หรือ `.wav`", ephemeral=True)
        return
    if file.size > TRANSCRIBE_MAX_BYTES:
        await interaction.response.send_message(
            "ไฟล์ใหญ่เกิน 20 MB", ephemeral=True)
        return

    # STT ช้ากว่า 3 วิแน่ -> defer ก่อน (spinner เห็นเฉพาะคนสั่ง)
    await interaction.response.defer(ephemeral=True, thinking=True)

    ext = ".mp3" if file.filename.lower().endswith(".mp3") else ".wav"
    audio_path = os.path.join(
        tempfile.gettempdir(),
        f"qwen_transcribe_{os.getpid()}_{int(time.time()*1000)}{ext}")
    try:
        try:
            await file.save(audio_path)
        except discord.DiscordException as e:  # noqa: BLE001
            await interaction.followup.send(
                f"ดาวน์โหลดไฟล์ไม่สำเร็จ: {e}", ephemeral=True)
            return

        try:
            duration = await asyncio.to_thread(probe_duration, audio_path)
        except RuntimeError as e:
            print(f"discord_say_bot: transcribe probe error: {e}",
                  file=sys.stderr, flush=True)
            await interaction.followup.send(
                "อ่านไฟล์เสียงไม่สำเร็จ (ไฟล์เสียหายหรือไม่ใช่ไฟล์เสียง)",
                ephemeral=True)
            return
        if duration > TRANSCRIBE_MAX_DURATION_S:
            await interaction.followup.send(
                f"เสียงยาวเกิน 10 นาที ({duration / 60:.1f} นาที)",
                ephemeral=True)
            return

        t0 = time.time()
        try:
            segments = await asyncio.to_thread(run_stt, audio_path, language)
        except Exception as e:  # noqa: BLE001
            print(f"discord_say_bot: transcribe STT error: {e}",
                  file=sys.stderr, flush=True)
            await interaction.followup.send(
                f"ถอดเสียงไม่สำเร็จ: {e}", ephemeral=True)
            return
        stt_s = time.time() - t0

        if not segments:
            await interaction.followup.send(
                "ถอดเสียงไม่พบข้อความ (เสียงเงียบหรือไม่มีคำพูด)",
                ephemeral=True)
            return

        composed: list[str] = []
        transcript_entries: list[dict] = []
        for idx, seg in enumerate(segments):
            text = seg["text"]
            m = mood or detect_mood(text)
            prefix = f"{MOOD_EMOJI[m]} " if m in MOOD_EMOJI else ""
            composed.append(f"{prefix}{text}")
            entry = {"id": f"w{idx}", "text": text,
                      "start": seg["start"], "end": seg["end"]}
            if m is not None:
                # เก็บ mood ที่ตรวจ/บังคับได้ไว้ใน transcript.json ด้วย (ตรงกับ
                # MOOD_PRESETS เสมอ — detect_mood คืนแต่ key ที่รู้จัก) ให้ /say
                # กับ /translate อ่านต่อได้ทันทีโดยไม่ต้อง detect ซ้ำ
                entry["mood"] = m
            transcript_entries.append(entry)
        body = "\n".join(composed)

        txt = discord.File(
            io.BytesIO(body.encode("utf-8")),
            filename=f"transcribe_{interaction.id}.txt")
        transcript_json = discord.File(
            io.BytesIO(json.dumps(transcript_entries, ensure_ascii=False,
                                   indent=2).encode("utf-8")),
            filename="transcript.json")
        no_ping = discord.AllowedMentions.none()
        # แทรก zero-width space กัน ``` ในเนื้อความทะลุ code fence (ไฟล์แนบใช้ body เดิม);
        # allowed_mentions=none กัน @mention จาก transcript
        safe_body = body.replace("```", "`​`​`")
        view = DeleteMessageView(interaction.user.id)
        if len(body) <= TRANSCRIBE_INLINE_MAX:
            sent_msg = await interaction.channel.send(
                f"```\n{safe_body}\n```", files=[txt, transcript_json],
                allowed_mentions=no_ping, view=view)
        else:
            sent_msg = await interaction.channel.send(
                "📝 ถอดเสียงเสร็จแล้ว (ข้อความยาว — ดูไฟล์แนบ)",
                files=[txt, transcript_json], allowed_mentions=no_ping,
                view=view)
        view.message = sent_msg
        await interaction.followup.send("✅ เสร็จแล้ว", ephemeral=True)
        print(f"discord_say_bot: transcribe guild={interaction.guild.id} "
              f"bytes={file.size} dur_s={duration:.1f} lines={len(segments)} "
              f"stt_s={stt_s:.2f} model={WHISPER_MODEL} lang={language or 'auto'} "
              f"explicit_mood={mood}",
              file=sys.stderr, flush=True)
    finally:
        try:
            os.remove(audio_path)
        except OSError:
            pass


@tree.command(
    name="translate",
    description="แปล transcript.json (จาก /transcribe) เป็นภาษาอื่น แล้ว gen เสียงเลย")
@app_commands.guild_only()
@app_commands.describe(
    file="transcript.json จาก /transcribe (JSON array [{id, text, start, end}])",
    source="ภาษาต้นทางของ transcript.json (MyMemory ต้องรู้ชัดเจน เดาไม่ได้)",
    target="ภาษาปลายทางที่จะแปลเป็น",
    mood="mood เริ่มต้นของทุกบรรทัด — ถ้า entry ใน transcript.json มี `mood` field "
         "เอง จะใช้ของ entry นั้นแทน (ไม่เลือกทั้งคู่ = เสียงปกติของ voice)",
    voice="เสียงที่จะใช้ (ไม่เลือก = default voice ที่ตั้งไว้ผ่าน /voice-clone set-default)",
    save_local="นอกจากแนบในแชท ให้ copy ไฟล์เสียง + transcript.json เก็บไว้ที่ "
               "outputs/translate/ ในโปรเจกต์ด้วย")
@app_commands.choices(
    source=[
        app_commands.Choice(name="ญี่ปุ่น", value="ja"),
        app_commands.Choice(name="อังกฤษ", value="en"),
        app_commands.Choice(name="ไทย", value="th"),
    ],
    target=[
        app_commands.Choice(name="อังกฤษ", value="en"),
        app_commands.Choice(name="ไทย", value="th"),
    ])
@app_commands.autocomplete(voice=_voice_autocomplete, mood=_mood_autocomplete)
async def translate(interaction: discord.Interaction,
                    file: discord.Attachment,
                    source: str,
                    target: str,
                    mood: str | None = None,
                    voice: str | None = None,
                    save_local: bool = False) -> None:
    # pre-defer validation — error ทุกจุดตรงนี้เป็น ephemeral, ไม่โพสต์ลงแชท
    if not file.filename.lower().endswith(".json"):
        await interaction.response.send_message(
            "ไฟล์ต้องเป็น `transcript.json` จาก `/transcribe`", ephemeral=True)
        return
    if file.size > TRANSLATE_MAX_BYTES:
        await interaction.response.send_message(
            "ไฟล์ใหญ่เกิน 1 MB", ephemeral=True)
        return

    if voice is not None:
        try:
            voice_clean = voice_store.sanitize_name(voice)
        except VoiceStoreError as e:
            await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
            return
        if not voice_store.voice_exists(voice_clean):
            await interaction.response.send_message(
                f"⚠️ ไม่พบเสียง `{voice_clean}`", ephemeral=True)
            return
    else:
        voice_clean = voice_store.get_default_voice()
    voice_instruct = voice_store.read_instruction(voice_clean)

    try:
        raw = await file.read()
    except discord.DiscordException as e:  # noqa: BLE001
        await interaction.response.send_message(
            f"ดาวน์โหลดไฟล์ไม่สำเร็จ: {e}", ephemeral=True)
        return
    try:
        entries = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        await interaction.response.send_message(
            f"ไฟล์ต้องเป็น transcript.json ที่ถูกต้อง (JSON, UTF-8): {e}",
            ephemeral=True)
        return
    if not isinstance(entries, list) or not entries or not all(
            isinstance(e, dict) and isinstance(e.get("text"), str) and e["text"]
            and (e.get("mood") is None or isinstance(e.get("mood"), str))
            for e in entries):
        await interaction.response.send_message(
            "รูปแบบไฟล์ไม่ตรง — ต้องเป็น JSON array ที่มี `text` ต่อบรรทัด "
            "(schema เดียวกับ transcript.json จาก /transcribe) `mood` ต่อ entry "
            "เป็น optional ถ้ามีต้องเป็น string", ephemeral=True)
        return
    source_texts = [e["text"] for e in entries]

    # mood ต่อ entry (จาก transcript.json) > mood param (บังคับทั้ง batch) >
    # default instruct ของ voice — resolve ก่อน defer เพราะเป็น local validation
    # ล้วน (ไม่ต้องรอ network); ผิดตัวไหน reject ทั้ง batch ระบุ entry นั้น
    instructs: list[str | None] = []
    entry_moods: list[str | None] = []
    for idx, e in enumerate(entries):
        entry_mood = e.get("mood") or mood
        try:
            instructs.append(resolve_instruct(entry_mood, None, voice_instruct))
        except ValueError as ex:
            await interaction.response.send_message(
                f"⚠️ entry ที่ {idx} (id={e.get('id', idx)}): {ex}", ephemeral=True)
            return
        entry_moods.append(entry_mood)

    # แปล + gen เสียงหลายบรรทัดช้ากว่า 3 วิแน่ -> defer ก่อน
    await interaction.response.defer(ephemeral=True, thinking=True)

    # LANG_CODES (qwen_clone_tts.py) ไม่มี "thai" — target:th ปล่อย auto ให้โมเดล
    # เดาจากตัวอักษรไทยในข้อความเอง (เหมือน /say ตอนพูดไทย)
    tts_lang = "english" if target == "en" else "auto"

    t0 = time.time()
    try:
        translated_texts = await asyncio.to_thread(
            _translate_batch, source_texts, source, target)
    except Exception as e:  # noqa: BLE001 — deep_translator เจอ network/quota/HTML
                             # error ของ MyMemory หลายแบบ ไม่มี exception class ตายตัว
        print(f"discord_say_bot: translate error: {e}", file=sys.stderr, flush=True)
        await interaction.followup.send(f"⚠️ แปลไม่สำเร็จ: {e}", ephemeral=True)
        return
    translate_s = time.time() - t0

    over = first_line_over_limit(translated_texts, MAX_CHARS)
    if over is not None:
        line_no, line_len = over
        await interaction.followup.send(
            f"⚠️ บรรทัดที่ {line_no} หลังแปลยาวเกินไป ({line_len} ตัวอักษร) "
            f"— จำกัดไม่เกิน {MAX_CHARS} ตัวอักษรต่อบรรทัด", ephemeral=True)
        return

    t0 = time.time()
    wav_paths: list[str] = []
    for idx, (spoken, instruct) in enumerate(zip(translated_texts, instructs)):
        wav_path = os.path.join(
            tempfile.gettempdir(),
            f"qwen_translate_{os.getpid()}_{int(time.time()*1000)}_{idx}.wav")
        ok = await asyncio.to_thread(
            _try_daemon, spoken, wav_path, instruct, voice_clean, "wav", tts_lang)
        if not ok:
            for p in wav_paths:
                try:
                    os.remove(p)
                except OSError:
                    pass
            try:
                os.remove(wav_path)
            except OSError:
                pass
            await interaction.followup.send(
                "⚠️ TTS daemon ไม่พร้อมใช้งาน (ล่ม/ยังไม่ได้รัน หรือสร้างเสียงไม่สำเร็จ) "
                "— ไม่มีบรรทัดไหนถูกสร้าง ตรวจ log ของบอท แล้วลองสตาร์ท `tts_daemon.py` ใหม่",
                ephemeral=True)
            return
        wav_paths.append(wav_path)
    gen_s = time.time() - t0

    # ช่องเงียบท้ายทุกประโยค เหมือน /say export_tts (ดู _concat_wavs)
    gap_s = max(SAY_SENTENCE_GAP_S, 0.5) if SAY_SENTENCE_GAP_S > 0 else 0.0
    try:
        export_path, tmpdir = await _concat_wavs(wav_paths, gap_s)
    except ExportError as e:
        for p in wav_paths:
            try:
                os.remove(p)
            except OSError:
                pass
        await interaction.followup.send(f"⚠️ {e}", ephemeral=True)
        return

    transcript_path = None
    try:
        transcript_entries = await _build_transcript(
            wav_paths, translated_texts, gap_s, entry_moods)
        transcript_path = f"{export_path}.transcript.json"
        with open(transcript_path, "w", encoding="utf-8") as f:
            json.dump(transcript_entries, f, ensure_ascii=False, indent=2)
    except Exception as e:  # noqa: BLE001 — ffprobe ล้มเหลว ไม่ทำให้ export เสียงพัง
        transcript_path = None
        await interaction.followup.send(
            f"⚠️ สร้าง transcript.json ไม่สำเร็จ ({e}) — ส่งเฉพาะไฟล์เสียง",
            ephemeral=True)

    saved_path = None
    if save_local:
        # copy ก่อนถึง finally ด้านล่างที่ลบ export_path/transcript_path ทิ้ง —
        # ไม่ move เพราะยังต้องใช้ export_path ส่งแนบแชทต่อ
        try:
            import shutil as _shutil_local
            save_dir = os.path.join(PROJ, "outputs", "translate")
            os.makedirs(save_dir, exist_ok=True)
            stamp = time.strftime("%Y%m%d_%H%M%S")
            saved_path = os.path.join(
                save_dir, f"{stamp}_{interaction.guild.id}_{target}.wav")
            _shutil_local.copy2(export_path, saved_path)
            if transcript_path is not None:
                _shutil_local.copy2(transcript_path, f"{saved_path}.transcript.json")
            print(f"discord_say_bot: translate save_local ok "
                  f"guild={interaction.guild.id} saved_path={saved_path}",
                  file=sys.stderr, flush=True)
        except OSError as e:
            saved_path = None
            print(f"discord_say_bot: translate save_local error "
                  f"guild={interaction.guild.id} err={e}", file=sys.stderr, flush=True)
            await interaction.followup.send(
                f"⚠️ save_local ไม่สำเร็จ ({e}) — ยังส่งไฟล์เสียงในแชทตามปกติ",
                ephemeral=True)

    try:
        translated_txt = "\n".join(translated_texts)
        txt_file = discord.File(
            io.BytesIO(translated_txt.encode("utf-8")),
            filename=f"translate_{target}_{interaction.id}.txt")
        files = [discord.File(export_path, filename=f"translate_{target}.wav"), txt_file]
        if transcript_path is not None:
            files.append(discord.File(transcript_path, filename="transcript.json"))
        view = DeleteMessageView(interaction.user.id)
        sent_msg = await interaction.channel.send(
            f"🌐 แปลเป็น `{target}` + gen เสียงเสร็จแล้ว ({len(wav_paths)} บรรทัด)",
            files=files, view=view)
        view.message = sent_msg
    finally:
        for p in wav_paths:
            try:
                os.remove(p)
            except OSError:
                pass
        if transcript_path is not None:
            try:
                os.remove(transcript_path)
            except OSError:
                pass
        if tmpdir is not None:
            import shutil as _shutil
            _shutil.rmtree(tmpdir, ignore_errors=True)

    ok_msg = "✅ แปล + gen เสียงเสร็จแล้ว"
    if saved_path is not None:
        ok_msg += f" (บันทึกไว้ที่ `{os.path.relpath(saved_path, PROJ)}`)"
    await interaction.followup.send(ok_msg, ephemeral=True)
    print(f"discord_say_bot: translate guild={interaction.guild.id} "
          f"lines={len(wav_paths)} target={target} translate_s={translate_s:.2f} "
          f"gen_s={gen_s:.2f} voice={voice_clean} explicit_mood={mood} "
          f"save_local={save_local} saved_path={saved_path}",
          file=sys.stderr, flush=True)


@tree.command(
    name="txt-to-json",
    description="แปลงไฟล์ .txt (1 บรรทัด = 1 ประโยค) เป็น transcript.json พร้อมใส่ mood ให้")
@app_commands.guild_only()
@app_commands.describe(
    file="ไฟล์ .txt (1 บรรทัด = 1 ประโยค, UTF-8, ≤100 KB) — รองรับ [mood:xxx] tag "
         "หรือ emoji นำหน้าบรรทัดเหมือน /say",
    mood="บังคับ mood ทุกบรรทัด (ไม่เลือก = ใช้ tag/emoji ในบรรทัดนั้นก่อน "
         "ไม่มีค่อยเดาอัตโนมัติจากข้อความ)")
@app_commands.autocomplete(mood=_mood_autocomplete)
async def txt_to_json(interaction: discord.Interaction,
                      file: discord.Attachment,
                      mood: str | None = None) -> None:
    # pre-response validation — error ทุกจุดตรงนี้เป็น ephemeral, ไม่โพสต์ลงแชท
    name_ok = file.filename.lower().endswith(".txt")
    type_ok = (file.content_type or "").startswith("text/")
    if not (name_ok or type_ok):
        await interaction.response.send_message(
            "ไฟล์ต้องเป็น `.txt` (UTF-8 text)", ephemeral=True)
        return
    if file.size > 100_000:
        await interaction.response.send_message(
            "ไฟล์ใหญ่เกิน 100 KB", ephemeral=True)
        return

    try:
        raw = await file.read()
    except discord.DiscordException as e:  # noqa: BLE001
        await interaction.response.send_message(
            f"อ่านไฟล์ไม่สำเร็จ: {e}", ephemeral=True)
        return
    try:
        source_text = raw.decode("utf-8-sig")  # -sig = กิน BOM ถ้ามี
    except UnicodeDecodeError:
        await interaction.response.send_message(
            "ไฟล์ต้องเป็น UTF-8 text", ephemeral=True)
        return

    lines = parse_lines(source_text)
    if not lines:
        await interaction.response.send_message(
            "ไฟล์ว่าง — ไม่มีบรรทัดให้แปลง", ephemeral=True)
        return

    # mood ต่อบรรทัด: mood param (บังคับทั้ง batch) > [mood:xxx]/emoji ในบรรทัด >
    # detect_mood เดาจากคำ (เหมือน /transcribe) — ไม่งั้นไม่ใส่ field mood เลย
    entries: list[dict] = []
    for idx, line in enumerate(lines):
        spoken, auto_mood = extract_mood(line)
        if not spoken:
            continue  # บรรทัดที่เหลือแต่ emoji/ว่าง -> ข้าม
        m = mood or auto_mood or detect_mood(spoken)
        entry = {"id": f"w{idx}", "text": spoken}
        if m is not None:
            entry["mood"] = m
        entries.append(entry)
    if not entries:
        await interaction.response.send_message(
            "ไม่มีข้อความให้แปลง (บรรทัดว่าง/มีแต่ emoji ทั้งหมด)", ephemeral=True)
        return

    transcript_json = discord.File(
        io.BytesIO(json.dumps(entries, ensure_ascii=False, indent=2).encode("utf-8")),
        filename="transcript.json")
    no_ping = discord.AllowedMentions.none()
    view = DeleteMessageView(interaction.user.id)
    await interaction.response.send_message(
        f"📄 แปลงเป็น transcript.json แล้ว ({len(entries)} บรรทัด)",
        files=[transcript_json], allowed_mentions=no_ping, view=view)
    view.message = await interaction.original_response()
    print(f"discord_say_bot: txt-to-json guild={interaction.guild.id} "
          f"bytes={file.size} lines={len(entries)} explicit_mood={mood}",
          file=sys.stderr, flush=True)


# ---------- /voice-clone (TTS-1009) ----------

voice_clone = app_commands.Group(
    name="voice-clone",
    description="สร้าง/จัดการเสียงโคลนสำหรับ /say (create/list/edit/delete/test)",
    guild_only=True)
tree.add_command(voice_clone)


def _voices_summary() -> str:
    voices = voice_store.list_voices()
    if not voices:
        return "ยังไม่มีเสียงใน voices/"
    default = voice_store.get_default_voice()
    rows = []
    for v in voices:
        mark = " (default)" if v["name"] == default else ""
        rows.append(f"• {v['name']}{mark}")
    return "\n".join(rows)


@voice_clone.command(name="list", description="แสดงเสียงทั้งหมดใน voices/")
async def voice_clone_list(interaction: discord.Interaction) -> None:
    body = _voices_summary().replace("```", "`​`​`")
    header = "🎙️ เสียงที่มี:\n```\n"
    footer = "\n```"
    # Discord content limit = 2000 chars — split body by lines if it doesn't fit.
    if len(header) + len(body) + len(footer) <= 2000:
        await interaction.response.send_message(
            f"{header}{body}{footer}", ephemeral=True)
        return

    limit = 2000 - len(header) - len(footer)
    lines = body.split("\n")
    chunks: list[str] = []
    current = ""
    for line in lines:
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            if current:
                chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)

    await interaction.response.send_message(
        f"{header}{chunks[0]}{footer}", ephemeral=True)
    for chunk in chunks[1:]:
        await interaction.followup.send(
            f"```\n{chunk}\n```", ephemeral=True)


@voice_clone.command(name="profile", description="ดูรายละเอียดเสียงหนึ่งตัว")
@app_commands.describe(name="ชื่อเสียงที่จะดู")
async def voice_clone_profile(interaction: discord.Interaction,
                              name: str) -> None:
    try:
        clean = voice_store.sanitize_name(name)
    except VoiceStoreError as e:
        await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
        return
    if not voice_store.voice_exists(clean):
        await interaction.response.send_message(
            f"⚠️ ไม่พบเสียง `{clean}`", ephemeral=True)
        return

    _, txt_path, _ = voice_store.voice_paths(clean)
    has_transcript = os.path.exists(txt_path)
    instruction = voice_store.read_instruction(clean)
    is_default = clean == voice_store.get_default_voice()

    lines = [
        f"🎙️ เสียง `{clean}`{' (default)' if is_default else ''}",
        f"transcript: {'มี' if has_transcript else 'ไม่มี'}",
        f"instruction: {instruction or '(ไม่มี)'}",
    ]
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@voice_clone.command(
    name="set-default", description="ตั้งเสียงหลักที่ /say ใช้เมื่อไม่ระบุ voice:")
@app_commands.describe(name="ชื่อเสียงที่จะตั้งเป็น default")
async def voice_clone_set_default(interaction: discord.Interaction,
                                  name: str) -> None:
    try:
        clean = voice_store.sanitize_name(name)
    except VoiceStoreError as e:
        await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
        return
    if not voice_store.voice_exists(clean):
        await interaction.response.send_message(
            f"⚠️ ไม่พบเสียง `{clean}`", ephemeral=True)
        return
    voice_store.set_default_voice(clean)
    await interaction.response.send_message(
        f"⭐ ตั้ง `{clean}` เป็น default voice แล้ว — `/say` ที่ไม่ระบุ `voice:` "
        f"จะใช้เสียงนี้", ephemeral=True)
    print(f"discord_say_bot: voice-clone set-default guild={interaction.guild.id} "
          f"name={clean}", file=sys.stderr, flush=True)


@voice_clone.command(
    name="create", description="โคลนเสียงใหม่จากไฟล์เสียงที่อัปโหลด")
@app_commands.describe(
    name="ชื่อเสียง (a-z, 0-9, _ เท่านั้น)",
    file="ไฟล์เสียงอ้างอิง .mp3/.wav/.m4a/.ogg (≤ 25 MB, ≥ 3 วิ)",
    instruction="คำบรรยายน้ำเสียงประจำตัวละคร (สั้น, อังกฤษ) — optional",
    overwrite="ทับเสียงชื่อเดิมถ้ามีอยู่แล้ว")
async def voice_clone_create(interaction: discord.Interaction, name: str,
                             file: discord.Attachment,
                             instruction: str | None = None,
                             overwrite: bool = False) -> None:
    try:
        clean = voice_store.sanitize_name(name)
    except VoiceStoreError as e:
        await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
        return
    if not file.filename.lower().endswith(VOICE_CLONE_EXTS):
        await interaction.response.send_message(
            f"ไฟล์ต้องเป็น {', '.join(VOICE_CLONE_EXTS)}", ephemeral=True)
        return
    if file.size > VOICE_CLONE_MAX_BYTES:
        await interaction.response.send_message(
            "ไฟล์ใหญ่เกิน 25 MB", ephemeral=True)
        return
    if voice_store.is_reserved(clean) and not overwrite:
        await interaction.response.send_message(
            f"⚠️ `{clean}` เป็นเสียง default — ใส่ `overwrite:true` ถ้าตั้งใจจริง",
            ephemeral=True)
        return
    if voice_store.voice_exists(clean) and not overwrite:
        await interaction.response.send_message(
            f"⚠️ เสียง `{clean}` มีอยู่แล้ว — ใส่ `overwrite:true` เพื่อทับ",
            ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    ext = os.path.splitext(file.filename.lower())[1]
    src_path = os.path.join(
        tempfile.gettempdir(),
        f"qwen_vc_{os.getpid()}_{int(time.time()*1000)}{ext}")
    wav_path, txt_path, _ = voice_store.voice_paths(clean)
    try:
        try:
            await file.save(src_path)
        except discord.DiscordException as e:  # noqa: BLE001
            await interaction.followup.send(
                f"ดาวน์โหลดไฟล์ไม่สำเร็จ: {e}", ephemeral=True)
            return
        try:
            dur = await asyncio.to_thread(
                voice_store.prepare_ref_audio, src_path, wav_path)
        except VoiceStoreError as e:
            await interaction.followup.send(f"⚠️ {e}", ephemeral=True)
            return
        try:
            lines = await asyncio.to_thread(run_stt, wav_path, None)
        except Exception as e:  # noqa: BLE001
            try:
                os.remove(wav_path)
            except OSError:
                pass
            print(f"discord_say_bot: voice-clone STT error: {e}",
                  file=sys.stderr, flush=True)
            await interaction.followup.send(
                f"ถอดเสียงอ้างอิงไม่สำเร็จ: {e}", ephemeral=True)
            return
        transcript = " ".join(lines).strip()
        if transcript:
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(transcript + "\n")
        elif os.path.exists(txt_path):
            # overwrite เสียงเดิมที่เคยมี transcript แต่รอบนี้ถอดได้ว่าง — ลบทิ้ง
            # ไม่งั้น has_transcript จะโกหกว่ามี (ไฟล์เก่าค้าง ไม่ตรงกับเสียงใหม่)
            os.remove(txt_path)
        if instruction:
            voice_store.write_instruction(clean, instruction)

        if transcript:
            safe = transcript.replace("```", "`​`​`")
            body = (f"ตรวจ transcript ที่ถอดได้ (แก้ที่ `voices/{clean}.txt` ได้):\n"
                     f"```\n{safe}\n```")
        else:
            # ไม่เขียน .txt ว่างเปล่าไว้ — ปล่อยว่างจริง (ref_text=None) ให้ตรงกับ
            # has_transcript=False ใน /voice-clone list; แต่เตือนไว้เพราะเสี่ยงชน
            # บั๊ก upstream ของ mlx-audio (ดู fix_mlx_audio_assets.py) ตอน generate
            # ถ้ายังไม่ได้รัน fix นั้นไว้
            body = ("⚠️ ถอดเสียงอ้างอิงไม่พบข้อความ (เสียงเงียบ/ไม่มีคำพูด) — ไม่มี "
                    f"transcript ให้ ใส่เองที่ `voices/{clean}.txt` ก่อนใช้งานจะ "
                    "ปลอดภัยกว่า ไม่งั้นตอน generate เสียงจะพึ่ง auto-transcribe "
                    "ภายในของ mlx-audio ซึ่งเคยพังถ้ายังไม่ได้รัน "
                    "`fix_mlx_audio_assets.py`")
        await interaction.followup.send(
            f"✅ สร้างเสียง `{clean}` แล้ว ({dur:.1f}s ต้นฉบับ)\n{body}",
            ephemeral=True)
        print(f"discord_say_bot: voice-clone create guild={interaction.guild.id} "
              f"name={clean} src_bytes={file.size} dur_s={dur:.1f} "
              f"transcript_len={len(transcript)} instruction={bool(instruction)}",
              file=sys.stderr, flush=True)
    finally:
        try:
            os.remove(src_path)
        except OSError:
            pass


@voice_clone.command(
    name="edit", description="แก้ instruction หรือเปลี่ยนชื่อเสียง")
@app_commands.describe(
    name="ชื่อเสียงปัจจุบัน",
    instruction="instruction ใหม่ (ส่งค่าว่างเพื่อลบ instruction เดิม)",
    rename="ชื่อใหม่ (a-z, 0-9, _)")
async def voice_clone_edit(interaction: discord.Interaction, name: str,
                           instruction: str | None = None,
                           rename: str | None = None) -> None:
    if instruction is None and rename is None:
        await interaction.response.send_message(
            "ต้องระบุอย่างน้อย `instruction:` หรือ `rename:`", ephemeral=True)
        return
    try:
        clean = voice_store.sanitize_name(name)
    except VoiceStoreError as e:
        await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
        return
    if not voice_store.voice_exists(clean):
        await interaction.response.send_message(
            f"⚠️ ไม่พบเสียง `{clean}`", ephemeral=True)
        return

    changes: list[str] = []
    if instruction is not None:
        if voice_store.is_reserved(clean):
            await interaction.response.send_message(
                f"⚠️ แก้ instruction ของ `{clean}` (reserved voice) ไม่ได้",
                ephemeral=True)
            return
        voice_store.write_instruction(clean, instruction)
        changes.append("instruction ถูกลบ" if not instruction.strip()
                       else "instruction อัปเดตแล้ว")

    final_name = clean
    if rename is not None:
        if voice_store.is_protected(clean):
            await interaction.response.send_message(
                f"⚠️ `{clean}` เป็น default voice ปัจจุบัน — `/voice-clone "
                f"set-default` ไปเสียงอื่นก่อนถึงจะ rename ได้", ephemeral=True)
            return
        try:
            new_clean = voice_store.sanitize_name(rename)
            voice_store.rename_voice(clean, new_clean)
        except VoiceStoreError as e:
            await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
            return
        final_name = new_clean
        changes.append(f"เปลี่ยนชื่อเป็น `{new_clean}`")

    await interaction.response.send_message(
        f"✏️ `{clean}`: " + ", ".join(changes), ephemeral=True)
    print(f"discord_say_bot: voice-clone edit guild={interaction.guild.id} "
          f"name={clean} -> {final_name} changes={changes}",
          file=sys.stderr, flush=True)


@voice_clone.command(name="delete", description="ลบเสียง (ต้อง confirm:true)")
@app_commands.describe(name="ชื่อเสียงที่จะลบ", confirm="ต้องใส่ true เพื่อยืนยัน")
async def voice_clone_delete(interaction: discord.Interaction, name: str,
                             confirm: bool = False) -> None:
    try:
        clean = voice_store.sanitize_name(name)
    except VoiceStoreError as e:
        await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
        return
    if voice_store.is_protected(clean):
        await interaction.response.send_message(
            f"⚠️ `{clean}` เป็น default voice ปัจจุบัน — `/voice-clone "
            f"set-default` ไปเสียงอื่นก่อนถึงจะลบได้", ephemeral=True)
        return
    if not confirm:
        await interaction.response.send_message(
            f"⚠️ ยืนยันด้วย `/voice-clone delete name:{clean} confirm:true`",
            ephemeral=True)
        return
    try:
        removed = voice_store.delete_voice(clean)
    except VoiceStoreError as e:
        await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
        return
    await interaction.response.send_message(
        f"🗑️ ลบเสียง `{clean}` แล้ว ({', '.join(removed)})", ephemeral=True)
    print(f"discord_say_bot: voice-clone delete guild={interaction.guild.id} "
          f"name={clean} removed={removed}", file=sys.stderr, flush=True)


@voice_clone.command(
    name="test", description="ทดลองสร้างเสียงพูดด้วยเสียงนี้")
@app_commands.describe(
    name="ชื่อเสียงที่จะทดสอบ",
    text="ข้อความทดสอบ (ไม่ระบุ = ประโยคเริ่มต้น)",
    mood="โทนเสียง (ไม่ระบุ = ใช้ instruction ประจำเสียง หรือ default)")
@app_commands.autocomplete(mood=_mood_autocomplete)
async def voice_clone_test(interaction: discord.Interaction, name: str,
                           text: str | None = None,
                           mood: str | None = None) -> None:
    try:
        clean = voice_store.sanitize_name(name)
    except VoiceStoreError as e:
        await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
        return
    if not voice_store.voice_exists(clean):
        await interaction.response.send_message(
            f"⚠️ ไม่พบเสียง `{clean}`", ephemeral=True)
        return
    spoken = (text or VOICE_CLONE_TEST_TEXT).strip()
    if len(spoken) > MAX_CHARS:
        await interaction.response.send_message(
            f"ข้อความยาวเกิน {MAX_CHARS} ตัวอักษร", ephemeral=True)
        return
    # instruct: mood > voice instruction > default (ไม่แตะ resolve_instruct — TTS-1010)
    if mood:
        # mood มาจาก autocomplete (ไม่ใช่ static choice) — client ส่งค่านอกลิสต์ได้
        if mood not in MOOD_PRESETS:
            await interaction.response.send_message(
                f"⚠️ ไม่รู้จัก mood `{mood}` — เลือกจาก: "
                f"{', '.join(sorted(MOOD_PRESETS))}", ephemeral=True)
            return
        instruct = MOOD_PRESETS[mood]
    else:
        instruct = voice_store.read_instruction(clean) or MOOD_PRESETS["default"]

    await interaction.response.defer(ephemeral=True, thinking=True)
    wav_path = os.path.join(
        tempfile.gettempdir(),
        f"qwen_vctest_{os.getpid()}_{int(time.time()*1000)}.wav")
    t0 = time.time()
    ok = await asyncio.to_thread(
        _try_daemon, spoken, wav_path, instruct, clean, "wav", "auto")
    gen_s = time.time() - t0
    if not ok:
        try:
            os.remove(wav_path)
        except OSError:
            pass
        await interaction.followup.send(
            "⚠️ TTS daemon ไม่พร้อมใช้งาน หรือสร้างเสียงไม่สำเร็จ", ephemeral=True)
        return
    try:
        await interaction.followup.send(
            f"🎧 ตัวอย่างเสียง `{clean}` (gen {gen_s:.1f}s)",
            file=discord.File(wav_path, filename=f"{clean}_test.wav"),
            ephemeral=True)
    finally:
        try:
            os.remove(wav_path)
        except OSError:
            pass
    print(f"discord_say_bot: voice-clone test guild={interaction.guild.id} "
          f"name={clean} mood={mood} chars={len(spoken)} gen_s={gen_s:.2f}",
          file=sys.stderr, flush=True)


# ---------- /voice-design ----------

# lazy singleton — โหลดครั้งแรกตอน /voice-design ถูกเรียก แล้ว cache ไว้ใช้ซ้ำ
# (ADR-0001: โมเดลเฉพาะ feature ฝั่ง Discord อยู่ใน process ของบอทเอง ไม่แตะ
# daemon protocol ที่ Hermes พึ่งพา)
_voice_design_model = None


def _load_voice_design_model():
    """โหลด VoiceDesign model (mono singleton) — import load_model แบบ lazy
    ตรงกับที่ main.py ทำ raise FileNotFoundError ถ้าไม่พบ model path"""
    global _voice_design_model
    if _voice_design_model is None:
        if not os.path.isdir(VOICE_DESIGN_MODEL_PATH):
            raise FileNotFoundError(
                f"VoiceDesign model not found at {VOICE_DESIGN_MODEL_PATH}")
        from mlx_audio.tts.utils import load_model
        _voice_design_model = load_model(VOICE_DESIGN_MODEL_PATH)
    return _voice_design_model


def _run_voice_design(description: str, text: str, out_wav: str) -> None:
    """generate เสียงจากคำบรรยาย (instruct) ลงไฟล์ out_wav — blocking,
    เรียกผ่าน asyncio.to_thread เท่านั้น (ห้าม block event loop)

    pattern เดียวกับ main.py run_design_session / qwen_clone_tts._run:
    generate_audio เขียนลง dir (ต่อท้าย _NNN) -> ย้ายไฟล์ที่เพิ่งเขียนมาเป็น out_wav
    """
    import shutil
    from mlx_audio.tts.generate import generate_audio

    model = _load_voice_design_model()
    tmp_dir = tempfile.mkdtemp(prefix="qwen_vd_")
    try:
        generate_audio(model=model, text=text, instruct=description,
                       output_path=tmp_dir)
        cands = sorted(
            (os.path.join(tmp_dir, f) for f in os.listdir(tmp_dir)
             if f.endswith((".wav", ".mp3"))),
            key=os.path.getmtime)
        if not cands:
            raise RuntimeError("no audio produced")
        shutil.move(cands[-1], out_wav)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@tree.command(
    name="voice-design",
    description="สร้างเสียงใหม่จากคำบรรยายข้อความ (ไม่ต้องมีไฟล์เสียงอ้างอิง)")
@app_commands.guild_only()
@app_commands.describe(
    description="คำบรรยายเสียงที่ต้องการ (สั้น, อังกฤษ) เช่น 'deep calm male narrator'",
    text="ข้อความตัวอย่างที่จะพูด",
    save_as="ถ้าระบุ = บันทึกผลเป็นเสียงถาวรใหม่ใน voices/ (a-z, 0-9, _)",
    overwrite="ทับเสียงชื่อเดิมถ้ามีอยู่แล้ว (ใช้คู่กับ save_as)")
async def voice_design(interaction: discord.Interaction, description: str,
                       text: str, save_as: str | None = None,
                       overwrite: bool = False) -> None:
    spoken = text.strip()
    if not spoken:
        await interaction.response.send_message(
            "ต้องระบุ `text:` เป็นข้อความตัวอย่างที่จะพูด", ephemeral=True)
        return
    if len(spoken) > MAX_CHARS:
        await interaction.response.send_message(
            f"ข้อความยาวเกิน {MAX_CHARS} ตัวอักษร", ephemeral=True)
        return

    # save_as: sanitize + เช็ค reserved/exists เหมือน /voice-clone create ทุกประการ
    clean: str | None = None
    if save_as is not None:
        try:
            clean = voice_store.sanitize_name(save_as)
        except VoiceStoreError as e:
            await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
            return
        if voice_store.is_reserved(clean) and not overwrite:
            await interaction.response.send_message(
                f"⚠️ `{clean}` เป็นเสียง default — ใส่ `overwrite:true` ถ้าตั้งใจจริง",
                ephemeral=True)
            return
        if voice_store.voice_exists(clean) and not overwrite:
            await interaction.response.send_message(
                f"⚠️ เสียง `{clean}` มีอยู่แล้ว — ใส่ `overwrite:true` เพื่อทับ",
                ephemeral=True)
            return

    if not os.path.isdir(VOICE_DESIGN_MODEL_PATH):
        await interaction.response.send_message(
            "⚠️ ไม่พบโมเดล VoiceDesign — โหลด "
            "`models/Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit` ก่อนใช้คำสั่งนี้",
            ephemeral=True)
        return

    # โหลดโมเดล + generate ช้ากว่า 3 วิแน่ -> defer ก่อน (spinner เห็นเฉพาะคนสั่ง)
    await interaction.response.defer(ephemeral=True, thinking=True)

    wav_path = os.path.join(
        tempfile.gettempdir(),
        f"qwen_vd_{os.getpid()}_{int(time.time()*1000)}.wav")
    t0 = time.time()
    try:
        try:
            await asyncio.to_thread(
                _run_voice_design, description, spoken, wav_path)
        except FileNotFoundError as e:
            await interaction.followup.send(f"⚠️ {e}", ephemeral=True)
            return
        except Exception as e:  # noqa: BLE001
            print(f"discord_say_bot: voice-design generate error: {e}",
                  file=sys.stderr, flush=True)
            await interaction.followup.send(
                f"สร้างเสียงไม่สำเร็จ: {e}", ephemeral=True)
            return
        gen_s = time.time() - t0

        # ไม่บันทึก -> แนบ preview อย่างเดียว (เหมือน /voice-clone test)
        if clean is None:
            await interaction.followup.send(
                f"🎨 ตัวอย่างเสียงที่ออกแบบไว้ (gen {gen_s:.1f}s)\n"
                f"คำบรรยาย: `{description}`",
                file=discord.File(wav_path, filename="voice_design.wav"),
                ephemeral=True)
            print(f"discord_say_bot: voice-design guild={interaction.guild.id} "
                  f"chars={len(spoken)} gen_s={gen_s:.2f} save_as=None",
                  file=sys.stderr, flush=True)
            return

        # save_as: trim/reformat เป็น reference clip ที่ถูกต้อง (mono 24kHz,
        # ≤ REF_TRIM_SECONDS) ผ่านฟังก์ชันเดียวกับ /voice-clone create
        vc_wav, vc_txt, _ = voice_store.voice_paths(clean)
        try:
            await asyncio.to_thread(
                voice_store.prepare_ref_audio, wav_path, vc_wav)
        except VoiceStoreError as e:
            await interaction.followup.send(f"⚠️ {e}", ephemeral=True)
            return

        # ถอด transcript ของ wav ที่ "trim แล้ว" (ไม่ใช่ text ต้นฉบับ) — ถ้า text
        # ยาวกว่า REF_TRIM_SECONDS วินาที เฉพาะ transcript ของคลิปที่ถูก trim จริง
        # เท่านั้นถึงจะตรง (เหตุผลเดียวกับ /voice-clone create)
        try:
            lines = await asyncio.to_thread(run_stt, vc_wav, None)
        except Exception as e:  # noqa: BLE001
            try:
                os.remove(vc_wav)
            except OSError:
                pass
            print(f"discord_say_bot: voice-design STT error: {e}",
                  file=sys.stderr, flush=True)
            await interaction.followup.send(
                f"ถอดเสียงอ้างอิงไม่สำเร็จ: {e}", ephemeral=True)
            return
        transcript = " ".join(lines).strip()
        if transcript:
            with open(vc_txt, "w", encoding="utf-8") as f:
                f.write(transcript + "\n")
        elif os.path.exists(vc_txt):
            # overwrite เสียงเดิมที่เคยมี transcript แต่รอบนี้ถอดได้ว่าง — ลบทิ้ง
            # ไม่ให้ has_transcript โกหกว่ามี (ไฟล์เก่าค้าง ไม่ตรงเสียงใหม่)
            os.remove(vc_txt)

        # เก็บ description เป็น default instruction ของเสียงใหม่ ให้ /say ใช้ต่อ
        # พร้อม tone ที่ตั้งใจไว้ตั้งแต่ออกแบบ
        voice_store.write_instruction(clean, description)

        if transcript:
            safe = transcript.replace("```", "`​`​`")
            body = (f"ตรวจ transcript ที่ถอดได้ (แก้ที่ `voices/{clean}.txt` ได้):\n"
                    f"```\n{safe}\n```")
        else:
            body = ("⚠️ ถอดเสียงอ้างอิงไม่พบข้อความ — ไม่มี transcript ให้ "
                    f"ใส่เองที่ `voices/{clean}.txt` ก่อนใช้งานจะปลอดภัยกว่า")
        await interaction.followup.send(
            f"✅ สร้างเสียง `{clean}` จากคำบรรยาย `{description}` แล้ว "
            f"(gen {gen_s:.1f}s) — ใช้กับ `/say voice:{clean}` ได้เลย\n{body}",
            file=discord.File(wav_path, filename=f"{clean}_preview.wav"),
            ephemeral=True)
        print(f"discord_say_bot: voice-design guild={interaction.guild.id} "
              f"chars={len(spoken)} gen_s={gen_s:.2f} save_as={clean} "
              f"transcript_len={len(transcript)}",
              file=sys.stderr, flush=True)
    finally:
        try:
            os.remove(wav_path)
        except OSError:
            pass


def main() -> int:
    if not DISCORD_BOT_TOKEN:
        print("ERROR: DISCORD_BOT_TOKEN is not set — export it as an "
              "environment variable before running (no .env auto-load in "
              "this project)", file=sys.stderr)
        return 1
    client.run(DISCORD_BOT_TOKEN)
    return 0


if __name__ == "__main__":
    sys.exit(main())
