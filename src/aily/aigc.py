import os
import asyncio
import sys
import random
import threading
import time
from reactivex.subject import Subject
from loguru import logger
from queue import SimpleQueue
from .hardwares.audio130x import AudioModule
from .llm import LLMs
from .tools import text_to_speech


class AIGC:
    # 事件
    wakeup = Subject()
    on_record_begin = Subject()
    on_record_end = Subject()
    on_play_begin = Subject()
    on_play_end = Subject()
    on_recognition = Subject()
    on_direction = Subject()
    on_invoke_start = Subject()
    on_invoke_end = Subject()

    audio_playlist_queue = SimpleQueue()
    llm_invoke_queue = SimpleQueue()
    event_queue = SimpleQueue()

    def __init__(self, port=None, baudrate: int = 1000000):
        self.port = port
        self.baudrate = baudrate

        self.hardware = None
        self.conversation_mode = "multi"

        self.audio_upload_cancel = False

        self.custom_llm_invoke = None
        self.llm = None
        self.llm_key = os.getenv("LLM_KEY")
        self.llm_model_name = os.getenv("LLM_MODEL_NAME", "gpt-3.5-turbo")
        self.llm_server = os.getenv("LLM_URL")
        self.llm_temperature = os.getenv("LLM_TEMPERATURE", 0.5)
        self.llm_pre_prompt = os.getenv("LLM_PRE_PROMPT")
        self.llm_max_token_length = os.getenv("LLM_MAX_TOKEN_LENGTH", 16384)

        self.wait_words_list = []
        self.wait_words_voice_list = []
        self.wait_words_init = True
        self.wait_words_voice_auto_play = True
        self.wait_words_data = bytearray()
        self.wait_words_voice_loop_play = False

        self.invalid_words = os.getenv("INVALID_WORDS")
        self.invalid_voice = None

        # 获取系统类型
        if sys.platform == "win32":
            self.root_path = "D://temp"
        else:
            self.root_path = "/tmp"

        self.wait_words_voice_path = self.root_path + "/wait_words_voice"

        # 最后对话时间
        self.last_conversation_time = 0
        # 聊天记录有效时间
        self.conversation_expired_at = 5 * 60

    def set_hardware(self, module):
        self.hardware = module

    def set_root_path(self, path):
        self.root_path = path

    def set_custom_llm_invoke(self, custom_invoke: callable):
        self.custom_llm_invoke = custom_invoke

    def clear_wait_words(self):
        self.wait_words_list.clear()

        if not os.path.exists(self.wait_words_voice_path):
            return

        for file in os.listdir(self.wait_words_voice_path):
            os.remove(self.wait_words_voice_path + "/" + file)

    def set_wait_words(self, words):
        if self.wait_words_init:
            self.wait_words_init = False
            self.clear_wait_words()

        self.wait_words_list.append(words)

    def set_wwords_auto_play(self, auto_play: bool):
        self.wait_words_voice_auto_play = auto_play

    def set_wwords_loop_play(self, loop_play: bool):
        self.wait_words_voice_loop_play = loop_play

    def set_expired_time(self, expired_time: int):
        self.conversation_expired_at = expired_time

    def _hardware_init(self):
        if self.hardware is None:
            self.hardware = AudioModule(self)
        self.hardware.set_conversation_mode(self.conversation_mode)
        self.hardware.init()

    def _llm_init(self):
        self.llm = LLMs(self)
        if self.custom_llm_invoke:
            self.llm.set_custom_invoke(self.custom_llm_invoke)

    def _init(self):
        # 初始化等待词
        if self.wait_words_list:
            logger.info("初始化等待词...")

            for words in self.wait_words_list:
                # 判断是纯文本还是语音文件地址
                if os.path.exists(words):
                    # self.wait_words_voice_list.append(words)
                    with open(words, "rb") as f:
                        data = f.read()
                        self.wait_words_voice_list.append(data)
                else:
                    # 将文字转为语音
                    speech_data = text_to_speech(words)
                    self.wait_words_voice_list.append(speech_data)
                    # filename = str(int(time.time() * 1000)) + ".mp3"
                    # save_path = self.wait_words_voice_path + "/" + filename
                    # with open(save_path, "wb") as f:
                    #     f.write(speech_data)
                    # self.wait_words_voice_list.append(save_path)

            logger.info("初始化等待词完成")

        # 读取默认
        if self.invalid_words:
            if os.path.exists(self.invalid_words):
                with open(self.invalid_words, "rb") as f:
                    self.invalid_voice = f.read()
            else:
                voice = text_to_speech(self.invalid_words)
                self.invalid_voice = voice

    def init(self):
        self._hardware_init()
        self._llm_init()
        self._init()

    def msg_handler(self):
        while True:
            if self.event_queue.empty():
                time.sleep(0.0001)
                continue

            event = self.event_queue.get()
            if event["type"] == "wakeup":
                self.wakeup.on_next(event["data"])
            elif event["type"] == "on_record_begin":
                self.on_record_begin.on_next(event["data"])
            elif event["type"] == "on_record_end":
                # 播放等待音频
                if self.wait_words_voice_auto_play:
                    self._auto_play_wait_words()
                self.on_record_end.on_next(event["data"])
            elif event["type"] == "on_play_begin":
                self.on_play_begin.on_next(event["data"])
            elif event["type"] == "on_play_end":
                self.on_play_end.on_next(event["data"])
            elif event["type"] == "on_recognition":
                self.on_recognition.on_next(event["data"])
            elif event["type"] == "on_direction":
                self.on_direction.on_next(event["data"])
            elif event["type"] == "on_invoke_start":
                self.on_invoke_start.on_next(event["data"])
            elif event["type"] == "on_invoke_end":
                self.on_invoke_end.on_next(event["data"])
            else:
                pass

    def set_conversation_mode(self, mode):
        self.conversation_mode = mode

    def play_wait_words(self, data):
        self.audio_playlist_queue.put({"type": "play_wait_words", "data": data})

    def play_invalid_words(self):
        if self.invalid_voice:
            self.audio_playlist_queue.put({"type": "play_mp3", "data": self.invalid_voice})
        else:
            logger.warning("未设置无效词")

    def _auto_play_wait_words(self):
        if self.wait_words_voice_list:
            words_index = random.randint(0, len(self.wait_words_voice_list) - 1)
            self.play_wait_words(self.wait_words_voice_list[words_index])
            # with open(self.wait_words_voice_list[words_index], "rb") as f:
            #     data = f.read()
            # self.play_wait_words(data)
        else:
            logger.warning("未设置等待词")

    def send_message(self, content):
        if not content:
            self.play_invalid_words()
        else:
            # 聊天记录过期清理
            if time.time() - self.last_conversation_time > 60 * 60 * 24:
                self.llm.clear_chat_records()
                self.last_conversation_time = time.time()
            self.llm_invoke_queue.put({"type": "invoke", "data": content})

    def set_key(self, key):
        if self.llm:
            self.llm.set_key(key)
        self.llm_key = key

    def set_model(self, model_name):
        if self.llm:
            self.llm.set_model(model_name)
        self.llm_model_name = model_name

    def set_server(self, url):
        if self.llm:
            self.llm.set_server(url)
        self.llm_server = url

    def set_temp(self, temperature):
        if self.llm:
            self.llm.set_temp(temperature)
        self.llm_temperature = temperature

    def set_pre_prompt(self, pre_prompt):
        if self.llm:
            self.llm.set_pre_prompt(pre_prompt)
        self.llm_pre_prompt = pre_prompt

    def play(self, data):
        self.audio_playlist_queue.put({"type": "play_tts", "data": data})

    async def main(self):
        self.init()
        tasks = [
            threading.Thread(target=self.msg_handler, daemon=True),
            threading.Thread(target=self.llm.run, daemon=True),
        ]
        self.hardware.start()
        for task in tasks:
            task.start()

        self.hardware.join()
        for task in tasks:
            task.join()

    def run(self):
        loop = asyncio.get_event_loop()
        try:
            loop.run_until_complete(self.main())
        except KeyboardInterrupt as e:
            pass
        finally:
            loop.close()
