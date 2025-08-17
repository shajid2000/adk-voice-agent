import asyncio
import aiohttp
import json
import time
import random
import string
import tempfile
import os
import logging
import sys
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager, redirect_stdout, redirect_stderr
from pathlib import Path
import sseclient
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.video.compositing.CompositeVideoClip import concatenate_videoclips
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import hashlib

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class VideoGenerationConfig:
    """Configuration for video generation"""
    base_url: str = "https://ltx-video.com/api/video/gen"
    max_workers: int = 3
    timeout: int = 300
    max_retries: int = 3
    retry_delay: float = 1.0
    temp_dir: Optional[str] = None
    
    def __post_init__(self):
        if self.temp_dir is None:
            self.temp_dir = tempfile.gettempdir()

@dataclass
class Scene:
    """Represents a video scene"""
    sec: int
    scene: str
    dialog: str
    url: Optional[str] = None
    
    @property
    def cache_key(self) -> str:
        """Generate cache key for the scene"""
        return hashlib.md5(f"{self.scene}".encode()).hexdigest()

class VideoGenerationError(Exception):
    """Custom exception for video generation errors"""
    pass

class VideoGenerator:
    """Optimized video generator with async support and better error handling"""
    
    def __init__(self, config: VideoGenerationConfig):
        self.config = config
        self.session_hash = ""
        self.headers = {
            'Content-Type': 'application/json',
            'x-zerogpu-uuid': 'fwmmUsBxWJ9SqpiE-V8r5'
        }
        self._session = None
    
    @asynccontextmanager
    async def get_session(self):
        """Context manager for aiohttp session"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self._session = aiohttp.ClientSession(
                headers=self.headers,
                timeout=timeout
            )
        try:
            yield self._session
        finally:
            pass  # Keep session alive for reuse
    
    async def close(self):
        """Close the aiohttp session"""
        if self._session and not self._session.closed:
            await self._session.close()
    
    def _generate_session_hash(self) -> str:
        """Generate a random session hash"""
        return ''.join(random.choices(string.ascii_letters + string.digits, k=13))
    
    async def generate_single_video(
        self, 
        scene: Scene, 
        model: str = "epiCRealism", 
        guidance: str = "", 
        steps: int = 4
    ) -> str:
        """
        Generate a single video from a scene with retry logic
        
        Args:
            scene: Scene object containing video description
            model: AI model to use
            guidance: Additional guidance for generation
            steps: Number of generation steps
            
        Returns:
            URL of the generated video
        """
        for attempt in range(self.config.max_retries):
            try:
                return await self._generate_video_attempt(scene, model, guidance, steps)
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed for scene {scene.sec}: {e}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay * (2 ** attempt))
                else:
                    logger.error(f"All attempts failed for scene {scene.sec}")
                    raise VideoGenerationError(f"Failed to generate video after {self.config.max_retries} attempts: {e}")
    
    async def _generate_video_attempt(
        self, 
        scene: Scene, 
        model: str, 
        guidance: str, 
        steps: int
    ) -> str:
        """Single attempt at video generation"""
        self.session_hash = self._generate_session_hash()
        
        queue_data = {
            "data": [scene.scene, model, guidance, steps],
            "event_data": None,
            "fn_index": 1,
            "trigger_id": 10,
            "session_hash": self.session_hash
        }
        
        async with self.get_session() as session:
            # Join the queue
            queue_url = f"{self.config.base_url}/queue/join?__theme=system"
            async with session.post(queue_url, json=queue_data) as response:
                if not response.ok:
                    raise VideoGenerationError(f"Queue join failed: {response.status}")
                
                logger.info(f"Video generation queued for scene {scene.sec}: {scene.scene[:50]}...")
                
                # Wait for results via SSE (this needs to be synchronous due to sseclient)
                return await asyncio.get_event_loop().run_in_executor(
                    None, self._wait_for_video_result
                )
    
    def _wait_for_video_result(self) -> str:
        """Wait for video generation result via Server-Sent Events"""
        sse_url = f"{self.config.base_url}/queue/data?session_hash={self.session_hash}"
        
        try:
            import requests  # Import here for thread executor
            response = requests.get(
                sse_url, 
                stream=True, 
                headers={'Accept': 'text/event-stream'},
                timeout=self.config.timeout
            )
            client = sseclient.SSEClient(response)
            
            for event in client.events():
                if event.data:
                    try:
                        data = json.loads(event.data)
                        
                        if data.get('msg') == 'process_completed':
                            video_data = data.get('output', {}).get('data', [{}])
                            if video_data and video_data[0].get('video', {}).get('url'):
                                video_url = video_data[0]['video']['url']
                                logger.info("Video generated successfully!")
                                return video_url
                            else:
                                raise VideoGenerationError('Invalid video data received')
                                
                        elif data.get('msg') == 'estimation':
                            if data.get('rank') and data.get('queue_size'):
                                logger.info(f"Position in queue: {data['rank']} of {data['queue_size']}")
                                
                        elif data.get('msg') == 'close_stream':
                            break
                            
                    except json.JSONDecodeError:
                        continue
                        
        except Exception as e:
            raise VideoGenerationError(f"SSE Error: {str(e)}")
            
        raise VideoGenerationError("No video URL received")

class VideoStitcher:
    """Handles video stitching with better resource management"""
    
    def __init__(self, config: VideoGenerationConfig):
        self.config = config
    
    async def download_video(self, url: str, temp_path: str) -> str:
        """Download video asynchronously"""
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response.raise_for_status()
                
                with open(temp_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(1024 * 1024):
                        f.write(chunk)
                
                return temp_path
    
    async def stitch_videos(self, scenes: List[Scene], output_path: str = "final_video.mp4") -> Dict[str, Any]:
        """
        Stitches videos from scenes into a single video with async downloads
        
        Args:
            scenes: List of Scene objects with URLs
            output_path: Path to save the final stitched video
            
        Returns:
            Dictionary with success status and path
        """
        if not scenes:
            raise ValueError("No scenes provided for stitching")
        
        clips = []
        temp_files = []
        
        try:
            # Download all videos concurrently
            download_tasks = []
            
            for i, scene in enumerate(scenes):
                if not scene.url:
                    logger.warning(f"No URL for scene {scene.sec}, skipping")
                    continue
                
                temp_file = os.path.join(
                    self.config.temp_dir, 
                    f"temp_video_{i}_{int(time.time())}.mp4"
                )
                temp_files.append(temp_file)
                download_tasks.append(self.download_video(scene.url, temp_file))
            
            if not download_tasks:
                raise ValueError("No valid video URLs to download")
            
            # Wait for all downloads to complete
            logger.info(f"Downloading {len(download_tasks)} videos...")
            downloaded_files = await asyncio.gather(*download_tasks, return_exceptions=True)
            
            # Filter out failed downloads
            valid_files = [f for f in downloaded_files if isinstance(f, str) and os.path.exists(f)]
            
            if not valid_files:
                raise ValueError("No videos downloaded successfully")
            
            logger.info(f"Successfully downloaded {len(valid_files)} videos")
            
            # Create video clips in a thread executor to avoid blocking
            def create_clips():
                clips_list = []
                for file_path in valid_files:
                    try:
                        clip = VideoFileClip(file_path)
                        clips_list.append(clip)
                    except Exception as e:
                        logger.error(f"Failed to create clip from {file_path}: {e}")
                return clips_list
            
            clips = await asyncio.get_event_loop().run_in_executor(None, create_clips)
            
            if not clips:
                raise ValueError("No valid video clips created")
            
            # Stitch videos in thread executor
            def stitch():
                final_clip = concatenate_videoclips(clips, method="compose")
                
                # Suppress MoviePy output by redirecting stdout/stderr
                with open(os.devnull, 'w') as devnull:
                    with redirect_stdout(devnull), redirect_stderr(devnull):
                        try:
                            # MoviePy 2.2.1 compatible parameters
                            final_clip.write_videofile(
                                output_path, 
                                codec="libx264", 
                                audio_codec="aac",
                                temp_audiofile="temp-audio.m4a",
                                remove_temp=True
                            )
                        except Exception as e:
                            logger.warning(f"First write attempt failed: {e}")
                            # Minimal fallback
                            final_clip.write_videofile(output_path, codec="libx264")
                
                final_clip.close()
                for clip in clips:
                    clip.close()
                return output_path
            
            logger.info("Stitching videos...")
            final_path = await asyncio.get_event_loop().run_in_executor(None, stitch)
            
            return {"success": True, "path": final_path}
            
        except Exception as e:
            logger.error(f"Error stitching videos: {e}")
            # Clean up clips
            for clip in clips:
                try:
                    clip.close()
                except:
                    pass
            raise
            
        finally:
            # Clean up temp files
            await self._cleanup_temp_files(temp_files)
    
    async def _cleanup_temp_files(self, temp_files: List[str]):
        """Clean up temporary files with proper error handling"""
        for file_path in temp_files:
            try:
                if os.path.exists(file_path):
                    await asyncio.sleep(0.1)  # Small delay before deletion
                    os.remove(file_path)
            except Exception as e:
                logger.warning(f"Could not delete temp file {file_path}: {e}")

class VideoProcessingPipeline:
    """Main pipeline for video generation and processing"""
    
    def __init__(self, config: Optional[VideoGenerationConfig] = None):
        self.config = config or VideoGenerationConfig()
        self.generator = VideoGenerator(self.config)
        self.stitcher = VideoStitcher(self.config)
    
    async def process_scenes(self, scenes_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Process a list of scenes and return video URLs
        
        Args:
            scenes_data: List of scene dictionaries
            
        Returns:
            Dictionary with processed scenes
        """
        scenes = [Scene(**scene_data) for scene_data in scenes_data]
        
        # Generate videos concurrently with limited concurrency
        semaphore = asyncio.Semaphore(self.config.max_workers)
        
        async def generate_with_semaphore(scene: Scene) -> Scene:
            async with semaphore:
                try:
                    scene.url = await self.generator.generate_single_video(scene)
                    logger.info(f"Generated video for scene {scene.sec}")
                except Exception as e:
                    logger.error(f"Failed to generate video for scene {scene.sec}: {e}")
                    scene.url = None
                return scene
        
        logger.info(f"Starting generation for {len(scenes)} scenes with {self.config.max_workers} workers...")
        
        # Process scenes concurrently
        processed_scenes = await asyncio.gather(
            *[generate_with_semaphore(scene) for scene in scenes],
            return_exceptions=True
        )
        
        # Filter successful results
        successful_scenes = [
            scene for scene in processed_scenes 
            if isinstance(scene, Scene) and scene.url
        ]
        
        logger.info(f"Successfully generated {len(successful_scenes)}/{len(scenes)} videos")
        
        # Sort by second
        successful_scenes.sort(key=lambda x: x.sec)
        
        return {
            "response": [
                {
                    "sec": scene.sec,
                    "scene": scene.scene,
                    "dialog": scene.dialog,
                    "url": scene.url
                }
                for scene in successful_scenes
            ]
        }
    
    async def generate_and_stitch_video(
        self, 
        scenes_data: List[Dict[str, Any]], 
        output_path: str = "final_video.mp4"
    ) -> Dict[str, Any]:
        """
        Complete pipeline: generate videos and stitch them together
        
        Args:
            scenes_data: List of scene dictionaries
            output_path: Path for final video
            
        Returns:
            Result dictionary with success status and path
        """
        try:
            # Generate videos
            result = await self.process_scenes(scenes_data)
            
            if not result["response"]:
                return {"success": False, "error": "No videos were generated successfully"}
            
            # Create scenes from result
            scenes = [
                Scene(
                    sec=item["sec"],
                    scene=item["scene"], 
                    dialog=item["dialog"],
                    url=item["url"]
                )
                for item in result["response"]
            ]
            
            # Stitch videos
            stitch_result = await self.stitcher.stitch_videos(scenes, output_path)
            
            return stitch_result
            
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            return {"success": False, "error": str(e)}
        
        finally:
            await self.generator.close()

# Optimized FastAPI endpoint
async def generate_video_endpoint(topic: str, duration: Optional[int] = 30):
    """
    Optimized FastAPI endpoint for video generation
    """
    try:
        # Get model configs and call agent (assuming these functions exist)
        runner, session_id = get_model_configs(USER_ID="shajid")
        raw_response = await call_agent_async(
            runner=runner,
            user_id="shajid",
            session_id=session_id,
            query=topic
        )
        
        # Parse response
        try:
            response = json.loads(raw_response)
        except json.JSONDecodeError:
            return {
                "error": "Invalid JSON returned from agent",
                "raw_response": raw_response
            }
        
        # Extract script
        if isinstance(response, dict) and "script" in response:
            scenes_data = response["script"]
        else:
            return {"error": "No 'script' key in response", "parsed_response": response}
        
        # Configure pipeline
        config = VideoGenerationConfig(max_workers=2)
        pipeline = VideoProcessingPipeline(config)
        
        # Generate and stitch video
        output_path = f"generated_video_{int(time.time())}.mp4"
        result = await pipeline.generate_and_stitch_video(scenes_data, output_path)
        
        if result['success']:
            from fastapi.responses import FileResponse
            return FileResponse(
                result["path"], 
                media_type="video/mp4", 
                filename=f"generated_video_{topic[:20]}.mp4"
            )
        else:
            return {"error": "Failed to generate/stitch videos", "details": result}
            
    except Exception as e:
        logger.error(f"Endpoint error: {e}")
        return {"error": "Internal server error", "details": str(e)}

# Example usage
if __name__ == "__main__":
    async def main():
        example_scenes = [
            {
                "sec": 1,
                "scene": "A fluffy tabby cat sits on a hardwood floor in a sunlit living room, looking intently at a red ball.",
                "dialog": "Purr..."
            },
            {
                "sec": 2, 
                "scene": "The tabby cat bats playfully at the red ball with its paw on the hardwood floor.",
                "dialog": "Tap."
            },
            {
                "sec": 3,
                "scene": "The red ball rolls away from the tabby cat on the hardwood floor.",
                "dialog": ""
            }
        ]
        
        config = VideoGenerationConfig(max_workers=2)
        pipeline = VideoProcessingPipeline(config)
        
        result = await pipeline.generate_and_stitch_video(
            example_scenes, 
            "optimized_cat_video.mp4"
        )
        
        print("Result:", result)
    
    asyncio.run(main())