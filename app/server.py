import io
import base64
import asyncio
import aiofiles
from pathlib import Path
from typing import AsyncIterator, Any, List
from datetime import datetime
from openai import AsyncOpenAI
from openai.types.responses import ResponseInputTextParam, ResponseInputImageParam
import os

from chatkit.server import ChatKitServer
from chatkit.types import (
    ThreadMetadata,
    UserMessageItem,
    ThreadStreamEvent,
    AssistantMessageItem,
    AssistantMessageContent,
    ThreadItemDoneEvent,
    AudioInput,
    TranscriptionResult,
    Action,
    WidgetItem,
    UserMessageTagContent,
    ImageAttachment,
    UserMessageTextContent,
    ProgressUpdateEvent,
    ClientEffectEvent,
    Annotation,
    URLSource,
)
from chatkit.agents import (
    AgentContext,
    stream_agent_response,
    ThreadItemConverter,
    ResponseStreamConverter,
    simple_to_agent_input,
)
from agents import Runner

from .types import RequestContext
from .agent import my_agent
from .tools import MOCK_ENTITIES

from dotenv import load_dotenv

load_dotenv()

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
UPLOAD_DIR = Path("uploads")


class LocalConverter(ThreadItemConverter):
    async def tag_to_message_content(
        self, tag: UserMessageTagContent
    ) -> ResponseInputTextParam:
        entity_id = tag.id
        entity_data = MOCK_ENTITIES.get(entity_id)

        if entity_data:
            context_block = (
                f"<ORDER_CONTEXT id='{entity_id}'>\n"
                f"  Title: {entity_data.get('title')}\n"
                f"  Status: {entity_data.get('status')}\n"
                f"  Items: {', '.join(entity_data.get('items', []))}\n"
                f"</ORDER_CONTEXT>"
            )
            return ResponseInputTextParam(
                type="input_text", text=f"\n[User tagged an entity]\n{context_block}\n"
            )

        return ResponseInputTextParam(
            type="input_text", text=f"\n[User tagged: {tag.text}]\n"
        )

    async def attachment_to_message_content(self, attachment):
        file_path = next(
            (f for f in UPLOAD_DIR.iterdir() if f.stem == attachment.id), None
        )
        if not file_path:
            return ResponseInputTextParam(type="input_text", text="[File not found]")

        async with aiofiles.open(file_path, "rb") as f:
            file_bytes = await f.read()

        if isinstance(attachment, ImageAttachment) or attachment.mime_type.startswith(
            "image/"
        ):
            b64 = base64.b64encode(file_bytes).decode("utf-8")
            return ResponseInputImageParam(
                type="input_image",
                detail="auto",
                image_url=f"data:{attachment.mime_type};base64,{b64}",
            )
        try:
            return ResponseInputTextParam(
                type="input_text",
                text=f"\n[File {attachment.name}]:\n{file_bytes.decode('utf-8')}\n",
            )
        except:
            return ResponseInputTextParam(
                type="input_text", text=f"[Binary file {attachment.name}]"
            )


class LocalResponseConverter(ResponseStreamConverter):
    async def base64_image_to_url(
        self, image_id: str, base64_image: str, partial_image_index: int | None = None
    ) -> str:
        return f"data:image/png;base64,{base64_image}"

    async def url_citation_to_annotation(self, citation) -> Annotation:
        return Annotation(
            source=URLSource(
                url=citation.url,
                title=citation.title or "Web Source",
            ),
            index=citation.end_index,
        )


class MyChatKitServer(ChatKitServer[RequestContext]):

    async def respond(
        self,
        thread: ThreadMetadata,
        input_message: UserMessageItem | None,
        context: RequestContext,
    ) -> AsyncIterator[ThreadStreamEvent]:

        # 1. Performance: Check for a previous response ID (Responses API State)
        # This prevents re-sending full history, making TTFT extremely fast.
        last_response_id = thread.metadata.get("last_response_id")

        # 2. If we have a stateful ID, we only need to send the NEW message.
        # Otherwise (first message), we send the history.
        if last_response_id and input_message:
            converter = LocalConverter()
            agent_inputs = await converter.to_agent_input([input_message])
        else:
            items_page = await self.store.load_thread_items(
                thread.id, None, 15, "desc", context
            )
            items = list(reversed(items_page.data))
            converter = LocalConverter()
            agent_inputs = await converter.to_agent_input(items)

        # 3. Handle Model Switching / Tool Forcing
        if input_message and input_message.inference_options:
            if input_message.inference_options.model:
                my_agent.model = input_message.inference_options.model
            if input_message.inference_options.tool_choice:
                my_agent.model_settings.tool_choice = (
                    input_message.inference_options.tool_choice.id
                )

        agent_context = AgentContext(
            thread=thread, store=self.store, request_context=context
        )

        # 4. Use the Responses API specialized runner
        # auto_previous_response_id ensures the SDK handles the chaining for us.
        result = Runner.run_streamed(
            my_agent,
            agent_inputs,
            context=agent_context,
            previous_response_id=last_response_id,
            auto_previous_response_id=True,
        )

        async for event in stream_agent_response(
            agent_context, result, converter=LocalResponseConverter(partial_images=3)
        ):
            yield event

        # Reset tool choice after response
        my_agent.model_settings.tool_choice = None
        my_agent.reset_tool_choice = True

        # 5. Performance: Capture and persist the new response ID for the next turn
        if result.last_response_id:
            thread.metadata["last_response_id"] = result.last_response_id
            await self.store.save_thread(thread, context)

        # Auto-title generation (non-blocking)
        if not thread.title and input_message:
            asyncio.create_task(
                self._generate_thread_title(thread, [input_message], context)
            )

    async def action(
        self,
        thread: ThreadMetadata,
        action: Action[str, Any],
        sender: WidgetItem | None,
        context: RequestContext,
    ) -> AsyncIterator[ThreadStreamEvent]:

        if action.type == "apply_theme_effect":
            yield ProgressUpdateEvent(text="Applying new styles...", icon="sparkle")
            yield ClientEffectEvent(name="update_ui_theme", data=action.payload)
            yield ThreadItemDoneEvent(
                item=AssistantMessageItem(
                    id=self.store.generate_item_id("message", thread, context),
                    thread_id=thread.id,
                    created_at=datetime.now(),
                    content=[
                        AssistantMessageContent(text="Theme updated successfully!")
                    ],
                )
            )
        elif action.type == "submit_feedback":
            yield ThreadItemDoneEvent(
                item=AssistantMessageItem(
                    id=self.store.generate_item_id("message", thread, context),
                    thread_id=thread.id,
                    created_at=datetime.now(),
                    content=[
                        AssistantMessageContent(text="Feedback received. Thank you!")
                    ],
                )
            )

    async def _generate_thread_title(
        self, thread: ThreadMetadata, items: List[Any], context: RequestContext
    ):
        try:
            first_text = "New Conversation"
            for item in items:
                if isinstance(item, UserMessageItem):
                    for part in item.content:
                        if isinstance(part, UserMessageTextContent):
                            first_text = part.text
                            break
                    break

            res = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "Summarize into a 3-word title. Text only.",
                    },
                    {"role": "user", "content": first_text},
                ],
            )
            thread.title = res.choices[0].message.content.strip().replace('"', "")
            await self.store.save_thread(thread, context)
        except:
            pass

    async def transcribe(
        self, audio_input: AudioInput, context: RequestContext
    ) -> TranscriptionResult:
        f = io.BytesIO(audio_input.data)
        f.name = "voice.webm"
        transcription = await client.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe", file=f
        )
        return TranscriptionResult(text=transcription.text)