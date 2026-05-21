import asyncio
import os
import time
import uuid
from collections.abc import AsyncGenerator

import streamlit as st
from dotenv import load_dotenv
from pydantic import ValidationError

from client import AgentClient, AgentClientError
from schema import ChatHistory, ChatMessage
from schema.task_data import TaskData, TaskDataStatus
from voice import VoiceManager

# A Streamlit app for interacting with the langgraph agent via a simple chat interface.
# The app has three main functions which are all run async:

# - main() - sets up the streamlit app and high level structure
# - draw_messages() - draws a set of chat messages - either replaying existing messages
#   or streaming new ones.
# - handle_feedback() - Draws a feedback widget and records feedback from the user.

# The app heavily uses AgentClient to interact with the agent's FastAPI endpoints.


APP_TITLE = "智能服务平台"
APP_ICON = "✨"
USER_ID_COOKIE = "user_id"


def coerce_chat_message(message: object) -> ChatMessage | None:
    """Accept ChatMessage objects even after Streamlit reloads modules."""
    if isinstance(message, ChatMessage):
        return message
    try:
        if hasattr(message, "model_dump"):
            return ChatMessage.model_validate(message.model_dump())
        if isinstance(message, dict):
            return ChatMessage.model_validate(message)
    except ValidationError:
        return None
    return None


def get_chat_title(messages: list[ChatMessage]) -> str:
    for message in messages:
        if message.type == "human" and message.content.strip():
            title = message.content.strip().replace("\n", " ")
            return title[:24] + ("..." if len(title) > 24 else "")
    return "新对话"


def save_current_chat() -> None:
    thread_id = st.session_state.get("thread_id")
    messages = st.session_state.get("messages")
    if not thread_id or messages is None:
        return
    if "chat_sessions" not in st.session_state:
        st.session_state.chat_sessions = {}
    if "chat_session_order" not in st.session_state:
        st.session_state.chat_session_order = []
    if "chat_session_meta" not in st.session_state:
        st.session_state.chat_session_meta = {}
    st.session_state.chat_sessions[thread_id] = list(messages)
    st.session_state.chat_session_meta[thread_id] = {
        "title": get_chat_title(messages),
        "updated_at": time.time(),
    }
    if thread_id not in st.session_state.chat_session_order:
        st.session_state.chat_session_order.insert(0, thread_id)


def get_or_create_user_id() -> str:
    """Get the user ID from session state or URL parameters, or create a new one if it doesn't exist."""
    # Check if user_id exists in session state
    if USER_ID_COOKIE in st.session_state:
        return st.session_state[USER_ID_COOKIE]

    # Try to get from URL parameters using the new st.query_params
    if USER_ID_COOKIE in st.query_params:
        user_id = st.query_params[USER_ID_COOKIE]
        st.session_state[USER_ID_COOKIE] = user_id
        return user_id

    # Generate a new user_id if not found
    user_id = str(uuid.uuid4())

    # Store in session state for this session
    st.session_state[USER_ID_COOKIE] = user_id

    # Also add to URL parameters so it can be bookmarked/shared
    st.query_params[USER_ID_COOKIE] = user_id

    return user_id


def get_agent_url() -> str:
    agent_url = os.getenv("AGENT_URL")
    if agent_url:
        return agent_url
    host = os.getenv("HOST", "0.0.0.0")
    port = os.getenv("PORT", 8080)
    return f"http://{host}:{port}"


def render_login(agent_url: str) -> None:
    st.markdown(f"## {APP_ICON} {APP_TITLE}")
    st.caption("请登录后继续使用")

    auth_client = AgentClient(base_url=agent_url, get_info=False)
    with st.form("login-form"):
        username = st.text_input("用户名", key="login-username")
        password = st.text_input("密码", type="password", key="login-password")
        submitted = st.form_submit_button("登录", use_container_width=True)
    if submitted:
        try:
            response = auth_client.login(username, password)
        except AgentClientError as e:
            st.error(str(e))
        else:
            st.session_state.auth_user = response.user.model_dump()
            st.rerun()


async def main() -> None:
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon=APP_ICON,
        menu_items={},
    )

    # Hide the streamlit upper-right chrome
    st.html(
        """
        <style>
        [data-testid="stStatusWidget"] {
                visibility: hidden;
                height: 0%;
                position: fixed;
            }
        </style>
        """,
    )
    if st.get_option("client.toolbarMode") != "minimal":
        st.set_option("client.toolbarMode", "minimal")
        await asyncio.sleep(0.1)
        st.rerun()

    load_dotenv()
    agent_url = get_agent_url()
    if "auth_user" not in st.session_state:
        render_login(agent_url)
        st.stop()

    user_id = st.session_state.auth_user["id"]
    st.session_state[USER_ID_COOKIE] = user_id
    st.query_params[USER_ID_COOKIE] = user_id

    if "agent_client" not in st.session_state:
        try:
            with st.spinner("正在连接智能体服务..."):
                st.session_state.agent_client = AgentClient(base_url=agent_url)
        except AgentClientError as e:
            st.error(f"连接智能体服务失败：{agent_url}，错误信息：{e}")
            st.markdown("服务可能仍在启动中，请稍等几秒后重试。")
            st.stop()
    agent_client: AgentClient = st.session_state.agent_client

    # Initialize voice manager (once per session)
    if "voice_manager" not in st.session_state:
        st.session_state.voice_manager = VoiceManager.from_env()
    voice = st.session_state.voice_manager

    if "thread_id" not in st.session_state:
        thread_id = st.query_params.get("thread_id")
        if not thread_id:
            thread_id = str(uuid.uuid4())
            messages = []
        else:
            try:
                messages: ChatHistory = agent_client.get_history(thread_id=thread_id).messages
            except AgentClientError:
                st.error("未找到此对话 ID 对应的历史消息。")
                messages = []
        st.session_state.messages = messages
        st.session_state.thread_id = thread_id
        save_current_chat()

    # Config options
    with st.sidebar:
        st.header(f"{APP_ICON} {APP_TITLE}")
        st.caption(f"当前用户：{st.session_state.auth_user['username']}")
        if st.button(":material/logout: 退出登录", use_container_width=True):
            for key in [
                "auth_user",
                "agent_client",
                "messages",
                "thread_id",
                "chat_sessions",
                "chat_session_order",
                "chat_session_meta",
                "last_audio",
            ]:
                st.session_state.pop(key, None)
            st.rerun()

        if st.button(":material/chat: 新建对话", use_container_width=True):
            save_current_chat()
            st.session_state.messages = []
            st.session_state.thread_id = str(uuid.uuid4())
            st.query_params["thread_id"] = st.session_state.thread_id
            # Clear saved audio when starting new chat
            if "last_audio" in st.session_state:
                del st.session_state.last_audio
            save_current_chat()
            st.rerun()

        with st.popover(":material/history: 对话历史", use_container_width=True):
            save_current_chat()
            cutoff = time.time() - 7 * 24 * 60 * 60
            recent_thread_ids = [
                saved_thread_id
                for saved_thread_id in st.session_state.get("chat_session_order", [])
                if st.session_state.get("chat_session_meta", {})
                .get(saved_thread_id, {})
                .get("updated_at", 0)
                >= cutoff
            ]
            if not recent_thread_ids:
                st.caption("最近一周暂无对话")
            for saved_thread_id in recent_thread_ids:
                saved_messages = st.session_state.chat_sessions.get(saved_thread_id, [])
                meta = st.session_state.chat_session_meta.get(saved_thread_id, {})
                title = meta.get("title") or get_chat_title(saved_messages)
                is_current = saved_thread_id == st.session_state.thread_id
                label = f":material/check: {title}" if is_current else title
                if st.button(label, key=f"history-{saved_thread_id}", use_container_width=True):
                    save_current_chat()
                    st.session_state.thread_id = saved_thread_id
                    st.session_state.messages = list(saved_messages)
                    st.query_params["thread_id"] = saved_thread_id
                    if "last_audio" in st.session_state:
                        del st.session_state.last_audio
                    st.rerun()

        with st.popover(":material/settings: 设置", use_container_width=True):
            model_idx = agent_client.info.models.index(agent_client.info.default_model)
            model = st.selectbox("选择大语言模型", options=agent_client.info.models, index=model_idx)
            agent_list = [a.key for a in agent_client.info.agents]
            agent_idx = agent_list.index(agent_client.info.default_agent)
            agent_client.agent = st.selectbox(
                "选择智能体",
                options=agent_list,
                index=agent_idx,
            )
            use_streaming = st.toggle("流式输出", value=True)
            # Audio toggle with callback: clears cached audio when toggled off
            enable_audio = st.toggle(
                "启用语音生成",
                value=True,
                disabled=not voice or not voice.tts,
                help="在 .env 中配置 VOICE_TTS_PROVIDER 后可启用"
                if not voice or not voice.tts
                else None,
                on_change=lambda: st.session_state.pop("last_audio", None)
                if not st.session_state.get("enable_audio", True)
                else None,
                key="enable_audio",
            )

            # Display user ID (for debugging or user information)
            st.text_input("用户 ID（只读）", value=user_id, disabled=True)

    # Draw existing messages
    messages: list[ChatMessage] = st.session_state.messages

    if len(messages) == 0:
        match agent_client.agent:
            case "chatbot":
                WELCOME = "你好！我是一个简单的聊天机器人，可以问我任何问题。"
            case "interrupt-agent":
                WELCOME = "你好！我是一个支持中断流程的智能体。告诉我你的生日，我可以为你预测性格。"
            case "research-assistant":
                WELCOME = "你好！我是 AI 研究助手，支持网页搜索和计算器。可以问我任何问题。"
            case "rag-assistant":
                WELCOME = """你好！我是 AI 公司政策与人力资源助手，可以查询 AcmeTech 员工手册。
                我可以帮你查找福利、远程办公、休假政策、公司价值观等信息。"""
            case _:
                WELCOME = "你好！我是 AI 智能体，可以问我任何问题。"

        with st.chat_message("ai"):
            st.write(WELCOME)

    # draw_messages() expects an async iterator over messages
    async def amessage_iter() -> AsyncGenerator[ChatMessage, None]:
        for m in messages:
            yield m

    await draw_messages(amessage_iter())

    # Render saved audio for the last AI message (if it exists)
    # This ensures audio persists across st.rerun() calls
    if (
        voice
        and enable_audio
        and "last_audio" in st.session_state
        and st.session_state.last_message
        and len(messages) > 0
        and messages[-1].type == "ai"
    ):
        with st.session_state.last_message:
            audio_data = st.session_state.last_audio
            st.audio(audio_data["data"], format=audio_data["format"])

    # Generate new message if the user provided new input
    # Use voice manager if available, otherwise fall back to regular input
    # REQUIRED: Set VOICE_STT_PROVIDER, VOICE_TTS_PROVIDER, OPENAI_API_KEY
    # in app .env (NOT service .env) to enable voice features.
    if voice:
        user_input = voice.get_chat_input("请输入你的问题")
    else:
        user_input = st.chat_input("请输入你的问题")

    if user_input:
        messages.append(ChatMessage(type="human", content=user_input))
        st.chat_message("human").write(user_input)
        try:
            if use_streaming:
                stream = agent_client.astream(
                    message=user_input,
                    model=model,
                    thread_id=st.session_state.thread_id,
                    user_id=user_id,
                )
                await draw_messages(stream, is_new=True)
                # Generate TTS audio for streaming response
                # Note: draw_messages() stores the final message in st.session_state.messages
                # and the container reference in st.session_state.last_message
                if voice and enable_audio and st.session_state.messages:
                    last_msg = st.session_state.messages[-1]
                    # Only generate audio for AI responses with content
                    if last_msg.type == "ai" and last_msg.content:
                        # Use audio_only=True since text was already streamed by draw_messages()
                        voice.render_message(
                            last_msg.content,
                            container=st.session_state.last_message,
                            audio_only=True,
                        )
            else:
                response = await agent_client.ainvoke(
                    message=user_input,
                    model=model,
                    thread_id=st.session_state.thread_id,
                    user_id=user_id,
                )
                messages.append(response)
                # Render AI response with optional voice
                with st.chat_message("ai"):
                    if voice and enable_audio:
                        voice.render_message(response.content)
                    else:
                        st.write(response.content)
            save_current_chat()
            st.rerun()  # Clear stale containers
        except AgentClientError as e:
            st.error(f"生成回复失败：{e}")
            st.stop()

    # If messages have been generated, show feedback widget
    if len(messages) > 0 and st.session_state.last_message:
        with st.session_state.last_message:
            await handle_feedback()


async def draw_messages(
    messages_agen: AsyncGenerator[ChatMessage | str, None],
    is_new: bool = False,
) -> None:
    """
    Draws a set of chat messages - either replaying existing messages
    or streaming new ones.

    This function has additional logic to handle streaming tokens and tool calls.
    - Use a placeholder container to render streaming tokens as they arrive.
    - Use a status container to render tool calls. Track the tool inputs and outputs
      and update the status container accordingly.

    The function also needs to track the last message container in session state
    since later messages can draw to the same container. This is also used for
    drawing the feedback widget in the latest chat message.

    Args:
        messages_aiter: An async iterator over messages to draw.
        is_new: Whether the messages are new or not.
    """

    # Keep track of the last message container
    last_message_type = None
    st.session_state.last_message = None

    # Placeholder for intermediate streaming tokens
    streaming_content = ""
    streaming_placeholder = None

    # Iterate over the messages and draw them
    while msg := await anext(messages_agen, None):
        # str message represents an intermediate token being streamed
        if isinstance(msg, str):
            # If placeholder is empty, this is the first token of a new message
            # being streamed. We need to do setup.
            if not streaming_placeholder:
                if last_message_type != "ai":
                    last_message_type = "ai"
                    st.session_state.last_message = st.chat_message("ai")
                with st.session_state.last_message:
                    streaming_placeholder = st.empty()

            streaming_content += msg
            streaming_placeholder.write(streaming_content)
            continue
        coerced_msg = coerce_chat_message(msg)
        if coerced_msg is None:
            st.error(f"收到不支持的消息类型：{type(msg)}")
            st.write(msg)
            st.stop()
        msg = coerced_msg

        match msg.type:
            # A message from the user, the easiest case
            case "human":
                last_message_type = "human"
                st.chat_message("human").write(msg.content)

            # A message from the agent is the most complex case, since we need to
            # handle streaming tokens and tool calls.
            case "ai":
                # If we're rendering new messages, store the message in session state
                if is_new:
                    st.session_state.messages.append(msg)

                # If the last message type was not AI, create a new chat message
                if last_message_type != "ai":
                    last_message_type = "ai"
                    st.session_state.last_message = st.chat_message("ai")

                with st.session_state.last_message:
                    # If the message has content, write it out.
                    # Reset the streaming variables to prepare for the next message.
                    if msg.content:
                        if streaming_placeholder:
                            streaming_placeholder.write(msg.content)
                            streaming_content = ""
                            streaming_placeholder = None
                        else:
                            st.write(msg.content)

                    if msg.tool_calls:
                        # Create a status container for each tool call and store the
                        # status container by ID to ensure results are mapped to the
                        # correct status container.
                        call_results = {}
                        for tool_call in msg.tool_calls:
                            # Use different labels for transfer vs regular tool calls
                            if "transfer_to" in tool_call["name"]:
                                label = f"""子智能体：{tool_call["name"]}"""
                            else:
                                label = f"""工具调用：{tool_call["name"]}"""

                            status = st.status(
                                label,
                                state="running" if is_new else "complete",
                            )
                            call_results[tool_call["id"]] = status

                        # Expect one ToolMessage for each tool call.
                        for tool_call in msg.tool_calls:
                            if "transfer_to" in tool_call["name"]:
                                status = call_results[tool_call["id"]]
                                status.update(expanded=True)
                                await handle_sub_agent_msgs(messages_agen, status, is_new)
                                break

                            # Only non-transfer tool calls reach this point
                            status = call_results[tool_call["id"]]
                            status.write("输入：")
                            status.write(tool_call["args"])
                            tool_result_raw = await anext(messages_agen)
                            tool_result = coerce_chat_message(tool_result_raw)

                            if tool_result is None or tool_result.type != "tool":
                                message_type = getattr(tool_result_raw, "type", type(tool_result_raw))
                                st.error(f"收到不支持的对话消息类型：{message_type}")
                                st.write(tool_result_raw)
                                st.stop()

                            # Record the message if it's new, and update the correct
                            # status container with the result
                            if is_new:
                                st.session_state.messages.append(tool_result)
                            if tool_result.tool_call_id:
                                status = call_results[tool_result.tool_call_id]
                            status.write("输出：")
                            status.write(tool_result.content)
                            status.update(state="complete")

            case "custom":
                # CustomData example used by the bg-task-agent
                # See:
                # - src/agents/utils.py CustomData
                # - src/agents/bg_task_agent/task.py
                try:
                    task_data: TaskData = TaskData.model_validate(msg.custom_data)
                except ValidationError:
                    st.error("从智能体收到不支持的自定义数据消息")
                    st.write(msg.custom_data)
                    st.stop()

                if is_new:
                    st.session_state.messages.append(msg)

                if last_message_type != "task":
                    last_message_type = "task"
                    st.session_state.last_message = st.chat_message(
                        name="task", avatar=":material/manufacturing:"
                    )
                    with st.session_state.last_message:
                        status = TaskDataStatus()

                status.add_and_draw_task_data(task_data)

            # In case of an unexpected message type, log an error and stop
            case _:
                st.error(f"收到不支持的对话消息类型：{msg.type}")
                st.write(msg)
                st.stop()


async def handle_feedback() -> None:
    """Draws a feedback widget and records feedback from the user."""

    # Keep track of last feedback sent to avoid sending duplicates
    if "last_feedback" not in st.session_state:
        st.session_state.last_feedback = (None, None)

    latest_run_id = st.session_state.messages[-1].run_id
    feedback = st.feedback("stars", key=latest_run_id)

    # If the feedback value or run ID has changed, send a new feedback record
    if feedback is not None and (latest_run_id, feedback) != st.session_state.last_feedback:
        # Normalize the feedback value (an index) to a score between 0 and 1
        normalized_score = (feedback + 1) / 5.0

        agent_client: AgentClient = st.session_state.agent_client
        try:
            await agent_client.acreate_feedback(
                run_id=latest_run_id,
                key="human-feedback-stars",
                score=normalized_score,
                kwargs={"comment": "In-line human feedback"},
            )
        except AgentClientError as e:
            st.error(f"记录反馈失败：{e}")
            st.stop()
        st.session_state.last_feedback = (latest_run_id, feedback)
        st.toast("反馈已记录", icon=":material/reviews:")


async def handle_sub_agent_msgs(messages_agen, status, is_new):
    """
    This function segregates agent output into a status container.
    It handles all messages after the initial tool call message
    until it reaches the final AI message.

    Enhanced to support nested multi-agent hierarchies with handoff back messages.

    Args:
        messages_agen: Async generator of messages
        status: the status container for the current agent
        is_new: Whether messages are new or replayed
    """
    nested_popovers = {}

    # looking for the transfer Success tool call message
    first_msg = await anext(messages_agen)
    if is_new:
        st.session_state.messages.append(first_msg)

    # Continue reading until we get an explicit handoff back
    while True:
        # Read next message
        sub_msg = await anext(messages_agen)

        # this should only happen is skip_stream flag is removed
        # if isinstance(sub_msg, str):
        #     continue

        if is_new:
            st.session_state.messages.append(sub_msg)

        # Handle tool results with nested popovers
        if sub_msg.type == "tool" and sub_msg.tool_call_id in nested_popovers:
            popover = nested_popovers[sub_msg.tool_call_id]
            popover.write("**输出：**")
            popover.write(sub_msg.content)
            continue

        # Handle transfer_back_to tool calls - these indicate a sub-agent is returning control
        if (
            hasattr(sub_msg, "tool_calls")
            and sub_msg.tool_calls
            and any("transfer_back_to" in tc.get("name", "") for tc in sub_msg.tool_calls)
        ):
            # Process transfer_back_to tool calls
            for tc in sub_msg.tool_calls:
                if "transfer_back_to" in tc.get("name", ""):
                    # Read the corresponding tool result
                    transfer_result = await anext(messages_agen)
                    if is_new:
                        st.session_state.messages.append(transfer_result)

            # After processing transfer back, we're done with this agent
            if status:
                status.update(state="complete")
            break

        # Display content and tool calls in the same nested status
        if status:
            if sub_msg.content:
                status.write(sub_msg.content)

            if hasattr(sub_msg, "tool_calls") and sub_msg.tool_calls:
                for tc in sub_msg.tool_calls:
                    # Check if this is a nested transfer/delegate
                    if "transfer_to" in tc["name"]:
                        # Create a nested status container for the sub-agent
                        nested_status = status.status(
                            f"""子智能体：{tc["name"]}""",
                            state="running" if is_new else "complete",
                            expanded=True,
                        )

                        # Recursively handle sub-agents of this sub-agent
                        await handle_sub_agent_msgs(messages_agen, nested_status, is_new)
                    else:
                        # Regular tool call - create popover
                        popover = status.popover(f"{tc['name']}", icon="🛠️")
                        popover.write(f"**工具：** {tc['name']}")
                        popover.write("**输入：**")
                        popover.write(tc["args"])
                        # Store the popover reference using the tool call ID
                        nested_popovers[tc["id"]] = popover


if __name__ == "__main__":
    asyncio.run(main())
