import asyncio
import base64
import json
import os
from pathlib import Path
from typing import AsyncIterable,Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Query, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from google.adk.agents import LiveRequestQueue
from google.adk.agents.run_config import RunConfig
from google.adk.events.event import Event
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types
from jarvis.agent import root_agent
from utils.utility import get_model_configs,call_agent_async
from utils.video_gen import generate_video_sequence
from utils.video_editor import stitch_videos

from utils.video_generation import VideoProcessingPipeline, VideoGenerationConfig

import time
import logging
from fastapi import HTTPException
#
# ADK Streaming
#

# Load Gemini API Key
load_dotenv()

APP_NAME = "ADK Streaming example"
session_service = InMemorySessionService()


def start_agent_session(session_id, is_audio=False):
    """Starts an agent session"""

    # Create a Session
    session = session_service.create_session(
        app_name=APP_NAME,
        user_id=session_id,
        session_id=session_id,
    )

    # Create a Runner
    runner = Runner(
        app_name=APP_NAME,
        agent=root_agent,
        session_service=session_service,
    )

    # Set response modality
    modality = "AUDIO" if is_audio else "TEXT"

    # Create speech config with voice settings
    speech_config = types.SpeechConfig(
        voice_config=types.VoiceConfig(
            # Puck, Charon, Kore, Fenrir, Aoede, Leda, Orus, and Zephyr
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Puck")
        )
    )

    # Create run config with basic settings
    config = {"response_modalities": [modality], "speech_config": speech_config}

    # Add output_audio_transcription when audio is enabled to get both audio and text
    if is_audio:
        config["output_audio_transcription"] = {}

    run_config = RunConfig(**config)

    # Create a LiveRequestQueue for this session
    live_request_queue = LiveRequestQueue()

    # Start agent session
    live_events = runner.run_live(
        session=session,
        live_request_queue=live_request_queue,
        run_config=run_config,
    )
    return live_events, live_request_queue


async def agent_to_client_messaging(
    websocket: WebSocket, live_events: AsyncIterable[Event | None]
):
    """Agent to client communication"""
    while True:
        async for event in live_events:
            if event is None:
                continue

            # If the turn complete or interrupted, send it
            if event.turn_complete or event.interrupted:
                message = {
                    "turn_complete": event.turn_complete,
                    "interrupted": event.interrupted,
                }
                await websocket.send_text(json.dumps(message))
                print(f"[AGENT TO CLIENT]: {message}")
                continue

            # Read the Content and its first Part
            part = event.content and event.content.parts and event.content.parts[0]
            if not part:
                continue

            # Make sure we have a valid Part
            if not isinstance(part, types.Part):
                continue

            # Only send text if it's a partial response (streaming)
            # Skip the final complete message to avoid duplication
            if part.text and event.partial:
                message = {
                    "mime_type": "text/plain",
                    "data": part.text,
                    "role": "model",
                }
                await websocket.send_text(json.dumps(message))
                print(f"[AGENT TO CLIENT]: text/plain: {part.text}")

            # If it's audio, send Base64 encoded audio data
            is_audio = (
                part.inline_data
                and part.inline_data.mime_type
                and part.inline_data.mime_type.startswith("audio/pcm")
            )
            if is_audio:
                audio_data = part.inline_data and part.inline_data.data
                if audio_data:
                    message = {
                        "mime_type": "audio/pcm",
                        "data": base64.b64encode(audio_data).decode("ascii"),
                        "role": "model",
                    }
                    await websocket.send_text(json.dumps(message))
                    print(f"[AGENT TO CLIENT]: audio/pcm: {len(audio_data)} bytes.")


async def client_to_agent_messaging(
    websocket: WebSocket, live_request_queue: LiveRequestQueue
):
    """Client to agent communication"""
    while True:
        # Decode JSON message
        message_json = await websocket.receive_text()
        message = json.loads(message_json)
        mime_type = message["mime_type"]
        data = message["data"]
        role = message.get("role", "user")  # Default to 'user' if role is not provided

        # Send the message to the agent
        if mime_type == "text/plain":
            # Send a text message
            content = types.Content(role=role, parts=[types.Part.from_text(text=data)])
            live_request_queue.send_content(content=content)
            print(f"[CLIENT TO AGENT PRINT]: {data}")
        elif mime_type == "audio/pcm":
            # Send audio data
            decoded_data = base64.b64decode(data)

            # Send the audio data - note that ActivityStart/End and transcription
            # handling is done automatically by the ADK when input_audio_transcription
            # is enabled in the config
            live_request_queue.send_realtime(
                types.Blob(data=decoded_data, mime_type=mime_type)
            )
            print(f"[CLIENT TO AGENT]: audio/pcm: {len(decoded_data)} bytes")

        else:
            raise ValueError(f"Mime type not supported: {mime_type}")


#
# FastAPI web app
#

app = FastAPI()

STATIC_DIR = Path("static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def root():
    """Serves the index.html"""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


# Import the optimized classes (assuming they're in a separate module)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI()

# Global pipeline instance (optional - for reusing sessions)
_video_pipeline = None

def get_video_pipeline() -> VideoProcessingPipeline:
    """Get or create video processing pipeline instance"""
    global _video_pipeline
    if _video_pipeline is None:
        config = VideoGenerationConfig(
            max_workers=2,  # Adjust based on your server capacity
            timeout=300,    # 5 minutes timeout
            max_retries=3,  # Retry failed generations
            temp_dir="./temp_videos"  # Specify temp directory
        )
        # Create temp directory if it doesn't exist
        os.makedirs(config.temp_dir, exist_ok=True)
        _video_pipeline = VideoProcessingPipeline(config)
    
    return _video_pipeline

@app.get("/generate-video")
async def generate_video(topic: str, duration: Optional[int] = 30):
    """
    Generate video from topic using optimized pipeline
    
    Args:
        topic: Video topic/description
        duration: Video duration in seconds (not used in current implementation)
    
    Returns:
        FileResponse with generated video or error response
    """
    try:
        logger.info(f"Starting video generation for topic: {topic}")
        
        # Get model configs and call agent (your existing code)
        runner, session_id = get_model_configs(USER_ID="shajid")
        raw_response = await call_agent_async(
            runner=runner,
            user_id="shajid",
            session_id=session_id,
            query=topic
        )
        
        # Parse the agent response
        try:
            response = json.loads(raw_response)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse agent response: {e}")
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "Invalid JSON returned from agent",
                    "raw_response": raw_response[:500]  # Truncate for safety
                }
            )
        
        # Extract script from response
        if isinstance(response, dict) and "script" in response:
            scenes_data = response["script"]
            logger.info(f"Extracted {len(scenes_data)} scenes from script")
        else:
            logger.error("No 'script' key found in agent response")
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "No 'script' key in response", 
                    "parsed_response": response
                }
            )
        
        # Validate scenes data
        if not scenes_data or not isinstance(scenes_data, list):
            raise HTTPException(
                status_code=400,
                detail={"error": "Invalid or empty scenes data"}
            )
        
        # Get the optimized pipeline
        pipeline = get_video_pipeline()
        
        # Generate unique output filename
        timestamp = int(time.time())
        safe_topic = "".join(c for c in topic[:20] if c.isalnum() or c in (' ', '_', '-')).strip()
        output_filename = f"generated_video_{safe_topic}_{timestamp}.mp4"
        output_path = f"./generated_videos/{output_filename}"
        
        # Create output directory if it doesn't exist
        os.makedirs("./generated_videos", exist_ok=True)
        
        # Run the optimized pipeline
        logger.info("Starting video generation and stitching pipeline...")
        result = await pipeline.generate_and_stitch_video(scenes_data, output_path)
        
        if result.get('success'):
            logger.info(f"Video generation successful: {result['path']}")
            
            # Verify file exists and has content
            if not os.path.exists(result['path']) or os.path.getsize(result['path']) == 0:
                raise HTTPException(
                    status_code=500,
                    detail={"error": "Generated video file is missing or empty"}
                )
            
            return FileResponse(
                result["path"],
                media_type="video/mp4",
                filename=f"{safe_topic}_video.mp4",
                headers={
                    "Content-Disposition": f"attachment; filename=\"{safe_topic}_video.mp4\"",
                    "Cache-Control": "no-cache"
                }
            )
        else:
            logger.error(f"Video generation failed: {result}")
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "Failed to generate/stitch videos", 
                    "details": result.get('error', 'Unknown error')
                }
            )
            
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Unexpected error in video generation: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error during video generation",
                "details": str(e)
            }
        )


@app.delete("/clear-videos")
async def clear_generated_videos():
    """
    Clear all generated videos from the generated_videos directory
    
    Returns:
        Dictionary with operation status and details
    """
    try:
        videos_dir = Path("./generated_videos")
        temp_dir = Path("./temp_videos")
        
        deleted_files = []
        errors = []
        
        # Clear generated_videos directory
        if videos_dir.exists():
            for file_path in videos_dir.iterdir():
                try:
                    if file_path.is_file():
                        file_size = file_path.stat().st_size
                        file_path.unlink()  # Delete the file
                        deleted_files.append({
                            "file": str(file_path.name),
                            "size_bytes": file_size,
                            "type": "generated_video"
                        })
                        logger.info(f"Deleted: {file_path.name}")
                except Exception as e:
                    error_msg = f"Failed to delete {file_path.name}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg)
        
        # Clear temp_videos directory
        if temp_dir.exists():
            for file_path in temp_dir.iterdir():
                try:
                    if file_path.is_file():
                        file_size = file_path.stat().st_size
                        file_path.unlink()  # Delete the file
                        deleted_files.append({
                            "file": str(file_path.name),
                            "size_bytes": file_size,
                            "type": "temp_video"
                        })
                        logger.info(f"Deleted temp file: {file_path.name}")
                except Exception as e:
                    error_msg = f"Failed to delete temp file {file_path.name}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg)
        
        # Calculate total space freed
        total_bytes_freed = sum(file_info["size_bytes"] for file_info in deleted_files)
        total_mb_freed = round(total_bytes_freed / (1024 * 1024), 2)
        
        response = {
            "success": True,
            "message": f"Cleanup completed. Deleted {len(deleted_files)} files",
            "details": {
                "files_deleted": len(deleted_files),
                "total_size_freed_mb": total_mb_freed,
                "deleted_files": deleted_files,
                "errors": errors if errors else None
            }
        }
        
        logger.info(f"Cleanup completed: {len(deleted_files)} files deleted, {total_mb_freed}MB freed")
        return response
        
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to clear generated videos",
                "details": str(e)
            }
        )


@app.get("/clear-videos")
async def delete_videos(file_name: str | None = Query(None, description="Optional file name to delete")):
    """
    Delete a specific video file or all video files from generated_videos directory
    
    Args:
        file_name: Optional name of the video file to delete. If not provided, deletes all .mp4 files.
        
    Returns:
        Dictionary with operation status
    """
    videos_dir = Path("./generated_videos")
    videos_dir.mkdir(exist_ok=True)  # ensure directory exists

    try:
        if file_name:
            # Delete specific file
            safe_filename = os.path.basename(file_name)
            if not safe_filename.endswith('.mp4'):
                raise HTTPException(status_code=400, detail="Only .mp4 files can be deleted")

            file_path = videos_dir / safe_filename
            if not file_path.exists():
                raise HTTPException(status_code=404, detail=f"File '{safe_filename}' not found")
            file_size_mb = round(file_path.stat().st_size / (1024 * 1024), 2)
            file_path.unlink()
            logger.info(f"Deleted specific file: {safe_filename} ({file_size_mb}MB)")
            return {
                "success": True,
                "message": f"Successfully deleted '{safe_filename}'",
                "details": {"file_name": safe_filename, "size_freed_mb": file_size_mb}
            }
        else:
            # Delete all .mp4 files
            deleted_files = []
            for file_path in videos_dir.glob("*.mp4"):
                size_mb = round(file_path.stat().st_size / (1024 * 1024), 2)
                file_path.unlink()
                deleted_files.append({"file_name": file_path.name, "size_freed_mb": size_mb})
                logger.info(f"Deleted file: {file_path.name} ({size_mb}MB)")

            return {
                "success": True,
                "message": f"Deleted {len(deleted_files)} file(s)",
                "details": deleted_files
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting videos: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete videos: {str(e)}")


@app.get("/videos/list")
async def list_generated_videos():
    """
    List all generated videos with their details
    
    Returns:
        Dictionary with list of videos and directory info
    """
    try:
        videos_dir = Path("./generated_videos")
        temp_dir = Path("./temp_videos")
        
        video_files = []
        temp_files = []
        
        # List generated videos
        if videos_dir.exists():
            for file_path in videos_dir.iterdir():
                if file_path.is_file() and file_path.suffix.lower() == '.mp4':
                    stat = file_path.stat()
                    video_files.append({
                        "name": file_path.name,
                        "size_bytes": stat.st_size,
                        "size_mb": round(stat.st_size / (1024 * 1024), 2),
                        "created_time": time.ctime(stat.st_ctime),
                        "modified_time": time.ctime(stat.st_mtime)
                    })
        
        # List temp files
        if temp_dir.exists():
            for file_path in temp_dir.iterdir():
                if file_path.is_file():
                    stat = file_path.stat()
                    temp_files.append({
                        "name": file_path.name,
                        "size_bytes": stat.st_size,
                        "size_mb": round(stat.st_size / (1024 * 1024), 2),
                        "created_time": time.ctime(stat.st_ctime)
                    })
        
        # Calculate totals
        total_video_size = sum(f["size_bytes"] for f in video_files)
        total_temp_size = sum(f["size_bytes"] for f in temp_files)
        total_size_mb = round((total_video_size + total_temp_size) / (1024 * 1024), 2)
        
        return {
            "success": True,
            "summary": {
                "total_videos": len(video_files),
                "total_temp_files": len(temp_files),
                "total_size_mb": total_size_mb
            },
            "generated_videos": sorted(video_files, key=lambda x: x["modified_time"], reverse=True),
            "temp_files": sorted(temp_files, key=lambda x: x["created_time"], reverse=True) if temp_files else []
        }
        
    except Exception as e:
        logger.error(f"Error listing videos: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to list generated videos",
                "details": str(e)
            }
        )

    


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    is_audio: str = Query(...),
):
    """Client websocket endpoint"""

    # Wait for client connection
    await websocket.accept()
    print(f"Client #{session_id} connected, audio mode: {is_audio}")

    # Start agent session
    live_events, live_request_queue = start_agent_session(
        session_id, is_audio == "true"
    )

    # Start tasks
    agent_to_client_task = asyncio.create_task(
        agent_to_client_messaging(websocket, live_events)
    )
    client_to_agent_task = asyncio.create_task(
        client_to_agent_messaging(websocket, live_request_queue)
    )
    await asyncio.gather(agent_to_client_task, client_to_agent_task)

    # Disconnected
    print(f"Client #{session_id} disconnected")
