from fastapi import FastAPI, WebSocket
from fastapi.responses import Response
import json
import argparse
import uvicorn

from main import run_bot


app = FastAPI()

@app.post("/")
async def start_call():
    return Response(
        content=open("streams.xml").read(),
        media_type="application/xml"
    )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    start_data = websocket.iter_text()
    await start_data.__anext__()

    call_data = json.loads(await start_data.__anext__())

    stream_sid = call_data["start"]["streamSid"]
    call_sid = call_data["start"]["callSid"]

    await run_bot(websocket, stream_sid, call_sid, app.state.testing)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipecat Twilio Chatbot Server")
    parser.add_argument(
        "-t", "--test", action="store_true", default=False, help="set the server in testing mode"
    )
    args, _ = parser.parse_known_args()

    app.state.testing = args.test

    uvicorn.run(app, host="0.0.0.0", port=5000)
