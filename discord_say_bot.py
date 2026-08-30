#!/usr/bin/env python3
"""Discord say bot — slash command `/say text:<ข้อความ> [mood:<preset>]`

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
"""
import asyncio
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
from say_moods import extract_mood, first_line_over_limit, parse_lines  # noqa: E402

DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
DISCORD_GUILD_ID = os.environ.get("DISCORD_GUILD_ID")
VC_IDLE_TIMEOUT_S = float(os.environ.get("VC_IDLE_TIMEOUT_S", "60"))
SAY_SENTENCE_GAP_S = float(os.environ.get("SAY_SENTENCE_GAP_S", "0.5"))

DEFAULT_VOICE = "Liino"

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
    text="ข้อความ (1 บรรทัด = 1 ประโยค; วางข้อความหลายบรรทัดได้)",
    mood="โทนเสียง (ไม่เลือก = auto จาก emoji หรือปกติ)")
@app_commands.choices(mood=[
    app_commands.Choice(name=m, value=m) for m in sorted(MOOD_PRESETS)])
async def say(interaction: discord.Interaction, text: str,
              mood: str | None = None) -> None:
    explicit_mood = mood  # ชื่อ preset ที่เลือกจาก dropdown หรือ None
    lines = parse_lines(text)
    if not lines:
        await interaction.response.send_message(
            f"ใช้: `/say text:<ข้อความ> [mood:<preset>]` (หลายบรรทัดได้ ไม่จำกัด"
            f"จำนวนบรรทัด 1 บรรทัด = 1 ประโยค ไม่เกิน {MAX_CHARS} ตัวอักษรต่อบรรทัด)",
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
          f"lines={len(wav_paths)} gen_s={gen_s:.2f} "
          f"explicit_mood={explicit_mood} chars={total_chars}",
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
