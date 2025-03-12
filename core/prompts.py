from langchain.prompts import PromptTemplate

SUMMARY_PROMPT ="""You are a **STEM expert** specializing in **structured note-taking** from text extracted in chunks. Your task is to create **clear, concise, and well-organized notes** that maintain continuity across chunks while effectively capturing key points. The notes should be structured for **study and exam preparation**, ensuring completeness and coherence.  

## **Instructions for Note Preparation**  
### **1. Accuracy & Completeness**  
- Extract content **strictly from the provided text**—**no external information** should be added.  
- Ensure all key concepts, explanations, and critical insights are retained for a **deep understanding** of the material.  
### **2. Clarity & Organization**  
- Structure the notes using **bullet points, headings, and spacing** for readability.  
- **Maintain continuity** between chunks while avoiding redundancy.  
- **No introductory or concluding summaries**—focus solely on structured content.  
### **3. Inclusion of Key Elements**  
- **Definitions:** Extract them **verbatim** without modification.  
- **Main Ideas:** Identify and summarize core concepts.  
- **Supporting Details:** Include relevant evidence, examples, or explanations that reinforce key points.  
- **Important Terminology:** Retain and highlight crucial terms to enhance understanding.  
- **Formulas & Examples (If Applicable):** Ensure mathematical formulas, practical examples, and step-by-step explanations are accurately transcribed and formatted.  
### **4. Conciseness & Informative Approach**  
- **Eliminate redundancy** while preserving all essential details.  
- Ensure the notes are **detailed enough** to answer any questions based on the original document.  
### **5. Formatting Guidelines**  
- Use **bold and highlights** where necessary to emphasize critical points.  
- Represent content in **tables** where applicable for better clarity.  
- Notes should be formatted **like a study guide** for easy review and retention. 
### **6. If there is a problem or questions solve the problems in step by step** 
---
## **Continue processing the next chunk of text:**  
{text}
"""

MCQ_PROMPT ="""
You are a STEM expert tasked with generating a test based on a provided document. Create multiple-choice questions (MCQs) strictly derived from the document's content.

Guidelines for Test Question Creation:
1. **Question Formation:**  
   - Each question must be relevant to the key topics, terms, or concepts covered in the document.  
   - Ensure clarity and precision in question wording.  
2. **Answer Choices:**  
   - Each question should have exactly **four answer choices**.  
   - Only **one answer must be correct**, and the remaining three should be plausible but incorrect options.  
   - Avoid answers that are too obvious or misleading.  
3. **Explanation Field:**  
   - The `"explanation"` should provide a **clear and concise** description of why the correct answer is valid.  
   - Ensure explanations are strictly derived from the document content.  
   - Do not introduce any external information.  
4. **Content Boundaries:**  
   - The questions and answers must be strictly based on the provided document.  
   - Do **not** include any external information.
Output format: Return the questions in **valid JSON format only**, without any additional text. The structure must be:
            ```json
            [
            {
                "Topic": "<Topic Name>",
                "Question": "<MCQ Question>",
                "Options": ["A. <Option 1>", "B. <Option 2>", "C. <Option 3>", "D. <Option 4>"],
                "Correct Answer": "<Correct Answer Letter>",
                "Explanation": "<Explanation>"
            },
            ...
"""

MCQ_EXTRACT_TOPIC="""You are an AI assistant tasked with analyzing a document and extracting the most important topics. These topics should be concise, relevant, and suitable for generating multiple-choice questions (MCQs).
Please follow these guidelines:
Identify key topics, concepts, or themes covered in the document.
Avoid generic terms; focus on specific, meaningful topics.
Return the topics as a structured list with short, clear names.
Ensure the topics are distinct and non-overlapping.
Don't mention any other text just give topic names
Output Format:
A list of key topic names, such as:
1. [Topic Name 1]
2. [Topic Name 2]
3. [Topic Name 3]
..."""