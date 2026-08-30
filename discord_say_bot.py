#!/usr/bin/env python3
"""Discord say bot — slash command `/say text:<ข้อความ> | file:<x.txt> [mood:<preset>]`

`text` = ข้อความบรรทัดเดียว, `file` = `.txt` attachment สำหรับข้อความหลายบรรทัด
(ต้องระบุอย่างใดอย่างหนึ่ง — XOR)

ให้บอทเข้า voice channel ที่ผู้สั่งอยู่ สร้างเสียงด้วย qwen3-tts (เสียงโคลน Liino)
ผ่าน tts_daemon fast path เท่านั้น (ไม่ fallback โหลดโมเดลเองถ้า daemon ล่ม —
ดู Decision ใน obsidian/kanban/tasks/TTS-1001.md) แล้วเล่นในห้องตามคิวต่อ guild

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
import os
import sys
import tempfile
import time

import discord
from discord import app_commands

PROJ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJ)

# reuse ของเดิมจาก qwen_clone_tts.py ทั้งหมด — ห้าม duplicate ค่า/logic
from qwen_clone_tts import MAX_CHARS, MOOD_PRESETS, _try_daemon, resolve_instruct  # noqa: E402
from say_moods import MOOD_EMOJI, extract_mood, first_line_over_limit, parse_lines  # noqa: E402
from stt_transcribe import WHISPER_MODEL, probe_duration, transcribe as run_stt  # noqa: E402
from transcribe_mood import detect_mood  # noqa: E402

DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
DISCORD_GUILD_ID = os.environ.get("DISCORD_GUILD_ID")
VC_IDLE_TIMEOUT_S = float(os.environ.get("VC_IDLE_TIMEOUT_S", "60"))
SAY_SENTENCE_GAP_S = float(os.environ.get("SAY_SENTENCE_GAP_S", "0.5"))

DEFAULT_VOICE = "Liino"

# /transcribe limits (TTS-1005)
TRANSCRIBE_MAX_BYTES = 20 * 1024 * 1024
TRANSCRIBE_MAX_DURATION_S = 600
TRANSCRIBE_INLINE_MAX = 1800  # ยาวกว่านี้ -> ส่งเฉพาะไฟล์แนบ ไม่ preview ในแชท

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


@tree.command(name="say",
              description="ให้บอทพูดข้อความใน voice channel ด้วยเสียง Liino")
@app_commands.guild_only()
@app_commands.describe(
    text="ข้อความบรรทัดเดียว (หลายบรรทัดให้ใช้ file:)",
    mood="โทนเสียง (ไม่เลือก = auto จาก emoji หรือปกติ)",
    file="ไฟล์ .txt สำหรับข้อความหลายบรรทัด (1 บรรทัด = 1 ประโยค, UTF-8, ≤100 KB)")
@app_commands.choices(mood=[
    app_commands.Choice(name=m, value=m) for m in sorted(MOOD_PRESETS)])
async def say(interaction: discord.Interaction, text: str | None = None,
              mood: str | None = None,
              file: discord.Attachment | None = None) -> None:
    explicit_mood = mood  # ชื่อ preset ที่เลือกจาก dropdown หรือ None

    # ต้องระบุ text หรือ file อย่างใดอย่างหนึ่ง (XOR) — เช็คก่อน defer
    if (text is None) == (file is None):
        await interaction.response.send_message(
            "ใช้: `/say text:<ข้อความ>` (บรรทัดเดียว) หรือ `/say file:<x.txt>` "
            "(หลายบรรทัด) — เลือกอย่างใดอย่างหนึ่ง", ephemeral=True)
        return

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
            instruct = resolve_instruct(m, None, False)
        except ValueError as e:
            await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
            return
        jobs_meta.append((spoken, instruct))

    author_voice = getattr(interaction.user, "voice", None)
    if author_voice is None or author_voice.channel is None:
        await interaction.response.send_message(
            "ต้องเข้า voice channel ก่อนถึงจะใช้คำสั่งนี้ได้", ephemeral=True)
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
            _try_daemon, spoken, wav_path, instruct, DEFAULT_VOICE, "wav")
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

    playback = _get_playback(interaction.guild)
    playback.ensure_worker()
    for wav_path in wav_paths:
        await playback.queue.put((voice_channel, interaction.channel, wav_path))

    # success: แจ้ง channel ปกติ + เคลียร์ spinner ephemeral ของคนสั่ง
    await interaction.channel.send(f"🔊 เข้าคิวแล้ว {len(wav_paths)} บรรทัด")
    await interaction.followup.send("✅ เข้าคิวแล้ว", ephemeral=True)
    print(f"discord_say_bot: queued say guild={interaction.guild.id} "
          f"src={src} lines={len(wav_paths)} gen_s={gen_s:.2f} "
          f"explicit_mood={explicit_mood} chars={total_chars}",
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
        if len(body) <= TRANSCRIBE_INLINE_MAX:
            await interaction.channel.send(f"```\n{body}\n```", file=txt)
        else:
            await interaction.channel.send(
                "📝 ถอดเสียงเสร็จแล้ว (ข้อความยาว — ดูไฟล์แนบ)", file=txt)
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
