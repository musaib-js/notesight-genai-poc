# Store the API documentation here# README

## Overview
This project is a FastAPI-based application that provides multiple endpoints for authentication, file uploads, MCQ generation, and PDF processing. Below is an overview of the key functionalities and their flowcharts.

---

## API Endpoints and Flowcharts

### 1. Authentication Process
Handles user authentication including password hashing, verification, and token creation.

```mermaid
graph TD;
    A[User Login Request] -->|Submit Credentials| B[FastAPI Auth Endpoint]
    B -->|Verify Credentials| C[Database Query]
    C -->|If Valid| D[Generate Access Token]
    D -->|Return Token| E[User Receives Token]
    C -->|If Invalid| F[Return Error Message]
```

### 2. File Upload Process
Handles file uploads and stores them in the `uploads` directory.

```mermaid
graph TD;
    A[User Uploads File] -->|Send POST Request| B[FastAPI File Upload Endpoint]
    B -->|Save File| C[Uploads Directory]
    C -->|Return Success Message| D[User Receives Confirmation]
```

### 3. MCQ Generation
Generates multiple-choice questions using different AI models.

```mermaid
graph TD;
    A[User Request for MCQs] -->|Send POST Request| B[MCQ Endpoint]
    B -->|Select AI Model| C[Gemini/Mistral/ChatGPT]
    C -->|Generate MCQs| D[Return MCQs to User]
```

### 4. PDF Processing
Processes uploaded PDFs and extracts necessary information.

```mermaid
graph TD;
    A[User Uploads PDF] -->|Send POST Request| B[PDF Processing Endpoint]
    B -->|Extract Data| C[Text Processing]
    C -->|Save Report| D[Database]
    D -->|Return Processed Data| E[User Receives Data]
```

---

## Installation and Setup
1. Clone the repository:
   ```bash
   git clone https://github.com/your-repo.git
   ```
2. Navigate to the project directory:
   ```bash
   cd your-project
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the application:
   ```bash
   uvicorn app:app --reload
   ```

---


