from agents import Agent
from agents.tool import ImageGenerationTool, WebSearchTool
from .tools import get_weather, get_order_details, preview_theme

# Initialize Tools
image_tool = ImageGenerationTool(
    tool_config={"type": "image_generation", "partial_images": 3}
)
search_tool = WebSearchTool()  # Real web search via Responses API

my_agent = Agent(
    name="ProAssistant",
    instructions="""
    You are an advanced researcher and UI designer.
    - If asked to search the web, use the web_search tool.
    - Use other tools according to user request.

    - When customizing themes:
      1. TYPOGRAPHY:
        - Propose high-quality font pairings.
        - If the user wants 'Modern/Clean', use 'Inter' or 'Public Sans'.
        - If the user wants 'Elegant/Classic', use 'Lora' or 'Playfair Display'.
        - If the user wants 'Code/Tech', use 'JetBrains Mono' or 'Fira Code'.
        
      2. FONT SOURCES:
        - Use these WOFF2 URLs for your proposals:
          * Lora: https://fonts.gstatic.com/s/lora/v37/0QIvMX1D_JOuMwr7I_FMl_E.woff2
          * Inter: https://rsms.me/inter/font-files/Inter-Regular.woff2
          * JetBrains Mono: https://fonts.gstatic.com/s/jetbrainsmono/v23/tDbV2o-flEEny0FZhsfKu5WU4xD1OwGtT0rU3BE.woff2
          * OpenAI Sans: https://cdn.openai.com/common/fonts/openai-sans/v2/OpenAISans-Regular.woff2
        - Format font_sources as a list of: {"family": "Font Name", "src": "URL", "weight": 400, "style": "normal", "display": "swap"}
    """,
    model="gpt-5.1",
    tools=[search_tool, preview_theme, get_weather, get_order_details, image_tool],
)
