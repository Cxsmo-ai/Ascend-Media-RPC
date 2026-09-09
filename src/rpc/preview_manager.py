import os
import sys
import time
import json
import logging
import shutil
import subprocess
import threading
import urllib.parse
import requests

logger = logging.getLogger("StremioAscend.RPCPreviewManager")

IS_WINDOWS = sys.platform == "win32"

class RPCPreviewManager:
    def __init__(self, config: dict):
        self.config = config
        self.history_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "rpc_artwork_cache",
            "preview_history.json"
        )
        self.history = self._load_history()
        
        # Threads & subprocesses state
        self.active_thread = None
        self.active_processes = []
        self.lock = threading.Lock()
        
        # Scheduler / Debounce state
        self.last_bucket = None
        self.pending_bucket = None
        self.debounce_time = 0
        self.active_previews = {} # bucket_seconds -> url
        self.current_media_id = None
        
        # Ensure directories exist
        os.makedirs(os.path.dirname(self.history_path), exist_ok=True)

    def update_config(self, config: dict):
        self.config = config

    def _load_history(self) -> dict:
        try:
            if os.path.exists(self.history_path):
                with open(self.history_path, "r") as f:
                    data = json.load(f)
                    # Purge expired items
                    now = time.time()
                    cleaned = {k: v for k, v in data.items() if v.get("expires_at", 0) > now}
                    return cleaned
        except Exception as e:
            logger.error(f"Error loading preview history: {e}")
        return {}

    def _save_history(self):
        try:
            with open(self.history_path, "w") as f:
                json.dump(self.history, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving preview history: {e}")

    def _resolve_binary(self, binary_name: str, config_key: str) -> str:
        override = self.config.get(config_key)
        if override and os.path.exists(override):
            return override
            
        # Check local bin folder
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        local_path = os.path.join(project_root, "bin", f"{binary_name}.exe" if IS_WINDOWS else binary_name)
        if os.path.exists(local_path):
            return local_path
            
        # Check system PATH
        resolved = shutil.which(binary_name)
        if resolved:
            return resolved
            
        return binary_name

    def is_youtube_video(self, status: dict) -> bool:
        url = status.get("page_url") or status.get("stream_url") or ""
        lowered = url.lower()
        return "youtube.com" in lowered or "youtu.be" in lowered

    def get_media_id(self, media_title_or_id: str, status: dict) -> str:
        url = status.get("page_url") or status.get("stream_url") or ""
        video_id = None
        if "youtube.com/watch" in url:
            try:
                parsed = urllib.parse.urlsplit(url)
                params = urllib.parse.parse_qs(parsed.query)
                video_id = params.get("v", [None])[0]
            except:
                pass
        elif "youtu.be/" in url:
            try:
                video_id = url.split("youtu.be/")[1].split("?")[0].split("/")[0]
            except:
                pass
        
        if video_id:
            return f"yt_{video_id}"
        return f"title_{media_title_or_id}"

    def get_active_preview_url(self, status: dict, media_title_or_id: str) -> str:
        if not self.config.get("rpc_preview_enabled", False):
            return None
        if not self.is_youtube_video(status):
            return None
            
        pos_sec = int(status.get("position", 0) / 1000)
        bucket_size = self.config.get("rpc_preview_bucket_seconds", 15)
        bucket = (pos_sec // bucket_size) * bucket_size
        
        media_id = self.get_media_id(media_title_or_id, status)
        cache_key = f"{media_id}_b{bucket}"
        
        # Check in-memory active previews
        if cache_key in self.active_previews:
            return self.active_previews[cache_key]
            
        # Check history cache
        if cache_key in self.history:
            item = self.history[cache_key]
            if item.get("expires_at", 0) > time.time():
                url = item.get("url")
                if url and self._validate_url(url):
                    self.active_previews[cache_key] = url
                    return url
                else:
                    try:
                        del self.history[cache_key]
                        self._save_history()
                    except:
                        pass
                    
        return None

    def _validate_url(self, url: str) -> bool:
        try:
            response = requests.head(url, timeout=5, allow_redirects=True)
            if response.status_code == 200 and "image/webp" in response.headers.get("Content-Type", "").lower():
                return True
        except:
            pass
        try:
            response = requests.get(url, headers={"Range": "bytes=0-1023"}, timeout=5, allow_redirects=True)
            if response.status_code in (200, 206) and "image/webp" in response.headers.get("Content-Type", "").lower():
                return True
        except:
            pass
        return False

    def cancel_active_jobs(self):
        with self.lock:
            for p in list(self.active_processes):
                try:
                    logger.info(f"Terminating active process {p.pid}")
                    p.terminate()
                    p.wait(timeout=2)
                except:
                    try:
                        p.kill()
                    except:
                        pass
            self.active_processes.clear()

    def update(self, status: dict, media_title_or_id: str):
        if not self.config.get("rpc_preview_enabled", False):
            return
        if not self.is_youtube_video(status):
            return
            
        state = status.get("state", "stopped")
        if state != "playing":
            if state == "stopped":
                self.cancel_active_jobs()
            return
            
        pos_sec = int(status.get("position", 0) / 1000)
        bucket_size = self.config.get("rpc_preview_bucket_seconds", 15)
        bucket = (pos_sec // bucket_size) * bucket_size
        
        media_id = self.get_media_id(media_title_or_id, status)
        cache_key = f"{media_id}_b{bucket}"
        
        # Check if media changed
        if media_id != self.current_media_id:
            self.current_media_id = media_id
            self.active_previews.clear()
            self.last_bucket = None
            self.pending_bucket = None
            self.cancel_active_jobs()
            
        # Check if bucket changed
        if bucket != self.last_bucket:
            if bucket != self.pending_bucket:
                self.pending_bucket = bucket
                self.debounce_time = time.time() + 1.5
                logger.info(f"Scheduled preview generation for bucket {bucket} (debounce 1.5s)")
                
            elif time.time() >= self.debounce_time:
                if self.get_active_preview_url(status, media_title_or_id) is not None:
                    self.last_bucket = bucket
                    self.pending_bucket = None
                    return
                    
                self.last_bucket = bucket
                self.pending_bucket = None
                self.cancel_active_jobs()
                
                t = threading.Thread(
                    target=self._generation_worker,
                    args=(status, media_id, bucket, cache_key),
                    daemon=True
                )
                self.active_thread = t
                t.start()

    def _generation_worker(self, status: dict, media_id: str, bucket: int, cache_key: str):
        logger.info(f"Starting preview generation thread for {cache_key}")
        try:
            ytdlp_bin = self._resolve_binary("yt-dlp", "rpc_preview_ytdlp_path")
            ffmpeg_bin = self._resolve_binary("ffmpeg", "rpc_preview_ffmpeg_path")
            ffprobe_bin = self._resolve_binary("ffprobe", "rpc_preview_ffprobe_path")
            
            source_url = status.get("page_url") or status.get("stream_url")
            direct_url = self._resolve_direct_url(source_url, ytdlp_bin)
            if not direct_url:
                logger.warning("Could not resolve direct video stream URL.")
                return
                
            fps = self._get_video_fps(direct_url, ffprobe_bin)
            logger.info(f"Detected FPS: {fps}")
            
            temp_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "rpc_artwork_cache",
                "temp"
            )
            os.makedirs(temp_dir, exist_ok=True)
            output_file = os.path.join(temp_dir, f"preview_{cache_key}_{int(time.time())}.webp")
            
            start_time = max(0, bucket + 1)
            success = self._generate_webp_ladder(direct_url, start_time, fps, ffmpeg_bin, output_file)
            if not success or not os.path.exists(output_file):
                logger.warning("Failed to generate animated WebP.")
                return
                
            expire = self.config.get("rpc_preview_expire", 172800)
            dl_url = self._upload_file(output_file, expire)
            
            try:
                os.remove(output_file)
            except:
                pass
                
            if dl_url:
                with self.lock:
                    self.active_previews[cache_key] = dl_url
                    self.history[cache_key] = {
                        "url": dl_url,
                        "expires_at": time.time() + expire
                    }
                    self._save_history()
                logger.info(f"Successfully activated live animated WebP for {cache_key}: {dl_url}")
            else:
                logger.warning("Upload failed.")
                
        except Exception as e:
            logger.error(f"Error in preview generation thread: {e}", exc_info=True)

    def _resolve_direct_url(self, source_url: str, ytdlp_bin: str) -> str:
        cmd = [
            ytdlp_bin,
            "-g",
            "--no-playlist",
            "--no-warnings",
            source_url
        ]
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0
            )
            with self.lock:
                self.active_processes.append(process)
            stdout, stderr = process.communicate(timeout=10)
            with self.lock:
                if process in self.active_processes:
                    self.active_processes.remove(process)
            if process.returncode == 0 and stdout.strip():
                return stdout.strip().split("\n")[0]
        except Exception as e:
            logger.error(f"Error running yt-dlp: {e}")
        return None

    def _get_video_fps(self, direct_url: str, ffprobe_bin: str) -> float:
        cmd = [
            ffprobe_bin,
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate",
            "-of", "default=noprint_wrappers=1:nokey=1",
            direct_url
        ]
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0
            )
            with self.lock:
                self.active_processes.append(process)
            stdout, stderr = process.communicate(timeout=8)
            with self.lock:
                if process in self.active_processes:
                    self.active_processes.remove(process)
            if process.returncode == 0 and stdout.strip():
                fps_str = stdout.strip()
                if "/" in fps_str:
                    num, den = fps_str.split("/")
                    return float(num) / float(den)
                return float(fps_str)
        except Exception as e:
            logger.error(f"Error running ffprobe: {e}")
        return 24.0

    def _generate_webp_ladder(self, direct_url: str, start_time: int, fps: float, ffmpeg_bin: str, output_file: str) -> bool:
        width = self.config.get("rpc_preview_width", 1024)
        height = self.config.get("rpc_preview_height", 1024)
        quality = self.config.get("rpc_preview_quality", 60)
        compression = self.config.get("rpc_preview_compression", 4)
        duration = self.config.get("rpc_preview_duration", 3)
        fit = self.config.get("rpc_preview_fit", "contain")
        
        target_fps = min(fps, 15.0)
        
        logger.info("Executing WebP generation Step 1 (high quality)")
        success = self._run_ffmpeg(direct_url, start_time, duration, target_fps, width, height, quality, compression, fit, ffmpeg_bin, output_file)
        if not success or not os.path.exists(output_file):
            return False
            
        size_mb = os.path.getsize(output_file) / (1024 * 1024)
        logger.info(f"Step 1 size: {size_mb:.2f} MB")
        
        if size_mb <= 4.0:
            return True
            
        logger.warning(f"WebP exceeds 4MB ({size_mb:.2f} MB). Trying safety downscaling Step 2...")
        
        width_step2 = int(width * 0.75)
        height_step2 = int(height * 0.75)
        quality_step2 = int(quality * 0.75)
        target_fps_step2 = min(target_fps, 10.0)
        
        success = self._run_ffmpeg(direct_url, start_time, duration, target_fps_step2, width_step2, height_step2, quality_step2, compression, fit, ffmpeg_bin, output_file)
        if not success or not os.path.exists(output_file):
            return False
            
        size_mb = os.path.getsize(output_file) / (1024 * 1024)
        logger.info(f"Step 2 size: {size_mb:.2f} MB")
        
        if size_mb <= 8.0:
            return True
            
        logger.error(f"WebP exceeds 8MB safety threshold ({size_mb:.2f} MB). Dropping preview.")
        try:
            os.remove(output_file)
        except:
            pass
        return False

    def _run_ffmpeg(self, direct_url: str, start_time: int, duration: int, fps: float, 
                    width: int, height: int, quality: int, compression: int, 
                    fit: str, ffmpeg_bin: str, output_file: str) -> bool:
        if fit == "contain":
            filter_complex = (
                f"[0:v]fps={fps},scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},boxblur=40:10[bg];"
                f"[0:v]fps={fps},scale={width}:{height}:force_original_aspect_ratio=decrease[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2"
            )
            filter_args = ["-filter_complex", filter_complex]
        else:
            filter_args = [
                "-vf", 
                f"fps={fps},scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black"
            ]
            
        cmd = [
            ffmpeg_bin,
            "-y",
            "-ss", str(start_time),
            "-i", direct_url,
            "-t", str(duration)
        ] + filter_args + [
            "-c:v", "libwebp_anim",
            "-quality", str(quality),
            "-compression_level", str(compression),
            "-loop", "0",
            "-an",
            output_file
        ]
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0
            )
            with self.lock:
                self.active_processes.append(process)
            stdout, stderr = process.communicate(timeout=25)
            with self.lock:
                if process in self.active_processes:
                    self.active_processes.remove(process)
            if process.returncode == 0:
                return True
            else:
                logger.error(f"ffmpeg error: {stderr}")
        except Exception as e:
            logger.error(f"Error running ffmpeg: {e}")
        return False

    def _upload_file(self, file_path: str, expire: int) -> str:
        try:
            url = "https://tmpfiles.org/api/v1/upload"
            with open(file_path, "rb") as f:
                files = {"file": f}
                data = {"expire": str(expire)}
                response = requests.post(url, files=files, data=data, timeout=20)
            if response.status_code == 200:
                res_data = response.json()
                if res_data.get("status") == "success":
                    page_url = res_data.get("data", {}).get("url")
                    if page_url:
                        dl_url = page_url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
                        return dl_url
            logger.error(f"Upload failed: status={response.status_code} body={response.text}")
        except Exception as e:
            logger.error(f"Exception during upload: {e}")
        return None
