const API_BASE_URL = "http://127.0.0.1:8000/api";  // Change if needed

// Upload PDF file and get summary
async function uploadFile() {
    const fileInput = document.getElementById("fileInput");
    if (fileInput.files.length === 0) {
        alert("Please select a file to upload.");
        return;
    }

    const formData = new FormData();
    formData.append("file", fileInput.files[0]);

    document.getElementById("uploadStatus").innerText = "Uploading...";

    try {
        const response = await fetch(`${API_BASE_URL}/upload/`, {
            method: "POST",
            body: formData
        });
        const result = await response.json();
        appendMessage("bot", result.summary || "No summary found.");
        document.getElementById("uploadStatus").innerText = result.message;

        // If upload is successful, fetch the summary
        if (result.success) {
            fetchSummary(result.file_path);  // ✅ Call the summary function
        }
    } catch (error) {
        console.error("Upload error:", error);
        document.getElementById("uploadStatus").innerText = "Upload failed!";
    }
}

// Ask a question (Chat functionality)
async function askQuestion() {
    const questionInput = document.getElementById("questionInput");
    const questionText = questionInput.value.trim();
    if (!questionText) {
        alert("Please enter a message.");
        return;
    }

    // Append user message to chat
    appendMessage("user", questionText);
    questionInput.value = ""; // Clear input field

    const formData = new URLSearchParams();
    formData.append("query", questionText);

    try {
        const response = await fetch(`${API_BASE_URL}/ask/`, {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: formData
        });
        const result = await response.json();

        // Append bot response to chat
        appendMessage("bot", result.answer || "No response from server.");
    } catch (error) {
        console.error("Error:", error);
        appendMessage("bot", "Failed to get a response!");
    }
}

// Append messages to chatbox
function appendMessage(sender, text) {
    const chatbox = document.getElementById("chatbox");
    const messageDiv = document.createElement("div");
    messageDiv.classList.add("message", sender);
    messageDiv.innerText = text;
    chatbox.appendChild(messageDiv);
    chatbox.scrollTop = chatbox.scrollHeight; // Auto-scroll to latest message
}
