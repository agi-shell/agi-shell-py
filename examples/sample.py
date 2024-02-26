import os

from agishell.aigc import AIGC
from agishell.hardwares.audio130x import AudioModule
from agishell.llms.openai import ChatOpenAI
from agishell.llm import AGIShellLLM

# llm 初始化
llm = AGIShellLLM(ChatOpenAI())
llm.set_key(os.getenv("OPENAI_KEY"))
llm.set_server(os.getenv("OPENAI_PROXY_URL"))


# 硬件模块初始化
audio = AudioModule('COM3')


def msg_handler(msg):
    print("收到了消息：{0}".format(msg))
    print("内容处理...")
    print("开始调用LLM...")
    # llm.invoke(msg.content)
    print("完成")


# 调用
aigc = AIGC(audio, llm)
aigc.init()
aigc.hardware_data.subscribe(
    lambda i: msg_handler(i)
)
aigc.llm_invoke_start.subscribe(
    lambda i: print("开始调用LLM")
)

aigc.llm_invoke_end.subscribe(
    lambda i: print("结束调用LLM")
)

aigc.llm_invoke_result.subscribe(
    lambda i: print("调用LLM完成, 结果为: {0}".format(i))
)
aigc.run()
