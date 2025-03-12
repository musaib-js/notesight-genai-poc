import streamlit as st
import requests

def extract_topics(uploaded_files, selected_model):
    """Uploads files and extracts key topics."""
    files = [("files", (file.name, file, "application/pdf")) for file in uploaded_files]
    data = {"model": selected_model}

    with st.spinner(f"Extracting key topics using {selected_model.capitalize()}... ⏳"):
        response = requests.post(f"{BASE_URL}/mcqs/", files=files, data=data)

    if response.status_code == 200:
        response_data = response.json()
        st.session_state["topics"] = response_data.get("topics", [])
        st.session_state["file_paths"] = response_data.get("file_paths", [])

        if st.session_state["topics"]:
            st.success("✅ Topics extracted successfully! Select topics below.")
        else:
            st.warning("⚠ No topics found in the document.")
    else:
        st.error("❌ Failed to extract topics. Please try again.")

def generate_mcqs(selected_topics, selected_model):
    """Generates MCQs based on selected topics."""
    with st.spinner(f"Generating MCQs using {selected_model.capitalize()}... ⏳"):
        response = requests.post(
            f"{BASE_URL}/mcqs/generate/",
            json={"topics": selected_topics, "file_paths": st.session_state["file_paths"], "model": selected_model}
        )

    if response.status_code == 200:
        mcqs = response.json()
        if mcqs:
            st.subheader("📚 Generated MCQs")
            for mcq in mcqs:
                with st.expander(f"📝 {mcq['question']}"):
                    for option in mcq["options"]:
                        st.write(f"{option}")
                    st.success(f"✅ Correct Answer: {mcq['correct_answer']}")
        else:
            st.warning("⚠ No MCQs were generated.")
    else:
        st.error("❌ Failed to generate MCQs. Please try again.")

BASE_URL = "http://localhost:8000"
st.set_page_config(layout="wide", page_title="POC for Notesight")

st.sidebar.title("Features")
page = st.sidebar.radio("Go to", ["Notes", "Flashcards","Chat","MCQ"])

if page == "Chat":
    st.title("Notesight POC - Document QA")

    uploaded_file = st.file_uploader("Upload a PDF document", type=["pdf"])

    if uploaded_file:
        files = {"file": (uploaded_file.name, uploaded_file, "application/pdf")}
        response = requests.post(f"{BASE_URL}/upload/", files=files)

        if response.status_code == 200:
            st.success("✅ File uploaded successfully!")
            file_path = response.json().get("file_path")
        else:
            st.error("❌ Failed to upload file")
            st.stop()

    st.subheader("💬 Ask Questions About the Document")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    query = st.chat_input("Ask a question about the document...")
    if query:
        with st.chat_message("user"):
            st.markdown(query)
        st.session_state.messages.append({"role": "user", "content": query})

        response = requests.post(f"{BASE_URL}/ask/", data={"query": query})

        answer = response.json().get("answer", "⚠ No response received.") if response.status_code == 200 else "❌ Error: Failed to get a response."

        with st.chat_message("assistant"):
            st.markdown(answer)

        st.session_state.messages.append({"role": "assistant", "content": answer})

elif page == "Notes":
    st.title("Notesight POC - 📄Generate Notes")

    uploaded_files = st.file_uploader("Upload PDFs for Notes Generation", accept_multiple_files=True)
    model_options = {"Gemini": "gemini","ChatGPT": "chatgpt", "Mistral": "mistral"}
    model = st.selectbox("Select AI Model", list(model_options.values()))
    if uploaded_files:
        files = [("files", (file.name, file, "application/pdf")) for file in uploaded_files]

        if st.button("📝 Generate Notes"):
            response = requests.post(f"{BASE_URL}/notes/", files=files, data={"model": model}, stream=True)

            if response.status_code == 200:
                st.subheader("Generated Notes:")

                notes_placeholder = st.empty()
                notes_text = ""
                
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        decoded_chunk = chunk.decode("utf-8")
                        notes_text += decoded_chunk
                        notes_placeholder.markdown(notes_text)

            else:
                st.error("❌ Failed to generate notes")

elif page == "Flashcards":
    st.title("Notesight POC - 📚Flashcard Generator")

    uploaded_files = st.file_uploader("Upload PDFs for Flashcards", type=["pdf"], accept_multiple_files=True)
    model_options = {"Gemini": "gemini","ChatGPT": "chatgpt", "Mistral": "mistral"}
    selected_model = st.selectbox("Select AI Model", list(model_options.keys()))
    if st.button("🔹 Generate Flashcards"):
        if uploaded_files:
            files = [("files", (file.name, file, "application/pdf")) for file in uploaded_files]
            data = {"model": model_options[selected_model]}

            with st.spinner(f"Generating flashcards using {selected_model}... ⏳"):
                response = requests.post(f"{BASE_URL}/flashcards/", files=files, data=data)

                if response.status_code == 200:
                    flashcards = response.json().get("flashcards", [])

                    if flashcards:
                        st.subheader(f"📝 Flashcards (Generated by {selected_model})")
                        for flashcard in flashcards:
                            with st.expander(f"**{flashcard.get('concept', 'Unknown Concept')}**"):
                                st.write(flashcard.get("definition", "No Definition Provided"))
                    else:
                        st.warning("⚠ No flashcards were generated.")
                else:
                    st.error(f"❌ Failed to generate flashcards using {selected_model}")
        else:
            st.warning("⚠ Please upload at least one file first.")


elif page == "MCQ":
    st.title("Notesight POC - Generate MCQs")

    uploaded_files = st.file_uploader("Upload PDFs for MCQ generation", type=["pdf"], accept_multiple_files=True)
    MODEL_OPTIONS = {"Gemini": "gemini", "ChatGPT": "chatgpt", "Mistral": "mistral"}
    selected_model = st.selectbox("Select AI Model", list(MODEL_OPTIONS.keys()))
    selected_model_key = MODEL_OPTIONS[selected_model]  # Get model key

    if st.button("🔹 Extract Key Topics"):
        if uploaded_files:
            extract_topics(uploaded_files, selected_model_key)
        else:
            st.warning("⚠ Please upload at least one file first.")

    if "topics" in st.session_state and st.session_state["topics"]:
        selected_topics = st.multiselect("Select Topics for MCQ Generation", st.session_state["topics"])
        
        if st.button("🎯 Generate MCQs"):
            if selected_topics:
                generate_mcqs(selected_topics, selected_model_key)
            else:
                st.warning("⚠ Please select at least one topic.")




