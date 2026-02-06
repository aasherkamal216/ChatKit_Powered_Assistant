# app/tools.py
from typing import Literal, List, Optional
from pydantic import BaseModel, Field
from agents import function_tool, RunContextWrapper
from chatkit.agents import AgentContext
from .widgets import (
    build_vibrant_weather_widget,
    build_clean_theme_widget,
    build_feedback_form,
)

from chatkit.widgets import Card, Title, Text, Button, Row
import json

# We define a global mapping of mock data for entity lookup
MOCK_ENTITIES = {
    "order_123": {
        "title": "Order #123",
        "status": "Shipped",
        "items": ["Laptop", "Mouse"],
    },
    "order_456": {"title": "Order #456", "status": "Processing", "items": ["Monitor"]},
}


@function_tool
async def get_weather(ctx: RunContextWrapper[AgentContext], location: str):
    """Get the current weather with a vibrant UI card."""
    # Realistically you'd call a weather API here
    widget = build_vibrant_weather_widget(
        location=location,
        temperature="72",
        condition_desc="Sunny sky and warm temperatures are expected for the rest of the afternoon.",
    )
    await ctx.context.stream_widget(widget)
    return f"Showed weather card for {location} with temperature {temperature} and condition: {condition_desc}:"


class FontSource(BaseModel):
    family: str = Field(description="The name of the font family")
    src: str = Field(description="The URL to the .woff2 font file")
    weight: int = Field(default=400, description="Font weight (e.g. 400, 700)")
    style: str = Field(default="normal", description="Font style (normal or italic)")
    display: str = Field(default="swap", description="CSS font-display property")


@function_tool
async def preview_theme(
    ctx: RunContextWrapper[AgentContext],
    reasoning: str,
    color_scheme: Literal["light", "dark"],
    radius: Literal["pill", "round", "soft", "sharp"],
    density: Literal["compact", "normal", "spacious"],
    accent_color: str,
    font_family: str,
    font_family_mono: str,
    font_sources: List[FontSource],  # Use the model list here
    accent_level: Literal[0, 1, 2, 3] = 2,
    base_font_size: Literal[14, 15, 16, 17, 18] = 16,
    grayscale_hue: int = 210,
):
    """
    Propose a fully customized UI theme including typography and external font loading.
    - reasoning: Explain why these fonts and colors match the requested style.
    - accent_color: Valid Hex code.
    - font_family: Full CSS font-family string.
    - font_sources: List of objects containing 'family' and 'src' (URL to .woff2).
    """
    theme_data = {
        "colorScheme": color_scheme,
        "radius": radius,
        "density": density,
        "typography": {
            "baseSize": base_font_size,
            "fontFamily": font_family,
            "fontFamilyMono": font_family_mono,
            "fontSources": font_sources,
        },
        "color": {
            "grayscale": {"hue": grayscale_hue, "tint": 8},
            "accent": {"primary": accent_color, "level": accent_level},
        },
    }

    widget = build_clean_theme_widget(reasoning, theme_data)
    await ctx.context.stream_widget(widget)
    return "Theme proposal with custom typography displayed."


@function_tool
async def show_feedback_form(ctx: RunContextWrapper[AgentContext]):
    """Display a feedback form to the user."""
    widget = build_feedback_form()
    await ctx.context.stream_widget(widget)
    return "Feedback form displayed."


@function_tool
async def get_order_details(ctx: RunContextWrapper[AgentContext], order_id: str):
    """Fetch details for a specific order ID (e.g. order_123). Use this format: order_xxx"""
    order = MOCK_ENTITIES.get(order_id)
    if order:
        return order
    return {"error": "Order not found"}
