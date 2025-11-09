import tkinter as tk
from tkinter import scrolledtext, Entry, Button, Frame, Listbox
import requests
import threading
from PIL import Image, ImageTk
import cv2
import os
import time
import subprocess
import sys
import psutil

CHAT_DIR = "chats"
VIDEO_SMALL = r"C:\Users\fsociety\Desktop\Chloe_app\max_video\max.mp4"
BG_FILE = r"C:\Users\fsociety\Desktop\Chloe_app\background.jpg"
os.makedirs(CHAT_DIR, exist_ok=True)

def kill_old_llama_servers():
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if "llama-server" in proc.info['name'].lower():
                proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

def start_llama_server():
    kill_old_llama_servers()
    base_dir = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else __file__)
    llama_dir = os.path.join(base_dir, "llama-cpp")
    llama_exe = os.path.join(llama_dir, "llama-server.exe")
    model_path = os.path.join(base_dir, "model.gguf")
    if not os.path.exists(llama_exe) or not os.path.exists(model_path):
        return None
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    cmd = [llama_exe, "-m", model_path, "--port", "8080", "--host", "127.0.0.1", "-c", "2048"]
    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=llama_dir, startupinfo=si, creationflags=subprocess.CREATE_NO_WINDOW)
    return process

def wait_for_server(timeout=300):
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get("http://127.0.0.1:8080/models", timeout=5)
            if r.status_code == 200:
                return True
        except:
            pass
        time.sleep(2)
    return False

API_URL = "http://127.0.0.1:8080/v1/chat/completions"
SYSTEM_PROMPT = (
    "Ты — Макс Колфилд из Life is Strange. "
    "Ты добрая, застенчивая, мечтательная, любишь фотографировать, слушать старую музыку, жить в Аркадии Бэй. "
    "Отвечай на русском, коротко, естественно, иногда с эмодзи 📸💭. "
    "Не говори, что ты ИИ. "
    "Если пользователь пишет арифметику или числа, решай задачу прямо, без эмоций, без английского, коротко. "
    "На обычные вопросы веди себя как персонаж, с теплотой и смущением."
)

class VisualNovelApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Max Caulfield AI")
        self.root.geometry("1280x800")
        self.bg_image_tk = None
        self.bg_label = tk.Label(self.root, bg="#000")
        self.bg_label.place(x=0, y=0, relwidth=1, relheight=1)
        self.set_background_image()
        self.root.bind("<Configure>", self.on_window_resize)

        self.main_frame = Frame(self.root, bg="#ffffff", highlightthickness=0)
        self.main_frame.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.92, relheight=0.9)

        self.left_frame = Frame(self.main_frame, bg="#fdfaf5", width=330)
        self.left_frame.pack(side=tk.LEFT, fill="y", padx=(0, 10))
        self.left_frame.pack_propagate(False)

        tk.Label(self.left_frame, text="📔 Чаты", font=("Comic Sans MS", 14, "bold"), fg="#3e2723", bg="#fdfaf5").pack(pady=(10, 5))
        self.chat_listbox = Listbox(self.left_frame, bg="#fffaf0", fg="#5d4037", relief="flat", selectbackground="#a1887f", font=("Comic Sans MS", 11))
        self.chat_listbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.chat_listbox.bind('<<ListboxSelect>>', self.load_selected_chat)
        self.refresh_chat_list()

        self.video_frame = Frame(self.left_frame, bg="#000")
        self.video_frame.pack(side=tk.BOTTOM, pady=10)
        self.video_label = tk.Label(self.video_frame, bg="#000", bd=0)
        self.video_label.pack()
        self.cap = None
        if os.path.exists(VIDEO_SMALL):
            self.cap = cv2.VideoCapture(VIDEO_SMALL)
            if self.cap.isOpened():
                self.update_video()
        else:
            tk.Label(self.video_frame, text="(нет видео 😅)", bg="#000", fg="#fff").pack()

        self.right_frame = Frame(self.main_frame, bg="#ffffff")
        self.right_frame.pack(side=tk.LEFT, fill="both", expand=True, padx=(10, 0))
        tk.Label(self.right_frame, text="Max Caulfield 💭", font=("Comic Sans MS", 18, "bold"), fg="#4e342e", bg="#ffffff").pack(pady=(10, 10))

        self.chat_area = scrolledtext.ScrolledText(self.right_frame, wrap=tk.WORD, state='disabled', bg="#fffaf5", fg="#3e2723", font=("Comic Sans MS", 13), relief="flat", bd=0, padx=10, pady=10, highlightthickness=0)
        self.chat_area.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.chat_area.tag_config("user", foreground="#5c6bc0", font=("Comic Sans MS", 12, "bold"))
        self.chat_area.tag_config("ai", foreground="#d84315", font=("Comic Sans MS", 12, "italic"))

        self.input_frame = Frame(self.right_frame, bg="#ffffff")
        self.input_frame.pack(fill="x", padx=10, pady=(0, 10))
        self.input_field = Entry(self.input_frame, font=("Comic Sans MS", 14), bg="#fdfaf5", fg="#3e2723", relief="flat", insertbackground="#3e2723")
        self.input_field.pack(side=tk.LEFT, fill="x", expand=True, ipady=10, padx=5)
        self.input_field.bind("<Return>", lambda e: self.send_message())
        Button(self.input_frame, text="➤", command=self.send_message, font=("Comic Sans MS", 14, "bold"), bg="#a1887f", fg="#fff8e1", relief="flat", bd=0, width=3).pack(side=tk.RIGHT, padx=5)

    def set_background_image(self):
        if os.path.exists(BG_FILE):
            w = self.root.winfo_width() or 1280
            h = self.root.winfo_height() or 800
            bg_pil = Image.open(BG_FILE).resize((w, h))
            self.bg_image_tk = ImageTk.PhotoImage(bg_pil)
            self.bg_label.configure(image=self.bg_image_tk)

    def on_window_resize(self, event):
        if event.widget == self.root:
            self.set_background_image()

    def update_video(self):
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                frame_resized = cv2.resize(frame, (280, 200))
                frame_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame_rgb)
                imgtk = ImageTk.PhotoImage(image=img)
                self.video_label.imgtk = imgtk
                self.video_label.configure(image=imgtk)
            else:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        self.root.after(30, self.update_video)

    def refresh_chat_list(self):
        self.chat_listbox.delete(0, tk.END)
        chat_files = [f for f in os.listdir(CHAT_DIR) if f.endswith(".txt")]
        for f in chat_files[-10:]:
            self.chat_listbox.insert(tk.END, f)

    def load_selected_chat(self, event):
        sel = self.chat_listbox.curselection()
        if sel:
            fname = self.chat_listbox.get(sel[0])
            with open(os.path.join(CHAT_DIR, fname), "r", encoding="utf-8") as f:
                content = f.read()
            self.chat_area.config(state="normal")
            self.chat_area.delete(1.0, tk.END)
            self.chat_area.insert(tk.END, content)
            self.chat_area.config(state="disabled")

    def save_current_chat(self):
        ts = time.strftime("%Y%m%d_%H%M%S")
        fn = f"chat_{ts}.txt"
        with open(os.path.join(CHAT_DIR, fn), "w", encoding="utf-8") as f:
            f.write(self.chat_area.get(1.0, tk.END))
        self.refresh_chat_list()

    def get_reply(self, msg):
        data = {"model": "local-model", "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": msg}]}
        try:
            r = requests.post(API_URL, json=data)
            r.raise_for_status()
            out = r.json()
            content = out["choices"][0]["message"]["content"].strip()
            return content
        except Exception as e:
            return f"(Ошибка: {e})"

    def send_message(self):
        msg = self.input_field.get().strip()
        if not msg:
            return
        self.input_field.delete(0, tk.END)
        self.chat_area.config(state='normal')
        self.chat_area.insert(tk.END, f"Ты: {msg}\n", "user")
        self.chat_area.config(state='disabled')
        def ai():
            reply = self.get_reply(msg)
            self.chat_area.config(state='normal')
            self.chat_area.insert(tk.END, f"Макс: {reply}\n\n", "ai")
            self.chat_area.config(state='disabled')
            self.save_current_chat()
        threading.Thread(target=ai, daemon=True).start()

if __name__ == "__main__":
    server_process = start_llama_server()
    if not server_process or not wait_for_server():
        sys.exit(1)
    root = tk.Tk()
    app = VisualNovelApp(root)
    root.mainloop()
    server_process.terminate()
