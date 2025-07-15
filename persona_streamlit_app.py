
import streamlit as st
import praw
import os
from dotenv import load_dotenv
from openai import OpenAI
from jinja2 import Template
import re

# Load environment variables
load_dotenv()

# Initialize Reddit and OpenAI clients
reddit = praw.Reddit(
    client_id=st.secrets["REDDIT_CLIENT_ID"],
    client_secret=st.secrets["REDDIT_CLIENT_SECRET"],
    username=st.secrets["REDDIT_USERNAME"],
    password=st.secrets["REDDIT_PASSWORD"],
    user_agent=st.secrets["REDDIT_USER_AGENT"]
)

# Initialize OpenAI via OpenRouter
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=st.secrets["OPENROUTER_API_KEY"]
)

def query_llm(prompt):
    try:
        completion = client.chat.completions.create(
            model="mistralai/mistral-7b-instruct",
            extra_headers={
                "HTTP-Referer": "https://github.com/your-repo",
                "X-Title": "PersonaFinderApp"
            },
            messages=[
                {"role": "system", "content": "You are an expert persona analyst."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=2048,
            temperature=0.7
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        return f"[Error querying LLM: {str(e)}]"

def extract_section(text, header):
    pattern = rf"\*\*{re.escape(header)}:\*\*\s*(.*?)(?=\n\*\*|$)"
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1).strip() if match else ""

def extract_bullet_list(section_text):
    lines = section_text.splitlines()
    return [line.strip("•- ").strip() for line in lines if line.strip()]

def extract_key_value_pairs(section_text):
    items = []
    for line in section_text.splitlines():
        line = line.strip("•- ").strip()
        if "(" in line and ")" in line:
            parts = line.rsplit("(", 1)
            items.append((parts[0].strip(), parts[1].strip(")")))
        else:
            items.append((line, ""))
    return items

def parse_llm_response(response_text):
    parsed = {
        "motivations": extract_key_value_pairs(extract_section(response_text, "Motivations")),
        "frustrations": extract_key_value_pairs(extract_section(response_text, "Frustrations")),
        "behaviors": extract_key_value_pairs(extract_section(response_text, "Behavioral habits")),
        "goals": extract_bullet_list(extract_section(response_text, "Goals and needs")),
        "quote": extract_section(response_text, "Short quote").strip('"'),
        "age": extract_section(response_text, "Age"),
        "occupation": extract_section(response_text, "Occupation"),
        "status": extract_section(response_text, "Status"),
        "location": extract_section(response_text, "Location"),
        "archetype": extract_section(response_text, "Archetype"),
    }

    personality_line = extract_section(response_text, "Personality")
    parsed["personality_bars"] = generate_personality_bars(personality_line)
    return parsed

def generate_personality_bars(personality_text):
    traits = personality_text.split(",")
    scores = {}
    for trait in traits:
        match = re.match(r"(\d+)%\s+(\w+)", trait.strip())
        if match:
            percent = int(match.group(1))
            label = match.group(2).capitalize()
            scores[label] = percent

    def bar(left, right):
        left_score = scores.get(left.capitalize(), 0)
        bar_length = 20
        left_len = round(left_score / 100 * bar_length)
        right_len = bar_length - left_len
        return f"{left.upper():<11} [" + "■" * left_len + "-" * right_len + f"] {right.upper()}"

    return [
        bar("Introverted", "Extroverted"),
        bar("Intuitive", "Sensing"),
        bar("Feeling", "Thinking"),
        bar("Perceiving", "Judging"),
    ]

def build_persona(username):
    redditor = reddit.redditor(username)
    posts = []
    comments = []
    try:
        posts = [sub.title + " " + sub.selftext for sub in redditor.submissions.new(limit=20)]
        comments = [c.body for c in redditor.comments.new(limit=50)]
    except Exception as e:
        return None, f"Error accessing user data: {e}"

    all_text = "\n".join(posts + comments)
    if not all_text.strip():
        return None, "No data found for user."

    prompt = f"""
Given the following Reddit posts and comments from a user, infer:

- Motivations
- Frustrations
- Behavioral habits
- Personality traits (Analyze the personality based on the following text.
For each MBTI dimension show the dominant side of each of the 4 pairs, along with how strongly the person leans toward that side.
Format the output like this (example values):
52% Introverted, 25% Intuitive, 90% Feeling, 65% Perceiving
- Goals and needs
- Age (just a number or range, no reasoning. e.g., 18 or "20s" or Uknown if not determined)
- Occupation (just the job title, no reasoning. e.g., "Software Engineer" or Uknown if not determined)
- Marital Status (one of: Single, Married, Unknown — no explanation)
- Location (only the place name, no reasoning.)
- Archetype (just the archetype title, no reasoning. e.g., "The Explorer")
- Generate a short quote (less than 140 characters)

Text:
{all_text}

Respond clearly under each heading using bullet points. Use exactly these headings in bold:
**Motivations:**
**Frustrations:**
**Behavioral habits:**
**Personality:**
**Goals and needs:**
**Age:**
**Occupation:**
**Status:**
**Location:**
**Archetype:**
**Short quote:**
"""

    llm_response = query_llm(prompt)
    parsed_data = parse_llm_response(llm_response)
    parsed_data["name"] = username

    with open("templates/persona_template.txt", "r", encoding="utf-8") as f:
        template = Template(f.read())

    rendered = template.render(**parsed_data)
    file_path = f"personas/{username}_persona.txt"
    os.makedirs("personas", exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(rendered)

    return rendered, file_path

# === Streamlit UI ===
st.title("🧠 Persona Finder")
st.write("Analyze any Reddit user's behavior using AI!")

profile_url = st.text_input("Enter Reddit profile URL (e.g. https://www.reddit.com/user/kojied/)")

if st.button("🧬 Find Persona"):
    if not profile_url.startswith("https://www.reddit.com/user/"):
        st.error("Invalid URL. Please enter a valid Reddit user profile link.")
    else:
        username = profile_url.rstrip("/").split("/user/")[-1].split("/")[0]
        result_text, filepath = build_persona(username)
        if result_text:
            st.success("Persona generated!")
            st.text_area("Persona Report", result_text, height=600)
            with open(filepath, "rb") as f:
                st.download_button(label="📄 Download Persona File", data=f, file_name=os.path.basename(filepath))
        else:
            st.error("Failed to generate persona.")
