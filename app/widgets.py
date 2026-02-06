from chatkit.widgets import (
    Card,
    Text,
    Button,
    Row,
    Col,
    Title,
    Image,
    Caption,
    Box,
    Spacer,
)


def build_vibrant_weather_widget(location: str, temperature: str, condition_desc: str):
    """Builds the high-fidelity weather card."""
    return Card(
        theme="dark",
        size="sm",
        padding={"y": 8, "x": 4},
        background="linear-gradient(111deg, #1769C8 0%, #258AE3 56.92%, #31A3F8 100%)",
        children=[
            Col(
                align="center",
                gap=2,
                children=[
                    Row(
                        align="center",
                        gap=2,
                        children=[
                            Image(
                                src="https://cdn.openai.com/API/storybook/mostly-sunny.png",
                                size=80,
                            ),
                            Title(
                                value=f"{temperature}°",
                                size="5xl",
                                weight="normal",
                                color="white",
                            ),
                        ],
                    ),
                    Col(
                        align="center",
                        gap=4,
                        children=[
                            Caption(value=location, color="white", size="lg"),
                            Text(
                                value=condition_desc, color="white", textAlign="center"
                            ),
                        ],
                    ),
                ],
            )
        ],
    )


def build_clean_theme_widget(reasoning: str, theme_data: dict):
    """Builds a compact theme proposal card with a color swatch."""
    accent_color = theme_data.get("color", {}).get("accent", {}).get("primary", "#ccc")

    return Card(
        size="sm",
        children=[
            Row(
                align="center",
                gap=3,
                children=[
                    Box(size=32, background=accent_color, radius="sm"),
                    Col(
                        children=[
                            Title(value="New Style Proposal", size="sm"),
                            Caption(
                                value=f"{theme_data['colorScheme'].title()} mode · {theme_data['radius']} edges"
                            ),
                        ]
                    ),
                ],
            ),
            Spacer(minSize=12),  # Added margin
            Text(value=reasoning, size="sm", color="secondary"),
            Spacer(minSize=8),
            Button(
                label="Apply Theme",
                block=True,
                onClickAction={"type": "apply_theme_effect", "payload": theme_data},
            ),
        ],
    )


def build_feedback_form():
    """Builds an interactive form."""
    return Card(
        asForm=True,
        children=[
            Form(
                onSubmitAction={
                    "type": "submit_feedback",
                    "payload": {},  # Form inputs auto-merge into payload
                },
                children=[
                    Title(value="Feedback"),
                    Text(value="How was your experience today?"),
                    Input(
                        name="user_comment", placeholder="Type here...", required=True
                    ),
                    Button(label="Submit Feedback", submit=True),
                ],
            )
        ],
    )
