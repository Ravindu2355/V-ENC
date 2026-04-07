import os
import time
import asyncio
import subprocess

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

API_ID = int(os.getenv("apiid"))
API_HASH = os.getenv("apihash")
BOT_TOKEN = os.getenv("tk")

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
    if len(message.command) < 2:
        return await message.reply("Usage: /text your_text")

    watermark_text = message.text.split(" ", 1)[1]
    await message.reply(f"✅ Watermark updated:\n{watermark_text}")

# ---------------- VIDEO ----------------
@app.on_message(filters.video | filters.document)
async def video_handler(client, message):
    file_id = message.id

    user_settings[file_id] = {
        "msg": message,
        "crf": 23,
        "audio": "copy",
        "scale": None
    }

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎥 CRF 23", callback_data=f"encode|{file_id}|23")],
        [InlineKeyboardButton("⚡ CRF 28", callback_data=f"encode|{file_id}|28")],
        [InlineKeyboardButton("🎧 AAC Audio", callback_data=f"audio|{file_id}")],
        [InlineKeyboardButton("📉 720p", callback_data=f"down|{file_id}")]
    ])

    await message.reply("Choose options:", reply_markup=keyboard)

# ---------------- BUTTON ----------------
@app.on_callback_query()
async def callback(client, query):
    try:
        data = query.data.split("|")
        action = data[0]
        file_id = int(data[1])

        settings = user_settings.get(file_id)
        if not settings:
            return await query.answer("Expired!", show_alert=True)

        if action == "encode":
            settings["crf"] = data[2]

        elif action == "audio":
            settings["audio"] = "aac"

        elif action == "down":
            settings["scale"] = "1280:-2"

        await query.message.edit_text("⚙ Processing...")

        await process_video(client, query.message, settings)

    except Exception as e:
        print(e)
        await query.message.reply(f"❌ Error:\n{e}")

# ---------------- DOWNLOAD ----------------
async def download(msg, path, status_msg):
    async def progress(current, total):
        percent = int(current * 100 / total)
        bar = "█" * (percent // 5) + "░" * (20 - percent // 5)
        await safe_edit(status_msg, f"📥 Downloading\n[{bar}] {percent}%")

    try:
        file_path = await msg.download(file_name=path, progress=progress)
        return file_path
    except Exception as e:
        await safe_edit(status_msg, f"❌ Download failed:\n{e}")
        return None

# ---------------- FFMPEG ----------------
async def run_ffmpeg(cmd, duration, msg):
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stderr=asyncio.subprocess.PIPE
    )

    error_log = ""

    while True:
        line = await process.stderr.readline()
        if not line:
            break

        line = line.decode(errors="ignore")
        error_log += line

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
    return process.returncode, error_log

# ---------------- UPLOAD ----------------
async def upload(client, chat_id, file_path, thumb, duration, msg):
    if not os.path.exists(file_path):
        await safe_edit(msg, "❌ Output file missing!")
        return

    async def progress(current, total):
        percent = int(current * 100 / total)
        bar = "█" * (percent // 5) + "░" * (20 - percent // 5)
        await safe_edit(msg, f"📤 Uploading\n[{bar}] {percent}%")

    try:
        await client.send_video(
            chat_id,
            file_path,
            thumb=thumb if os.path.exists(thumb) else None,
            duration=int(duration),
            supports_streaming=True,
            progress=progress
        )
    except Exception as e:
        await safe_edit(msg, f"❌ Upload failed:\n{e}")

# ---------------- PROCESS ----------------
async def process_video(client, status_msg, settings):
    msg = settings["msg"]

    # DOWNLOAD
    input_path = await download(msg, f"{msg.id}", status_msg)
    if not input_path:
        return

    if not os.path.exists(input_path):
        await safe_edit(status_msg, "❌ File not found after download!")
        return

    output_path = f"out_{msg.id}.mp4"
    thumb_path = f"{msg.id}.jpg"

    try:
        # DURATION
        duration = float(subprocess.check_output([
            "ffprobe","-v","error",
            "-show_entries","format=duration",
            "-of","default=noprint_wrappers=1:nokey=1",
            input_path
        ]).decode().strip())

        # CODEC DETECT
        codec = subprocess.check_output([
            "ffprobe","-v","error",
            "-select_streams","v:0",
            "-show_entries","stream=codec_name",
            "-of","csv=p=0",
            input_path
        ]).decode().strip()

        # THUMB FIX
        subprocess.run([
            "ffmpeg","-y",
            "-i",input_path,
            "-ss","2",
            "-frames:v","1",
            thumb_path
        ])

        # SMART MODE
        if codec == "h264" and settings["audio"] == "copy" and not settings["scale"]:
            cmd = [
                "ffmpeg","-y",
                "-i",input_path,
                "-c","copy",
                "-movflags","+faststart",
                output_path
            ]
        else:
            vf = f"drawtext=text='{watermark_text}':x=10:y=H-th-10:fontsize=20:fontcolor=white@0.4"
            if settings["scale"]:
                vf = f"scale={settings['scale']}," + vf

            cmd = [
                "ffmpeg","-y",
                "-i",input_path,
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
        code, log = await run_ffmpeg(cmd, duration, status_msg)

        if code != 0:
            print(log)
            await safe_edit(status_msg, "❌ Encoding failed!")
            return

        # UPLOAD
        await upload(client, msg.chat.id, output_path, thumb_path, duration, status_msg)

        await safe_edit(status_msg, "✅ Done!")

    except Exception as e:
        print(e)
        await safe_edit(status_msg, f"❌ Error:\n{e}")

    finally:
        for f in [input_path, output_path, thumb_path]:
            if os.path.exists(f):
                os.remove(f)

# ---------------- RUN ----------------
app.run()
