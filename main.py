from fastapi import FastAPI, status

app = FastAPI()

@app.get("/", status_code=status.HTTP_200_OK)
def home():
    return {"message": "Welcome to Notesight Intelligence Systems!"}

@app.get("/health", status_code=status.HTTP_200_OK)
def health():
    return {"status": "Up and Healthy!"}