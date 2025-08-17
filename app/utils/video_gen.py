import requests
import json
import time
import random
import string
from typing import List, Dict, Any
import threading
from queue import Queue
import sseclient
from urllib.parse import urlencode

class VideoGenerator:
    def __init__(self):
        self.base_url = "https://ltx-video.com/api/video/gen"
        self.session_hash = ""
        self.headers = {
            'Content-Type': 'application/json',
            'x-zerogpu-uuid': 'fwmmUsBxWJ9SqpiE-V8r5'
        }
    
    def generate_session_hash(self) -> str:
        """Generate a random session hash"""
        return ''.join(random.choices(string.ascii_letters + string.digits, k=13))
    
    def generate_single_video(self, prompt: str, model: str = "epiCRealism", guidance: str = "", steps: int = 4) -> str:
        """
        Generate a single video from a text prompt
        
        Args:
            prompt: Text description of the video
            model: AI model to use
            guidance: Additional guidance for generation
            steps: Number of generation steps
            
        Returns:
            URL of the generated video
        """
        try:
            # Generate session hash
            self.session_hash = self.generate_session_hash()
            
            # Queue join request data
            queue_data = {
                "data": [prompt, model, guidance, steps],
                "event_data": None,
                "fn_index": 1,
                "trigger_id": 10,
                "session_hash": self.session_hash
            }
            
            # Join the queue
            queue_url = f"{self.base_url}/queue/join?__theme=system"
            response = requests.post(queue_url, headers=self.headers, json=queue_data)
            
            if not response.ok:
                raise Exception(f"Queue join failed: {response.status_code}")
            
            print(f"Video generation queued for: {prompt[:50]}...")
            
            # Wait for results via SSE
            video_url = self._wait_for_video_result()
            return video_url
            
        except Exception as e:
            print(f"Error generating video for prompt '{prompt[:50]}...': {str(e)}")
            return ""
    
    def _wait_for_video_result(self) -> str:
        """
        Wait for video generation result via Server-Sent Events
        
        Returns:
            URL of the generated video
        """
        sse_url = f"{self.base_url}/queue/data?session_hash={self.session_hash}"
        
        try:
            response = requests.get(sse_url, stream=True, headers={'Accept': 'text/event-stream'})
            client = sseclient.SSEClient(response)
            
            for event in client.events():
                if event.data:
                    try:
                        data = json.loads(event.data)
                        
                        if data.get('msg') == 'process_started':
                            print("Processing video request...")
                        elif data.get('msg') == 'process_generating':
                            print("Generating video frames...")
                        elif data.get('msg') == 'process_completed':
                            if data.get('output', {}).get('data', [{}])[0].get('video', {}).get('url'):
                                video_url = data['output']['data'][0]['video']['url']
                                print("Video generated successfully!")
                                return video_url
                            else:
                                raise Exception('Invalid video data received')
                        elif data.get('msg') == 'estimation':
                            if data.get('rank') and data.get('queue_size'):
                                print(f"Position in queue: {data['rank']} of {data['queue_size']}")
                        elif data.get('msg') == 'close_stream':
                            break
                            
                    except json.JSONDecodeError:
                        continue
                        
        except Exception as e:
            print(f"SSE Error: {str(e)}")
            
        return ""

def generate_video_sequence(scenes_data: List[Dict[str, Any]], max_workers: int = 3) -> Dict[str, Any]:
    """
    Generate videos for a sequence of scenes and return results in the specified format
    
    Args:
        scenes_data: List of scene dictionaries with 'sec', 'scene', and 'dialog' keys
        max_workers: Maximum number of concurrent video generations
        
    Returns:
        Dictionary with 'response' key containing updated scenes with video URLs
    """
    
    def worker_thread(scene_queue: Queue, result_queue: Queue, generator: VideoGenerator):
        """Worker thread for generating videos"""
        while True:
            try:
                scene = scene_queue.get(timeout=1)
                if scene is None:
                    break
                    
                print(f"Generating video for second {scene['sec']}: {scene['scene'][:50]}...")
                
                # Generate video for this scene
                video_url = generator.generate_single_video(scene['scene'])
                
                # Add URL to scene data
                scene['url'] = video_url
                result_queue.put(scene)
                scene_queue.task_done()
                
            except Exception as e:
                print(f"Worker error: {str(e)}")
                scene_queue.task_done()
    
    # Create queues and generators
    scene_queue = Queue()
    result_queue = Queue()
    generators = [VideoGenerator() for _ in range(max_workers)]
    
    # Add scenes to queue
    for scene in scenes_data:
        scene_queue.put(scene.copy())
    
    # Start worker threads
    threads = []
    for generator in generators:
        thread = threading.Thread(target=worker_thread, args=(scene_queue, result_queue, generator))
        thread.daemon = True
        thread.start()
        threads.append(thread)
    
    # Collect results
    results = []
    processed_count = 0
    total_scenes = len(scenes_data)
    
    print(f"Starting generation for {total_scenes} scenes with {max_workers} workers...")
    
    while processed_count < total_scenes:
        try:
            scene_result = result_queue.get(timeout=300)  # 5 minute timeout per scene
            results.append(scene_result)
            processed_count += 1
            print(f"Completed {processed_count}/{total_scenes} scenes")
        except Exception as e:
            print(f"Timeout or error waiting for result: {str(e)}")
            break
    
    # Stop worker threads
    for _ in range(max_workers):
        scene_queue.put(None)
    
    # Wait for threads to finish
    for thread in threads:
        thread.join(timeout=10)
    
    # Sort results by second
    results.sort(key=lambda x: x.get('sec', 0))
    
    return {
        "response": results
    }

# Example usage
if __name__ == "__main__":
    # Example scene data (like your cat playing with ball example)
    example_scenes = [
        {
            "sec": 1,
            "scene": "A fluffy tabby cat sits on a hardwood floor in a sunlit living room, looking intently at a red ball. The living room includes a couch and a coffee table.",
            "dialog": "Purr..."
        },
        {
            "sec": 2,
            "scene": "The tabby cat bats playfully at the red ball with its paw on the hardwood floor of the living room. The living room includes a couch and a coffee table.",
            "dialog": "Tap."
        },
        {
            "sec": 3,
            "scene": "The red ball rolls a short distance away from the tabby cat on the hardwood floor in the living room. The living room includes a couch and a coffee table.",
            "dialog": ""
        }
    ]
    
    # Generate videos for the scenes
    # result = generate_video_sequence(example_scenes, max_workers=2)
    
    # # Print results
    # print("\nFinal Results:")
    # print(json.dumps(result, indent=2))
    
    # # Save results to file
    # with open('generated_videos.json', 'w') as f:
    #     json.dump(result, f, indent=2)
    
    # print(f"\nGenerated videos for {len(result['response'])} scenes")
    # print("Results saved to 'generated_videos.json'")