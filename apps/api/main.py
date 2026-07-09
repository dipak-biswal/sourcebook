from fastapi import FastAPI

app = FastAPI(
    title="Sourcebook",
    description="Multi-tenant docuemnt AI workspace",
    version="0.1.0",
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "sourcebook"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
