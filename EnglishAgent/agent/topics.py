"""Topic-based lesson definitions with target vocabulary."""

TOPICS = {
    "animals": {
        "name": "Animals",
        "emoji": "🐾",
        "target_words": {
            "A1": ["cat", "dog", "bird", "fish", "horse", "cow", "pig", "sheep"],
            "A2": ["elephant", "giraffe", "monkey", "dolphin", "parrot", "turtle", "rabbit", "bear"],
            "B1": ["predator", "habitat", "endangered", "mammal", "species", "migration", "nocturnal", "camouflage"],
        },
        "prompt_suffix": "Conduct a lesson about animals. Use animal descriptions, sounds, and fun facts. Ask what animals the student likes and why.",
    },
    "food": {
        "name": "Food & Cooking",
        "emoji": "🍕",
        "target_words": {
            "A1": ["bread", "milk", "apple", "rice", "egg", "water", "sugar", "salt"],
            "A2": ["recipe", "delicious", "ingredients", "dessert", "spicy", "healthy", "meal", "snack"],
            "B1": ["cuisine", "nutritious", "savory", "appetite", "garnish", "marinate", "culinary", "seasoning"],
        },
        "prompt_suffix": "Conduct a lesson about food and cooking. Discuss favorite dishes, ingredients, and cooking methods. Use food vocabulary naturally.",
    },
    "colors": {
        "name": "Colors & Art",
        "emoji": "🎨",
        "target_words": {
            "A1": ["red", "blue", "green", "yellow", "white", "black", "pink", "orange"],
            "A2": ["purple", "grey", "brown", "bright", "dark", "light", "colorful", "paint"],
            "B1": ["turquoise", "crimson", "vivid", "palette", "shade", "contrast", "vibrant", "gradient"],
        },
        "prompt_suffix": "Conduct a lesson about colors and art. Describe objects by their colors, discuss art and creativity.",
    },
    "family": {
        "name": "Family & People",
        "emoji": "👨‍👩‍👧‍👦",
        "target_words": {
            "A1": ["mother", "father", "sister", "brother", "baby", "friend", "boy", "girl"],
            "A2": ["uncle", "aunt", "cousin", "grandparent", "neighbor", "teenager", "adult", "partner"],
            "B1": ["relative", "generation", "sibling", "ancestor", "heritage", "bond", "reunion", "nurture"],
        },
        "prompt_suffix": "Conduct a lesson about family and relationships. Ask about the student's family, discuss family activities and traditions.",
    },
    "travel": {
        "name": "Travel & Places",
        "emoji": "✈️",
        "target_words": {
            "A1": ["car", "bus", "train", "plane", "hotel", "map", "beach", "city"],
            "A2": ["airport", "passport", "luggage", "tourist", "adventure", "journey", "explore", "souvenir"],
            "B1": ["itinerary", "accommodation", "destination", "expedition", "nomadic", "excursion", "wanderlust", "immerse"],
        },
        "prompt_suffix": "Conduct a lesson about travel and places. Discuss dream destinations, travel experiences, and planning trips.",
    },
    "weather": {
        "name": "Weather & Seasons",
        "emoji": "🌤️",
        "target_words": {
            "A1": ["sun", "rain", "snow", "cold", "hot", "wind", "cloud", "warm"],
            "A2": ["storm", "thunder", "foggy", "humid", "freeze", "rainbow", "temperature", "forecast"],
            "B1": ["drought", "blizzard", "precipitation", "humidity", "climate", "atmosphere", "phenomenon", "monsoon"],
        },
        "prompt_suffix": "Conduct a lesson about weather and seasons. Discuss the weather today, seasonal activities, and climate differences.",
    },
    "sports": {
        "name": "Sports & Games",
        "emoji": "⚽",
        "target_words": {
            "A1": ["ball", "run", "swim", "jump", "play", "win", "team", "game"],
            "A2": ["football", "basketball", "tennis", "score", "champion", "athlete", "exercise", "compete"],
            "B1": ["tournament", "sportsmanship", "endurance", "agility", "referee", "spectator", "rivalry", "stamina"],
        },
        "prompt_suffix": "Conduct a lesson about sports and games. Discuss favorite sports, physical activities, and sports events.",
    },
    "school": {
        "name": "School & Education",
        "emoji": "📚",
        "target_words": {
            "A1": ["book", "pen", "teacher", "student", "class", "read", "write", "learn"],
            "A2": ["homework", "exam", "subject", "library", "science", "history", "project", "graduate"],
            "B1": ["curriculum", "scholarship", "academic", "discipline", "extracurricular", "thesis", "mentor", "seminar"],
        },
        "prompt_suffix": "Conduct a lesson about school and education. Discuss school subjects, learning habits, and educational experiences.",
    },
    "body": {
        "name": "Body & Health",
        "emoji": "🏃",
        "target_words": {
            "A1": ["head", "hand", "eye", "nose", "ear", "mouth", "leg", "arm"],
            "A2": ["stomach", "shoulder", "knee", "healthy", "exercise", "medicine", "doctor", "hospital"],
            "B1": ["immune", "symptom", "diagnosis", "posture", "metabolism", "rehabilitation", "chronic", "wellness"],
        },
        "prompt_suffix": "Conduct a lesson about the body and health. Name body parts, discuss healthy habits and staying fit.",
    },
    "clothes": {
        "name": "Clothes & Fashion",
        "emoji": "👔",
        "target_words": {
            "A1": ["shirt", "shoes", "hat", "dress", "coat", "socks", "bag", "pocket"],
            "A2": ["jacket", "sweater", "uniform", "fashion", "style", "comfortable", "elegant", "casual"],
            "B1": ["wardrobe", "accessory", "fabric", "tailored", "trendy", "sustainable", "versatile", "couture"],
        },
        "prompt_suffix": "Conduct a lesson about clothes and fashion. Describe outfits, discuss shopping for clothes and personal style.",
    },
    "house": {
        "name": "House & Home",
        "emoji": "🏠",
        "target_words": {
            "A1": ["door", "window", "bed", "table", "chair", "kitchen", "room", "floor"],
            "A2": ["bathroom", "bedroom", "garden", "furniture", "garage", "balcony", "stairs", "ceiling"],
            "B1": ["interior", "renovation", "appliance", "spacious", "cozy", "dwelling", "mortgage", "landlord"],
        },
        "prompt_suffix": "Conduct a lesson about houses and homes. Describe rooms, furniture, and discuss dream houses.",
    },
    "city": {
        "name": "City & Transport",
        "emoji": "🏙️",
        "target_words": {
            "A1": ["street", "shop", "park", "car", "bus", "road", "building", "bridge"],
            "A2": ["traffic", "station", "market", "museum", "restaurant", "subway", "downtown", "avenue"],
            "B1": ["infrastructure", "congestion", "metropolitan", "pedestrian", "commute", "suburb", "urbanization", "intersection"],
        },
        "prompt_suffix": "Conduct a lesson about city life and transportation. Discuss places in a city, giving directions, and urban life.",
    },
    "jobs": {
        "name": "Jobs & Work",
        "emoji": "💼",
        "target_words": {
            "A1": ["doctor", "teacher", "work", "job", "office", "shop", "cook", "drive"],
            "A2": ["engineer", "manager", "salary", "interview", "career", "colleague", "company", "experience"],
            "B1": ["entrepreneur", "qualification", "profession", "deadline", "promotion", "negotiate", "freelance", "corporate"],
        },
        "prompt_suffix": "Conduct a lesson about jobs and work. Discuss different professions, work experiences, and career goals.",
    },
    "emotions": {
        "name": "Emotions & Feelings",
        "emoji": "😊",
        "target_words": {
            "A1": ["happy", "sad", "angry", "scared", "tired", "love", "like", "cry"],
            "A2": ["excited", "nervous", "surprised", "disappointed", "proud", "jealous", "grateful", "lonely"],
            "B1": ["overwhelmed", "nostalgic", "empathy", "frustration", "contentment", "resilience", "melancholy", "euphoria"],
        },
        "prompt_suffix": "Conduct a lesson about emotions and feelings. Discuss different situations and how they make us feel. Practice expressing emotions in English.",
    },
    "hobbies": {
        "name": "Hobbies & Free Time",
        "emoji": "🎸",
        "target_words": {
            "A1": ["music", "dance", "draw", "sing", "play", "watch", "read", "cook"],
            "A2": ["photography", "gardening", "collect", "puzzle", "painting", "camping", "hiking", "volunteer"],
            "B1": ["leisure", "pastime", "enthusiast", "craftsmanship", "improvise", "meditation", "pursuit", "amateur"],
        },
        "prompt_suffix": "Conduct a lesson about hobbies and free time. Discuss what the student enjoys doing, share hobby ideas, and practice related vocabulary.",
    },
    "transport": {
        "name": "Transport & Vehicles",
        "emoji": "🚂",
        "target_words": {
            "A1": ["car", "bus", "bike", "train", "boat", "walk", "fly", "drive"],
            "A2": ["motorcycle", "helicopter", "subway", "ferry", "ticket", "passenger", "pilot", "captain"],
            "B1": ["autonomous", "locomotive", "aviation", "navigation", "velocity", "turbulence", "acceleration", "emission"],
        },
        "prompt_suffix": "Conduct a lesson about transport and vehicles. Discuss different ways to travel, traffic, and transportation experiences.",
    },
    "nature": {
        "name": "Nature & Environment",
        "emoji": "🌿",
        "target_words": {
            "A1": ["tree", "flower", "water", "sun", "moon", "star", "river", "mountain"],
            "A2": ["forest", "ocean", "desert", "jungle", "volcano", "island", "valley", "waterfall"],
            "B1": ["ecosystem", "biodiversity", "conservation", "sustainable", "erosion", "deforestation", "renewable", "carbon"],
        },
        "prompt_suffix": "Conduct a lesson about nature and the environment. Discuss natural wonders, ecology, and how to protect the planet.",
    },
    "shopping": {
        "name": "Shopping & Money",
        "emoji": "🛒",
        "target_words": {
            "A1": ["buy", "sell", "money", "cheap", "price", "shop", "pay", "gift"],
            "A2": ["discount", "receipt", "exchange", "cashier", "bargain", "refund", "customer", "expensive"],
            "B1": ["inflation", "budget", "investment", "transaction", "consumer", "merchandise", "wholesale", "negotiate"],
        },
        "prompt_suffix": "Conduct a lesson about shopping and money. Practice shopping dialogues, discuss prices, and shopping habits.",
    },
    "health": {
        "name": "Health & Wellness",
        "emoji": "🏥",
        "target_words": {
            "A1": ["sick", "cold", "hurt", "sleep", "eat", "water", "rest", "help"],
            "A2": ["fever", "allergy", "vitamin", "diet", "fitness", "nutrition", "checkup", "prescription"],
            "B1": ["therapy", "diagnosis", "preventive", "holistic", "chronic", "rehabilitation", "supplement", "immunity"],
        },
        "prompt_suffix": "Conduct a lesson about health and wellness. Discuss healthy habits, visiting a doctor, and staying well.",
    },
    "technology": {
        "name": "Technology & Internet",
        "emoji": "💻",
        "target_words": {
            "A1": ["phone", "computer", "game", "photo", "video", "music", "message", "search"],
            "A2": ["website", "internet", "download", "social media", "battery", "screen", "password", "update"],
            "B1": ["algorithm", "artificial intelligence", "cybersecurity", "innovation", "automation", "virtual reality", "startup", "bandwidth"],
        },
        "prompt_suffix": "Conduct a lesson about technology and the internet. Discuss gadgets, apps, and how technology changes our lives.",
    },
}


def get_topic_prompt(topic_name: str, level: str = "A2") -> str | None:
    """Get the prompt suffix for a topic with level-appropriate target words."""
    topic = TOPICS.get(topic_name.lower())
    if not topic:
        return None

    # Select words for the student's level and below
    levels = ["A1", "A2", "B1", "B2", "C1"]
    level_idx = levels.index(level) if level in levels else 1
    words = []
    for l in levels[: level_idx + 1]:
        words.extend(topic["target_words"].get(l, []))

    words_str = ", ".join(words[:12])  # limit to 12 words
    return (
        f"TOPIC: {topic['name']} {topic['emoji']}\n"
        f"Target vocabulary for this lesson: {words_str}\n"
        f"{topic['prompt_suffix']}\n"
        f"Try to naturally introduce and practice these words during the conversation."
    )


def list_topics() -> list[dict]:
    """Return list of topics with name and emoji."""
    return [
        {"key": k, "name": v["name"], "emoji": v["emoji"]}
        for k, v in TOPICS.items()
    ]
