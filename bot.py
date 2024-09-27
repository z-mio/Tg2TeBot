import os
from collections import deque
from hashlib import md5

from pyrogram import Client, filters
from pyrogram.types import Message

from loguru import logger
from urllib.parse import urlparse
from dotenv import load_dotenv
from os import getenv
from tenacity import retry, stop_after_attempt
import httpx

load_dotenv()

channel_id = int(getenv("CHANNEL_ID"))
bot_token = getenv("BOT_TOKEN")
api_id = getenv("API_ID")
api_hash = getenv("API_HASH")

blog_url = getenv("BLOG_URL")
time_code = getenv("UNIQUECODE")
cid = getenv("CID")

lsky_url = getenv("LSKY_URL")
lsky_token = getenv("LSKY_TOKEN")

if proxy_url := getenv("PROXY", None):
    parsed_url = urlparse(proxy_url)
    proxy_url = {
        "scheme": parsed_url.scheme,
        "hostname": parsed_url.hostname,
        "port": parsed_url.port,
        "username": parsed_url.username,
        "password": parsed_url.password,
    }

app = Client(
    f'{bot_token.split(":")[0]}_bot',
    api_id=api_id,
    api_hash=api_hash,
    bot_token=bot_token,
    proxy=proxy_url,
)


@retry(stop=stop_after_attempt(3))
async def send_talk(content: str):
    body = {
        "content": content,
        "token": "crx",
        "time_code": md5(time_code.encode("utf-8")).hexdigest(),
        "action": "send_talk",
        "cid": cid,
        "mediaId": 1,
        "msg_type": "text",
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(
            blog_url,
            data=body,
        )
        response.raise_for_status()
        logger.info(response.text)


@retry(stop=stop_after_attempt(3))
async def upload_img(path: str):
    async with httpx.AsyncClient() as client:
        file = open(path, "rb")
        response = await client.post(
            f"{lsky_url}/api/v1/upload",
            headers={"Authorization": f"Bearer {lsky_token}"},
            files={"file": file},
        )
        response.raise_for_status()
        data = response.json()
        if not data["status"]:
            raise Exception(data["message"])
        file.close()
    return data["data"]["links"]["url"]


processed_media_groups = deque(maxlen=1)


async def media_group_filter(_, __, message):
    media_group_id = message.media_group_id
    if not media_group_id:
        return True
    if media_group_id not in processed_media_groups:
        processed_media_groups.append(media_group_id)
        return True


media_group_filter = filters.create(media_group_filter)


@app.on_message(filters.chat(channel_id) & media_group_filter)
async def post(_, msg: Message):
    msgs = await msg.get_media_group() if msg.media_group_id else [msg]
    m = msgs[0]
    caption = m.caption or m.text or ""
    if entities := (m.caption_entities or m.entities):
        caption = app.parser.unparse(caption, entities, True)

    imgs = []
    img = ""
    for msg in msgs:
        if msg.photo or msg.sticker:
            path = await msg.download()
            url = await upload_img(path)
            imgs.append(url)
            os.remove(path)

    if imgs:
        imgs = [f"<img src='{img}'/>" for img in imgs]
        img = "".join(imgs)

    if msgs[0].show_above_text:
        text = f"{caption}\n\n{img}"
    else:
        text = f"{img}\n\n{caption}"
    text = text.strip()

    if not text:
        return
    text += f"\n\n> [原文]({m.link})"
    await send_talk(text)
    logger.success(f"已发送：{m.link}")


if __name__ == "__main__":
    logger.success("Bot开始运行...")
    app.run()
