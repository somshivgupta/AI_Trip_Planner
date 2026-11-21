
import streamlit as st
import requests
import uuid

BASE_URL = "http://localhost:8000"

st.set_page_config(
    page_title="Travel Planner Agent",
    page_icon="🗺️",
    layout="centered",
    initial_sidebar_state="expanded"
)

# ---------------- SESSION STATE ----------------

if "messages" not in st.session_state:
    st.session_state.messages = []

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

# ---------------- SIDEBAR ----------------

with st.sidebar:
    st.title("🧭 Travel Planner")

    if st.button("＋ New Chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.thread_id = str(uuid.uuid4())
        st.rerun()

    st.divider()
    st.caption("Your AI-powered travel assistant")

# ---------------- MAIN CHAT ----------------

st.title("🗺️ Travel Planner")

if not st.session_state.messages:
    st.markdown("### How can I help you plan your next trip?")
    st.caption("Ask me about destinations, itineraries, weather, budgets and more.")

# Display previous conversation
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat input stays at the bottom
user_input = st.chat_input("Ask me anything about your trip...")

if user_input and user_input.strip():

    # Store and display user message
    st.session_state.messages.append({
        "role": "user",
        "content": user_input
    })

    with st.chat_message("user"):
        st.markdown(user_input)

    # Generate assistant response
    with st.chat_message("assistant"):
        with st.spinner("Planning your trip..."):
            try:
                payload = {
                    "question": user_input,
                    "thread_id": st.session_state.thread_id
                }

                response = requests.post(
                    f"{BASE_URL}/query",
                    json=payload,
                    timeout=180
                )

                if response.status_code == 200:
                    answer = response.json().get(
                        "answer",
                        "No answer returned."
                    )

                    st.markdown(answer)

                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": answer
                    })

                else:
                    error_message = (
                        f"Request failed ({response.status_code}): "
                        f"{response.text}"
                    )
                    st.error(error_message)

            except requests.exceptions.Timeout:
                st.error(
                    "The request timed out. Please try again."
                )

            except requests.exceptions.RequestException as e:
                st.error(f"Could not connect to the API: {e}")

            except Exception as e:
                st.error(f"An unexpected error occurred: {e}")

# ---------------- DISCLAIMER ----------------

st.divider()
st.caption(
    "AI-generated travel information may contain errors. "
    "Please verify prices, availability and travel details before booking."
)