"""Topics suggested in the topic field: our own A-Z list, plus the topic names of the
tests imported from your books (they stay on your computer). The examiner writes the
questions for a topic. (The "By letter" mode uses the topic cards of
eslconversationquestions.com instead, downloaded by you: see esl.py.)
"""
from . import books

TOPICS = [
    "Advertising", "Animals", "Apps", "Architecture", "Art",
    "Bicycles", "Birthdays", "Books", "Breakfast", "Business",
    "Cars", "Celebrities", "Childhood", "Cities", "Climate change", "Clothes", "Colours", "Cooking",
    "Daily routine", "Dancing", "Decisions", "Dreams",
    "Education", "Emails", "Energy", "Environment", "Exercise",
    "Family", "Fashion", "Films", "Food", "Friends", "Furniture", "Future",
    "Gardens", "Gifts", "Goals", "Games",
    "Health", "Helping others", "History", "Hobbies", "Holidays", "Home", "Hometown",
    "Ideas", "Internet", "Inventions",
    "Jobs", "Journeys",
    "Kindness", "Kitchens",
    "Languages", "Leisure", "Libraries", "Lifestyle",
    "Maps", "Markets", "Memories", "Money", "Museums", "Music",
    "Nature", "Neighbours", "News", "Noise",
    "Old age", "Online shopping", "Outdoor activities",
    "Parks", "Patience", "Pets", "Photography", "Plans", "Public transport",
    "Queues", "Quiet places",
    "Reading", "Recycling", "Relaxing", "Restaurants", "Rules",
    "Science", "Seasons", "Shopping", "Skills", "Sleep", "Social media", "Sport", "Success",
    "Teachers", "Technology", "Television", "Time management", "Tourism", "Traditions", "Travel",
    "Uniforms", "Universities",
    "Volunteering", "Vacations",
    "Water", "Weather", "Weekends", "Work",
    "Young people", "Yoga",
    "Zoos",
]


def all_topics() -> list[dict]:
    """Our topics and your books' topic names, A-Z, without repeats."""
    found = {t.lower(): {"name": t, "source": "app"} for t in TOPICS}
    for book in books.load_books():
        for test in book["tests"]:
            for part in ("part1", "part3"):
                for t in test[part]:
                    name = t["topic"].strip().rstrip(".")
                    name = name[:1].upper() + name[1:]
                    if 2 < len(name) <= 40:
                        found.setdefault(name.lower(), {"name": name, "source": "books"})
    return sorted(found.values(), key=lambda t: t["name"].lower())
