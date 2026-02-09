import os
import sys
import customtkinter
import threading
import subprocess
from tkinter import filedialog
from pytubefix import YouTube
import certifi

os.environ["SSL_CERT_FILE"] = certifi.where()

APP_NAME = "Vortex"
THEME_COLOR = "dark-blue"
SUCCESS_COLOR = "#2CC985"
ERROR_COLOR = "#FF4B4B"

customtkinter.set_appearance_mode("Dark")
customtkinter.set_default_color_theme(THEME_COLOR)

user_home = os.path.expanduser("~")
download_path = os.path.join(user_home, 'Downloads')
yt_object = None  
last_progress = -1

def get_ffmpeg_path():
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, "ffmpeg") if os.name != 'nt' else os.path.join(sys._MEIPASS, "ffmpeg.exe")
    return "ffmpeg"

def thread_safe_update(func, *args, **kwargs):
    def wrapper():
        func(*args, **kwargs)
        root.update_idletasks() 
    root.after(0, wrapper)

def sanitize_filename(name):
    return "".join([c for c in name if c.isalpha() or c.isdigit() or c==' ' or c=='-']).rstrip()

def update_status(message, color="white"):
    thread_safe_update(lambda: status_label.configure(text=message, text_color=color))

def update_progress(percentage, text):
    def _update():
        progress_label.configure(text=text)
        progress_bar.set(percentage)
    thread_safe_update(_update)

def select_folder():
    global download_path
    folder_selected = filedialog.askdirectory()
    if folder_selected:
        download_path = folder_selected
        path_display.configure(text=f".../{os.path.basename(download_path)}")

def on_progress(stream, chunk, bytes_remaining):
    global last_progress
    total_size = stream.filesize
    bytes_downloaded = total_size - bytes_remaining
    percentage = bytes_downloaded / total_size
    
    current_prog_int = int(percentage * 100)
    
    if current_prog_int > last_progress or current_prog_int == 0:
        per_text = f"{current_prog_int}%"
        update_progress(percentage, per_text)
        last_progress = current_prog_int
        
        if current_prog_int == 100:
            last_progress = -1

def merge_files(video_path, audio_path, output_path):
    ffmpeg_path = get_ffmpeg_path()
    try:
        cmd = [
            ffmpeg_path, '-y', '-i', video_path, '-i', audio_path, 
            '-c:v', 'copy', '-c:a', 'aac', '-ac', '2', output_path
        ]
        
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)
        return True
    except FileNotFoundError:
        return "FFMPEG_MISSING"
    except Exception as e:
        return str(e)

def search_logic():
    global yt_object
    try:
        update_status("Fetching metadata...", "#3498db")
        thread_safe_update(lambda: search_btn.configure(state="disabled"))
        thread_safe_update(lambda: progress_bar.configure(mode="indeterminate"))
        thread_safe_update(progress_bar.start)
        
        url = url_entry.get()
        if not url:
            update_status("Please paste a URL first", ERROR_COLOR)
            return

        yt_object = YouTube(url, on_progress_callback=on_progress)
        
        thread_safe_update(lambda: video_title_label.configure(text=yt_object.title))
        
        streams = yt_object.streams.filter(only_video=True, file_extension='mp4')
        
        unique_res = list(set([s.resolution for s in streams if s.resolution]))
        
        def get_res_val(res_string):
            try:
                return int("".join([c for c in res_string if c.isdigit()]))
            except: 
                return 0

        resolutions = sorted(unique_res, key=get_res_val, reverse=True)
        
        if not resolutions:
            update_status("No MP4 streams found", ERROR_COLOR)
            return

        def update_menu():
            res_menu.configure(values=resolutions)
            res_menu.set(resolutions[0])
            res_menu.configure(state="normal")
            download_btn.configure(state="normal", fg_color=SUCCESS_COLOR)
        
        thread_safe_update(update_menu)
        update_status("Ready to download", SUCCESS_COLOR)
        
    except Exception as e:
        update_status(f"Error: {str(e)}", ERROR_COLOR) 
        print(e)
    finally:
        thread_safe_update(progress_bar.stop)
        thread_safe_update(lambda: progress_bar.configure(mode="determinate"))
        thread_safe_update(lambda: progress_bar.set(0))
        thread_safe_update(lambda: search_btn.configure(state="normal"))

def download_logic():
    global yt_object
    try:
        if not yt_object: return
        
        thread_safe_update(lambda: download_btn.configure(state="disabled"))
        selected_res = res_menu.get()
        safe_title = sanitize_filename(yt_object.title)
        
        prog_stream = yt_object.streams.filter(progressive=True, res=selected_res, file_extension='mp4').first()

        if prog_stream:
            update_status(f"Downloading {selected_res} (Fast)...", "#3498db")
            prog_stream.download(download_path, filename=f"{safe_title}.mp4")
            update_status("Download Complete!", SUCCESS_COLOR)
        else:
            update_status(f"Downloading HQ Video ({selected_res})...", "#e67e22")
            
            temp_vid = os.path.join(download_path, "temp_v.mp4")
            temp_aud = os.path.join(download_path, "temp_a.mp4")
            final_out = os.path.join(download_path, f"{safe_title}.mp4")

            vid_stream = yt_object.streams.filter(res=selected_res, only_video=True).first()
            
            if vid_stream: 
                vid_stream.download(download_path, filename="temp_v.mp4")
                
                thread_safe_update(lambda: progress_bar.set(0))
                update_status("Downloading HQ Audio...", "#e67e22")
                
                aud_stream = yt_object.streams.get_audio_only()
                if aud_stream:
                    aud_stream.download(download_path, filename="temp_a.mp4")
                
                    update_status("Processing (Merging)...", "#9b59b6")
                    result = merge_files(temp_vid, temp_aud, final_out)
                    
                    if os.path.exists(temp_vid): os.remove(temp_vid)
                    if os.path.exists(temp_aud): os.remove(temp_aud)

                    if result is True:
                        update_status("Saved to Downloads!", SUCCESS_COLOR)
                    elif result == "FFMPEG_MISSING":
                        update_status("Error: FFmpeg missing", ERROR_COLOR)
                    else:
                        update_status("Merge Failed", ERROR_COLOR)
                else:
                    update_status("Error: No Audio Found", ERROR_COLOR)
            else:
                update_status(f"Error: Stream {selected_res} unavailable", ERROR_COLOR)
            
    except Exception as e:
        update_status(f"Error: {str(e)}", ERROR_COLOR)
    finally:
        thread_safe_update(lambda: download_btn.configure(state="normal"))

def run_search(): threading.Thread(target=search_logic, daemon=True).start()
def run_download(): threading.Thread(target=download_logic, daemon=True).start()

root = customtkinter.CTk()
root.geometry("600x550")
root.title(f"{APP_NAME} | High-Res Downloader")

try:
    root.iconbitmap("icon.ico")
except:
    pass
root.resizable(False, False)

header_frame = customtkinter.CTkFrame(root, corner_radius=0, fg_color="transparent")
header_frame.pack(pady=20)

app_logo = customtkinter.CTkLabel(header_frame, text="VORTEX", font=("Futura", 32, "bold"), text_color="white")
app_logo.pack()

subtitle = customtkinter.CTkLabel(header_frame, text="YouTube Downloader & Converter", font=("Arial", 12), text_color="gray")
subtitle.pack()

input_frame = customtkinter.CTkFrame(root, fg_color="transparent")
input_frame.pack(pady=10, padx=20, fill="x")

url_entry = customtkinter.CTkEntry(input_frame, placeholder_text="Paste YouTube Link Here...", height=40, font=("Arial", 14))
url_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

search_btn = customtkinter.CTkButton(input_frame, text="SEARCH", width=100, height=40, command=run_search, font=("Arial", 12, "bold"))
search_btn.pack(side="right")

info_frame = customtkinter.CTkFrame(root, border_color="#333", border_width=2)
info_frame.pack(pady=20, padx=20, fill="x")

video_title_label = customtkinter.CTkLabel(info_frame, text="Waiting for link...", font=("Arial", 16, "bold"), wraplength=500)
video_title_label.pack(pady=(15, 5), padx=10)

settings_row = customtkinter.CTkFrame(info_frame, fg_color="transparent")
settings_row.pack(pady=10)

res_menu = customtkinter.CTkOptionMenu(settings_row, values=["Quality"], state="disabled", width=120)
res_menu.pack(side="left", padx=10)

folder_btn = customtkinter.CTkButton(settings_row, text="Folder", width=80, fg_color="#555", hover_color="#666", command=select_folder)
folder_btn.pack(side="left", padx=10)

path_display = customtkinter.CTkLabel(settings_row, text=".../Downloads", text_color="gray", font=("Arial", 10))
path_display.pack(side="left")

status_frame = customtkinter.CTkFrame(root, fg_color="transparent")
status_frame.pack(pady=(10, 0), padx=20, fill="x")

status_label = customtkinter.CTkLabel(status_frame, text="Idle", font=("Arial", 12))
status_label.pack(side="left")

progress_label = customtkinter.CTkLabel(status_frame, text="0%", font=("Arial", 12))
progress_label.pack(side="right")

progress_bar = customtkinter.CTkProgressBar(root, height=12, progress_color=SUCCESS_COLOR)
progress_bar.set(0)
progress_bar.pack(pady=5, padx=20, fill="x")

download_btn = customtkinter.CTkButton(root, text="DOWNLOAD VIDEO", height=50, command=run_download, 
                                       font=("Arial", 18, "bold"), state="disabled", fg_color="#444")
download_btn.pack(pady=20, padx=40, fill="x")

footer = customtkinter.CTkLabel(root, text="Powered by Python & FFmpeg", font=("Arial", 10), text_color="#444")
footer.pack(side="bottom", pady=10)

root.lift()
root.attributes('-topmost',True)
root.after_idle(root.attributes,'-topmost',False)

root.mainloop()