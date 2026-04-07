import os
import time
import asyncio
import subprocess

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

API_ID = int(os.getenv("tk"))
API_HASH = os.getenv("apihash")
BOT_TOKEN = os.getenv("apiid")

app = Client("encoder_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

user_settings = {}
watermark_text = "telegram:@yourname"

last_update_time = {}
last_text = {}

# ---------------- SAFE EDIT ----------------
async def safe_edit(msg, text):
    msg_id = msg.id

    if last_text.get(msg_id) == text:
        return

    if time.time() - last_update_time.get(msg_id, 0) < 5:
        return

    try:
        await msg.edit_text(text)
        last_update_time[msg_id] = time.time()
        last_text[msg_id] = text
    except:
        pass

# ---------------- START ----------------
@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply("Send me a video 🎬")

# ---------------- TEXT ----------------
@app.on_message(filters.command("text"))
async def set_text(client, message):
    global watermark_text
    watermark_text = message.text.split(" ", 1)[1]
    await message.reply(f"✅ Watermark updated:\n{watermark_text}")

# ---------------- VIDEO ----------------
@app.on_message(filters.video | filters.document)
async def video_handler(client, message):
    file_id = message.id

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎥 CRF 23", callback_data=f"encode|{file_id}|23")],
        [InlineKeyboardButton("⚡ CRF 28", callback_data=f"encode|{file_id}|28")],
        [InlineKeyboardButton("🎧 Audio AAC", callback_data=f"audio|{file_id}")],
        [InlineKeyboardButton("📉 720p", callback_data=f"down|{file_id}")]
    ])

    user_settings[file_id] = {
        "msg": message,
        "crf": 23,
        "audio": "copy",
        "scale": None
    }

    await message.reply("Choose options:", reply_markup=keyboard)

# ---------------- BUTTON ----------------
@app.on_callback_query()
async def callback(client, query):
    data = query.data.split("|")
    action = data[0]
    file_id = int(data[1])

    settings = user_settings[file_id]

    if action == "encode":
        settings["crf"] = data[2]

    elif action == "audio":
        settings["audio"] = "aac"

    elif action == "down":
        settings["scale"] = "1280:-2"

    await query.message.edit_text("⚙ Processing...")

    await process_video(client, query.message, settings)

# ---------------- DOWNLOAD ----------------
async def download(client, msg, path, status_msg):
    async def progress(current, total):
        percent = int(current * 100 / total)
        bar = "█" * (percent // 5) + "░" * (20 - percent // 5)

        await safe_edit(status_msg, f"📥 Downloading\n[{bar}] {percent}%")

    return await msg.download(file_name=path, progress=progress)

# ---------------- FFMPEG ----------------
async def run_ffmpeg(cmd, duration, msg):
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stderr=asyncio.subprocess.PIPE
    )

    while True:
        line = await process.stderr.readline()
        if not line:
            break

        line = line.decode()

        if "time=" in line:
            try:
                t = line.split("time=")[-1].split(" ")[0]
                h, m, s = t.split(":")
                current = float(h)*3600 + float(m)*60 + float(s)

                percent = min(int((current / duration) * 100), 100)
                bar = "█" * (percent // 5) + "░" * (20 - percent // 5)

                await safe_edit(msg, f"🎬 Encoding\n[{bar}] {percent}%")
            except:
                pass

    await process.wait()

# ---------------- UPLOAD ----------------
async def upload(client, chat_id, file_path, thumb, duration, msg):
    async def progress(current, total):
        percent = int(current * 100 / total)
        bar = "█" * (percent // 5) + "░" * (20 - percent // 5)

        await safe_edit(msg, f"📤 Uploading\n[{bar}] {percent}%")

    await client.send_video(
        chat_id,
        file_path,
        thumb=thumb,
        duration=int(duration),
        supports_streaming=True,
        progress=progress
    )

# ---------------- PROCESS ----------------
async def process_video(client, status_msg, settings):
    msg = settings["msg"]

    input_path = f"{msg.id}.mp4"
    output_path = f"out_{msg.id}.mp4"
    thumb_path = f"{msg.id}.jpg"

    # DOWNLOAD
    await download(client, msg, input_path, status_msg)

    # DURATION
    duration = float(subprocess.check_output([
        "ffprobe","-v","error",
        "-show_entries","format=duration",
        "-of","default=noprint_wrappers=1:nokey=1",
        input_path
    ]).decode())

    # THUMB
    subprocess.run([
        "ffmpeg","-i",input_path,
        "-ss","2",
        "-vframes","1",
        thumb_path
    ])

    vf = f"drawtext=text='{watermark_text}':x=10:y=H-th-10:fontsize=20:fontcolor=white@0.4"

    if settings["scale"]:
        vf = f"scale={settings['scale']}," + vf

    cmd = [
        "ffmpeg","-i",input_path,
        "-c:v","libx264",
        "-crf",str(settings["crf"]),
        "-preset","veryfast",
        "-vf",vf,
        "-movflags","+faststart"
    ]

    if settings["audio"] == "aac":
        cmd += ["-c:a","aac","-b:a","128k"]
    else:
        cmd += ["-c:a","copy"]

    cmd.append(output_path)

    # ENCODE
    await run_ffmpeg(cmd, duration, status_msg)

    # UPLOAD
    await upload(client, msg.chat.id, output_path, thumb_path, duration, status_msg)

    await safe_edit(status_msg, "✅ Done!")

    os.remove(input_path)
    os.remove(output_path)
    os.remove(thumb_path)

# ---------------- RUN ----------------
app.run()
