#!/usr/bin/env python3
"""Discord say bot — slash command
`/say text:<ข้อความ> | file:<x.txt> [mood:<preset>] [export_tts:true]`

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
    SAY_SENTENCE_GAP_S   (default 0.5) วินาทีที่เว้นเงียบหลังจบแต่ละประโยคก่อนเล่นบรรทัดถัดไป (0 = ปิด)
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

# /voice-clone limits (TTS-1009)
VOICE_CLONE_MAX_BYTES = 25 * 1024 * 1024
VOICE_CLONE_EXTS = (".mp3", ".wav", ".m4a", ".ogg")
VOICE_CLONE_TEST_TEXT = "สวัสดีค่ะ นี่คือตัวอย่างเสียงพูดจากเสียงโคลนนี้"

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


async def _voice_autocomplete(
        interaction: discord.Interaction,
        current: str) -> list[app_commands.Choice[str]]:
    """dynamic autocomplete แทน static Choice list — กันเกิน 25 รายการ (Discord
    limit) เมื่อมีเสียงเยอะ; filter ด้วย substring ของ current"""
    current = (current or "").strip().lower()
    names = [v["name"] for v in voice_store.list_voices()]
    matched = [n for n in names if current in n][:25]
    return [app_commands.Choice(name=n, value=n) for n in matched]


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
                  "แบบ hyperframes transcribe) คู่กับไฟล์เสียง — ต้องใช้กับ export_tts:true")
@app_commands.choices(
    mood=[app_commands.Choice(name=m, value=m) for m in sorted(MOOD_PRESETS)],
    language=[app_commands.Choice(name=c, value=c)
              for c in LANG_CODES if c != "auto"])
@app_commands.autocomplete(voice=_voice_autocomplete)
async def say(interaction: discord.Interaction, text: str | None = None,
              mood: str | None = None,
              language: str | None = None,
              file: discord.Attachment | None = None,
              voice: str | None = None,
              export_tts: bool = False,
              is_transcript: bool = False) -> None:
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
    jobs_meta: list[tuple[str, str | None]] = []  # (spoken, instruct)
    for spoken, m in prepared:
        try:
            instruct = resolve_instruct(m, None, voice_instruct)
        except ValueError as e:
            await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
            return
        jobs_meta.append((spoken, instruct))

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
    for idx, (spoken, instruct) in enumerate(jobs_meta):
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
        export_path = wav_paths[0]
        tmpdir = None
        if len(wav_paths) > 1:
            import shutil
            import subprocess
            if shutil.which("ffmpeg") is None:
                for p in wav_paths:
                    try:
                        os.remove(p)
                    except OSError:
                        pass
                await interaction.followup.send(
                    "⚠️ ต้องมี ffmpeg เพื่อรวมหลายบรรทัดเป็นไฟล์เดียว", ephemeral=True)
                return
            tmpdir = tempfile.mkdtemp(prefix="qwen_say_export_")
            list_file = os.path.join(tmpdir, "list.txt")
            with open(list_file, "w", encoding="utf-8") as f:
                for p in wav_paths:
                    f.write(f"file '{p}'\n")
            export_path = os.path.join(tmpdir, "export.wav")
            r = subprocess.run(
                ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                 "-f", "concat", "-safe", "0", "-i", list_file,
                 "-ar", "24000", "-ac", "1", export_path],
                capture_output=True, text=True)
            if r.returncode != 0 or not os.path.exists(export_path):
                shutil.rmtree(tmpdir, ignore_errors=True)
                for p in wav_paths:
                    try:
                        os.remove(p)
                    except OSError:
                        pass
                await interaction.followup.send(
                    f"⚠️ รวมไฟล์เสียงไม่สำเร็จ: {r.stderr}", ephemeral=True)
                return

        transcript_path = None
        if is_transcript:
            # timeline จากความยาว wav ต่อบรรทัดจริง (ffprobe) ไม่ใช้ STT — ข้อความ
            # รู้อยู่แล้วจาก jobs_meta/wav_paths อยู่ index ตรงกัน; ต่อกันแบบ concat
            # ตรงๆ ไม่มี silence คั่น (ดู ffmpeg concat ด้านบน) จึงบวกสะสมตรงๆ ได้
            try:
                durations = [await asyncio.to_thread(probe_duration, p)
                             for p in wav_paths]
                entries = []
                t = 0.0
                for idx, (spoken, _instruct) in enumerate(jobs_meta):
                    d = durations[idx]
                    entries.append({"id": f"w{idx}", "text": spoken,
                                     "start": round(t, 3), "end": round(t + d, 3)})
                    t += d
                transcript_path = f"{export_path}.transcript.json"
                with open(transcript_path, "w", encoding="utf-8") as f:
                    json.dump(entries, f, ensure_ascii=False, indent=2)
            except Exception as e:  # noqa: BLE001 — ffprobe ล้มเหลว ไม่ทำให้ export เสียงพัง
                transcript_path = None
                await interaction.followup.send(
                    f"⚠️ สร้าง transcript.json ไม่สำเร็จ ({e}) — ส่งเฉพาะไฟล์เสียง",
                    ephemeral=True)

        try:
            files = [discord.File(export_path, filename="say_export.wav")]
            if transcript_path is not None:
                files.append(discord.File(transcript_path, filename="transcript.json"))
            await interaction.channel.send(
                f"🔊 ส่งออกเสียงแล้ว ({len(wav_paths)} บรรทัด)", files=files)
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

        await interaction.followup.send("✅ ส่งออกไฟล์เสียงแล้ว", ephemeral=True)
        print(f"discord_say_bot: exported say guild={interaction.guild.id} "
              f"src={src} lines={len(wav_paths)} gen_s={gen_s:.2f} "
              f"explicit_mood={explicit_mood} lang={lang} chars={total_chars} "
              f"voice={voice_clean} is_transcript={is_transcript}",
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
    mood=[app_commands.Choice(name=m, value=m) for m in sorted(MOOD_PRESETS)],
    language=[
        app_commands.Choice(name="ไทย", value="th"),
        app_commands.Choice(name="ญี่ปุ่น", value="ja"),
        app_commands.Choice(name="อังกฤษ", value="en"),
    ])
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
            lines = await asyncio.to_thread(run_stt, audio_path, language)
        except Exception as e:  # noqa: BLE001
            print(f"discord_say_bot: transcribe STT error: {e}",
                  file=sys.stderr, flush=True)
            await interaction.followup.send(
                f"ถอดเสียงไม่สำเร็จ: {e}", ephemeral=True)
            return
        stt_s = time.time() - t0

        if not lines:
            await interaction.followup.send(
                "ถอดเสียงไม่พบข้อความ (เสียงเงียบหรือไม่มีคำพูด)",
                ephemeral=True)
            return

        composed: list[str] = []
        for line in lines:
            m = mood or detect_mood(line)
            prefix = f"{MOOD_EMOJI[m]} " if m in MOOD_EMOJI else ""
            composed.append(f"{prefix}{line}")
        body = "\n".join(composed)

        txt = discord.File(
            io.BytesIO(body.encode("utf-8")),
            filename=f"transcribe_{interaction.id}.txt")
        no_ping = discord.AllowedMentions.none()
        # แทรก zero-width space กัน ``` ในเนื้อความทะลุ code fence (ไฟล์แนบใช้ body เดิม);
        # allowed_mentions=none กัน @mention จาก transcript
        safe_body = body.replace("```", "`​`​`")
        if len(body) <= TRANSCRIBE_INLINE_MAX:
            await interaction.channel.send(
                f"```\n{safe_body}\n```", file=txt, allowed_mentions=no_ping)
        else:
            await interaction.channel.send(
                "📝 ถอดเสียงเสร็จแล้ว (ข้อความยาว — ดูไฟล์แนบ)", file=txt,
                allowed_mentions=no_ping)
        await interaction.followup.send("✅ เสร็จแล้ว", ephemeral=True)
        print(f"discord_say_bot: transcribe guild={interaction.guild.id} "
              f"bytes={file.size} dur_s={duration:.1f} lines={len(lines)} "
              f"stt_s={stt_s:.2f} model={WHISPER_MODEL} lang={language or 'auto'} "
              f"explicit_mood={mood}",
              file=sys.stderr, flush=True)
    finally:
        try:
            os.remove(audio_path)
        except OSError:
            pass


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
        tag = "" if v["has_transcript"] else " (ไม่มี transcript)"
        ins = f" — {v['instruction']}" if v["instruction"] else ""
        mark = " (default)" if v["name"] == default else ""
        rows.append(f"• {v['name']}{tag}{ins}{mark}")
    return "\n".join(rows)


@voice_clone.command(name="list", description="แสดงเสียงทั้งหมดใน voices/")
async def voice_clone_list(interaction: discord.Interaction) -> None:
    body = _voices_summary().replace("```", "`​`​`")
    await interaction.response.send_message(
        f"🎙️ เสียงที่มี:\n```\n{body}\n```", ephemeral=True)


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
@app_commands.choices(
    mood=[app_commands.Choice(name=m, value=m) for m in sorted(MOOD_PRESETS)])
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
