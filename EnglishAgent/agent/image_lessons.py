"""DALL-E image-based lesson generation."""

from openai import OpenAI

# Prompt templates for discussing images by topic
IMAGE_LESSON_PROMPTS = {
    "animals": "I'm showing you a picture with animals. What animals can you see? Describe what they are doing!",
    "food": "Look at this picture of food! What dishes can you see? Which one would you like to try?",
    "colors": "Look at this colorful picture! What colors can you see? What is your favorite color here?",
    "family": "Look at this picture of a family! How many people do you see? What are they doing?",
    "travel": "Look at this beautiful place! Where do you think this is? Would you like to visit?",
    "weather": "Look at this picture! What is the weather like? What season do you think it is?",
    "sports": "Look at this picture! What sport is this? Do you like this sport?",
    "school": "Look at this classroom! What can you see? What is happening?",
    "body": "Look at this picture! Can you name the body parts you see?",
    "clothes": "Look at what these people are wearing! Can you describe their clothes?",
    "house": "Look at this house! How many rooms can you see? Describe what you see!",
    "city": "Look at this city! What buildings can you see? Is it busy or quiet?",
    "jobs": "Look at this person working! What is their job? Would you like this job?",
    "emotions": "Look at the faces in this picture! How do these people feel? Why do you think so?",
    "hobbies": "Look at this picture! What hobby is this? Do you enjoy doing this?",
    "transport": "Look at these vehicles! What types of transport can you see?",
    "nature": "Look at this beautiful nature scene! What do you see? Describe it!",
    "shopping": "Look at this shop! What can you buy here? What would you like to buy?",
    "health": "Look at this picture about health! What healthy activities do you see?",
    "technology": "Look at these gadgets! What technology can you see? Do you use any of these?",
}

# DALL-E prompt templates for generating topic images
IMAGE_GENERATION_PROMPTS = {
    "animals": "A colorful, child-friendly illustration of a zoo with various animals: elephant, giraffe, monkey, parrot, and dolphin. Bright, cheerful cartoon style.",
    "food": "A colorful illustration of a kitchen table with various foods: fruits, bread, cheese, salad, and a delicious cake. Warm, inviting cartoon style.",
    "colors": "An artist's studio with paint tubes, brushes, and a colorful rainbow canvas. Bright, vibrant illustration style.",
    "family": "A warm illustration of a happy diverse family having a picnic in a park. Friendly cartoon style.",
    "travel": "An illustrated travel scene with a plane, suitcase, map, and famous landmarks in the background. Adventure-themed cartoon style.",
    "weather": "A split illustration showing four seasons: sunny summer, rainy autumn, snowy winter, and blooming spring. Colorful cartoon style.",
    "sports": "An illustrated sports field with children playing different sports: football, basketball, tennis, and swimming. Active, dynamic cartoon style.",
    "school": "A bright, cheerful classroom illustration with students, books, a blackboard, and school supplies. Friendly cartoon style.",
    "nature": "A beautiful illustrated landscape with mountains, a river, forest, flowers, and a blue sky with clouds. Serene cartoon style.",
    "technology": "An illustrated desk with modern technology: laptop, smartphone, headphones, smartwatch, and a robot. Futuristic yet friendly cartoon style.",
}


def generate_lesson_image(client: OpenAI, topic: str) -> str | None:
    """Generate a DALL-E image for a topic lesson. Returns image URL."""
    prompt = IMAGE_GENERATION_PROMPTS.get(topic.lower())
    if not prompt:
        prompt = f"A colorful, child-friendly educational illustration about {topic}. Bright cartoon style, suitable for English learning."

    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        return response.data[0].url
    except Exception:
        return None


def get_image_question(topic: str) -> str:
    """Get the conversation prompt for discussing an image."""
    return IMAGE_LESSON_PROMPTS.get(
        topic.lower(),
        "Look at this picture! What do you see? Describe everything you notice!"
    )
