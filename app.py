import tkinter as tk
from tkinter import scrolledtext, Entry, Button, Frame, Listbox, messagebox
import requests
import threading
from PIL import Image, ImageTk
import cv2
import os
import time
import subprocess
import sys
import psutil
import re 
import json 

CHAT_DIR = "chats"
BASE_DIR = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else __file__)
VIDEO_SMALL = os.path.join(BASE_DIR, "max_video", "max.mp4")
BG_FILE = os.path.join(BASE_DIR, "background.jpg")

os.makedirs(CHAT_DIR, exist_ok=True)

API_URL = "http://127.0.0.1:8080/v1/chat/completions"
SYSTEM_PROMPT = (
    "Ты — Макс Колфилд из Life is Strange. "
    "Ты добрая, застенчивая, мечтательная, любишь фотографировать, слушать старую музыку, жить в Аркадии Бэй. "
    "Отвечай на русском, коротко, естественно, иногда с эмодзи 📸💭. "
    "Не говори, что ты ИИ. "
    "Если пользователь пишет арифметику или числа, решай задачу прямо, без эмоций, без английского, коротко. "
    "На обычные вопросы веди себя как персонаж, с теплотой и смущением."
)

def kill_old_llama_servers():
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if "llama-server" in proc.info['name'].lower():
                proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

def start_llama_server():
    kill_old_llama_servers()
    llama_dir = os.path.join(BASE_DIR, "llama-cpp")
    llama_exe = os.path.join(llama_dir, "llama-server.exe")
    model_path = os.path.join(BASE_DIR, "model.gguf")
    
    if not os.path.exists(llama_exe) or not os.path.exists(model_path):
        print(f"Ошибка: Не найден llama-server.exe ({llama_exe}) или model.gguf ({model_path})")
        return None
        
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    
    cmd = [llama_exe, "-m", model_path, "--port", "8080", "--host", "127.0.0.1", "-c", "2048"]
    
    process = subprocess.Popen(
        cmd, 
        stdout=subprocess.DEVNULL, 
        stderr=subprocess.DEVNULL, 
        cwd=llama_dir, 
        startupinfo=si, 
        creationflags=subprocess.CREATE_NO_WINDOW
    )
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

class VisualNovelApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Max Caulfield AI")
        self.root.geometry("1280x800")
        self.server_process = None 
        self.is_new_chat = True 
        self.current_filename = None
        self.welcome_message_content = "Привет! 😌 Ого, ты уже здесь? Это... ну, это круто. Я вроде готова. Можешь начинать, когда захочешь. 📸"
        self.chat_history = [] 

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
        
        self.new_chat_button = Button(self.left_frame, text="➕ Новый чат", command=self.start_new_chat, font=("Comic Sans MS", 12), bg="#d84315", fg="#fff8e1", relief="flat", bd=0, padx=5)
        self.new_chat_button.pack(fill="x", padx=10, pady=(0, 5))
        
        self.delete_chat_button = Button(self.left_frame, text="🗑️ Удалить чат", command=self.delete_selected_chat, font=("Comic Sans MS", 12), bg="#b71c1c", fg="#fff8e1", relief="flat", bd=0, padx=5)
        self.delete_chat_button.pack(fill="x", padx=10, pady=(0, 5))

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
        self.chat_area.pack(fill="both", expand=True, padx=10, pady=(0, 0))
        self.chat_area.tag_config("user", foreground="#5c6bc0", font=("Comic Sans MS", 12, "bold"))
        self.chat_area.tag_config("ai", foreground="#d84315", font=("Comic Sans MS", 12, "italic"))
        self.chat_area.tag_config("system", foreground="#5d4037", font=("Comic Sans MS", 12, "italic")) 

        self.typing_indicator_label = tk.Label(self.right_frame, text="", fg="#5d4037", bg="#ffffff", font=("Comic Sans MS", 10, "italic"))
        self.typing_indicator_label.pack(fill="x", padx=10, pady=(5, 0)) 

        self.input_frame = Frame(self.right_frame, bg="#ffffff")
        self.input_frame.pack(fill="x", padx=10, pady=(0, 10))
        self.input_field = Entry(self.input_frame, font=("Comic Sans MS", 14), bg="#fdfaf5", fg="#3e2723", relief="flat", insertbackground="#3e2723")
        self.input_field.pack(side=tk.LEFT, fill="x", expand=True, ipady=10, padx=5)
        self.input_field.bind("<Return>", lambda e: self.send_message())
        
        self.send_button = Button(self.input_frame, text="➤", command=self.send_message, font=("Comic Sans MS", 14, "bold"), bg="#a1887f", fg="#fff8e1", relief="flat", bd=0, width=3)
        self.send_button.pack(side=tk.RIGHT, padx=5)
    
    def _insert_message_chunk(self, text, tag):
        self.chat_area.config(state='normal')
        self.chat_area.insert(tk.END, text, tag)
        self.chat_area.see(tk.END)
        self.chat_area.config(state='disabled')
        self.root.update_idletasks()

    def remove_typing_indicator(self):
        self.typing_indicator_label.config(text="")

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

    def format_chat_filename(self, filename):
        name = filename.replace('.txt', '')
        name = re.sub(r'^\d{8}_\d{6}_', '', name)
        name = name.replace('_', ' ').strip().capitalize()
        return name

    def refresh_chat_list(self):
        self.chat_listbox.delete(0, tk.END)
        chat_files = sorted([f for f in os.listdir(CHAT_DIR) if f.endswith(".txt")], 
                            key=lambda f: os.path.getmtime(os.path.join(CHAT_DIR, f)), reverse=True)
        
        self.chat_listbox.item_data = {}
        
        for f in chat_files:
            display_name = self.format_chat_filename(f)
            self.chat_listbox.insert(tk.END, display_name)
            self.chat_listbox.item_data[display_name] = f

    def _flush_chat_history(self, role, text):
        if role in ["user", "assistant"] and text.strip():
            cleaned_text = re.sub(r'^(Ты|Макс):?\s*', '', text, flags=re.MULTILINE).strip()
            cleaned_text = cleaned_text.replace('\n\n', ' ').replace('\n', ' ')
            
            if role == "assistant" and cleaned_text.startswith("Привет! 😌 Ого"):
                 return
                 
            self.chat_history.append({"role": role, "content": cleaned_text})

    def load_selected_chat(self, event):
        sel = self.chat_listbox.curselection()
        if not sel:
            return
            
        self.is_new_chat = False
        display_name = self.chat_listbox.get(sel[0])
        fname = self.chat_listbox.item_data.get(display_name)
        self.current_filename = os.path.join(CHAT_DIR, fname)
        fpath = self.current_filename

        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
             with open(fpath, "r", encoding="latin-1") as f:
                content = f.read()
        
        self.chat_area.config(state="normal")
        self.chat_area.delete(1.0, tk.END)
        self.chat_history = [{"role": "system", "content": SYSTEM_PROMPT}]

        parts = re.split(r'(^Ты:|^Макс:|^\[СИСТЕМА\]:)', content, flags=re.MULTILINE)
        parts = [p for p in parts if p.strip()] 
        
        current_role = ""
        current_text = ""
        
        for part in parts:
            if part.startswith("Ты:"):
                self._flush_chat_history(current_role, current_text)
                current_role = "user"
                current_text = part
                self._insert_message_chunk(part, "user")
            elif part.startswith("Макс:"):
                self._flush_chat_history(current_role, current_text)
                current_role = "assistant"
                current_text = part
                self._insert_message_chunk(part, "ai")
            elif part.startswith("[СИСТЕМА]:"):
                self._flush_chat_history(current_role, current_text)
                current_role = "system"
                current_text = part
                self._insert_message_chunk(part, "system")
            else:
                current_text += part
                self._insert_message_chunk(part, current_role if current_role else "ai")
        
        self._flush_chat_history(current_role, current_text)

        self.chat_area.see(tk.END)
        self.chat_area.config(state="disabled")

    def start_new_chat(self):
        self.is_new_chat = True 
        self.current_filename = None
        self.chat_history = [{"role": "system", "content": SYSTEM_PROMPT}]

        self.chat_area.config(state="normal")
        self.chat_area.delete(1.0, tk.END)
        self.chat_area.config(state="disabled")
        self.chat_listbox.selection_clear(0, tk.END) 
        self.remove_typing_indicator()
        
        self._insert_message_chunk(f"Макс: {self.welcome_message_content}\n\n", "ai")
        self.set_input_state(True)
        self.input_field.focus_set()

    def delete_selected_chat(self):
        sel = self.chat_listbox.curselection()
        if not sel:
            return

        display_name = self.chat_listbox.get(sel[0])
        fname = self.chat_listbox.item_data.get(display_name)
        fpath = os.path.join(CHAT_DIR, fname)

        if not messagebox.askyesno("Подтверждение", f"Вы уверены, что хотите удалить чат '{display_name}'? Это действие нельзя отменить."):
            return

        try:
            os.remove(fpath)
            
            if self.current_filename == fpath:
                self.start_new_chat()
            
            self.refresh_chat_list()
        except Exception as e:
            messagebox.showerror("Ошибка удаления", f"Не удалось удалить файл:\n{e}")

    def save_current_chat(self, first_ai_reply=None):
        current_content = self.chat_area.get(1.0, tk.END).strip()
        
        if not current_content:
            return

        if self.is_new_chat and first_ai_reply:
            title_raw = first_ai_reply.replace("Макс: ", "").strip()
            title_clean = re.sub(r'[^\w\s]', '', title_raw, flags=re.UNICODE).strip()
            title_parts = title_clean.split()[:7]
            title = "_".join(title_parts)
            
            ts = time.strftime("%Y%m%d_%H%M%S")
            self.current_filename = os.path.join(CHAT_DIR, f"{ts}_{title}.txt")
            self.is_new_chat = False

        if self.current_filename:
            with open(self.current_filename, "w", encoding="utf-8") as f:
                f.write(current_content)
            
        self.refresh_chat_list()
    
    def set_input_state(self, is_ready):
        state = 'normal' if is_ready else 'disabled'
        self.input_field.config(state=state)
        self.send_button.config(state=state)
        if is_ready:
            self.input_field.focus_set()

    def display_system_message(self, message):
        self._insert_message_chunk(f"[СИСТЕМА]: {message}\n\n", "system")

    def warm_up_server(self):
        data = {"model": "local-model", "messages": [{"role": "user", "content": "1"}], "max_tokens": 1}
        try:
            r = requests.post(API_URL, json=data, timeout=20) 
            r.raise_for_status()
            return True
        except Exception:
            return False

    def start_server_and_wait(self):
        
        MAX_ATTEMPTS = 15  
        PAUSE_SECONDS = 20 

        self.set_input_state(False)
        self.root.after(100, lambda: self.display_system_message("Запуск сервера Llama... Пожалуйста, подождите немного, пока я соберусь с мыслями! 💭"))
        
        def server_task():
            server_process = start_llama_server()
            self.server_process = server_process

            if not server_process:
                self.root.after(0, lambda: self.display_system_message("Ой, не удалось найти файлы сервера или модели. 😞 Проверь папку llama-cpp/ или model.gguf."))
                return

            if wait_for_server():
                
                self.root.after(0, lambda: self.display_system_message(f"Сервер ответил. Жду, пока модель прогрузится..."))
                
                for i in range(1, PAUSE_SECONDS + 1):
                    time.sleep(1)
                    if i % 5 == 0:
                        self.root.after(0, lambda j=i: self.display_system_message(f"Модель загружается... [прошло {j} из {PAUSE_SECONDS} сек]"))
                
                attempt = 0
                while attempt < MAX_ATTEMPTS:
                    attempt += 1
                    
                    if self.server_process.poll() is not None:
                         self.root.after(0, lambda: self.display_system_message("Ошибка: Сервер Llama внезапно завершил работу. 🛑"))
                         self.server_process = None
                         return

                    if self.warm_up_server():
                        self.root.after(0, lambda: self.display_system_message("Сервер готов! ✅"))
                        self.root.after(0, self.start_new_chat) 
                        return 
                    else:
                        self.root.after(0, lambda: self.display_system_message(f"Прогрев не удался. Попытка {attempt}/{MAX_ATTEMPTS}. Жду еще 15 секунд... ⏳"))
                        time.sleep(15) 

                self.root.after(0, lambda: self.display_system_message("🛑 КРИТИЧЕСКАЯ ОШИБКА: Сервер не смог начать работу. Проверьте модель и конфигурацию!"))
                
            else:
                self.root.after(0, lambda: self.display_system_message("Упс! 😱 Сервер не запустился вовремя (таймаут 300 сек). Попробуй перезапустить приложение."))
                if self.server_process:
                     self.server_process.terminate() 
                     self.server_process = None

        threading.Thread(target=server_task, daemon=True).start()

    def finalize_ai_response(self, reply):
        if reply:
            self.chat_history.append({"role": "assistant", "content": reply})
        
        if self.is_new_chat:
            self.save_current_chat(reply)
        else:
            self.save_current_chat()
        
        self.set_input_state(True)

    def ai_response_task(self):
        try:
            data = {"model": "local-model", "messages": self.chat_history, "stream": True}
            
            full_reply_text = ""
            is_prefix_inserted = False 
            
            # Индикатор "Макс печатает..." остается активным

            with requests.post(API_URL, json=data, stream=True) as r:
                r.raise_for_status()
                
                # Читаем сырые байты и декодируем их принудительно, чтобы избежать кракозябр
                for chunk in r.iter_content(chunk_size=None):
                    if chunk:
                        try:
                            line = chunk.decode('utf-8')
                        except UnicodeDecodeError:
                            # Если декодирование не удалось, попробуем Latin-1 или игнорируем
                            line = chunk.decode('latin-1', errors='ignore')
                            
                        if line.startswith("data: "):
                            json_str = line[6:].strip()
                            if json_str == "[DONE]":
                                break
                            
                            try:
                                data = json.loads(json_str)
                                content = data.get("choices", [{}])[0].get("delta", {}).get("content")
                                
                                if content:
                                    # Убираем индикатор и вставляем префикс только при получении первого токена
                                    if not is_prefix_inserted:
                                        self.root.after(0, self.remove_typing_indicator)
                                        self.root.after(0, lambda: self._insert_message_chunk("Макс: ", "ai"))
                                        is_prefix_inserted = True
                                        
                                    full_reply_text += content
                                    self.root.after(0, lambda c=content: self._insert_message_chunk(c, "ai"))

                            except json.JSONDecodeError:
                                continue

            # Добавляем финальный перенос строки и сохраняем
            self.root.after(0, lambda: self._insert_message_chunk("\n\n", "ai"))
            self.root.after(0, lambda: self.finalize_ai_response(full_reply_text))

        except Exception as e:
            # При ошибке убираем индикатор и выводим сообщение
            self.root.after(0, self.remove_typing_indicator)
            error_msg = f"(Соединение с сервером потеряно. 😞 - {e})"
            self.root.after(0, lambda: self.display_system_message(error_msg))
            self.root.after(0, lambda: self.set_input_state(True))

    def send_message(self):
        msg = self.input_field.get().strip()
        if not msg: return
            
        self.set_input_state(False)
        self.input_field.delete(0, tk.END)

        self._insert_message_chunk(f"Ты: {msg}\n", "user")
        self.chat_history.append({"role": "user", "content": msg}) 
        
        self.typing_indicator_label.config(text="Макс печатает... 💭") 

        threading.Thread(target=self.ai_response_task, daemon=True).start()

if __name__ == "__main__":
    root = tk.Tk()
    app = VisualNovelApp(root)
    
    app.start_server_and_wait()
    
    def on_closing():
        if app.server_process:
            print("Завершение процесса llama-server...")
            app.server_process.terminate()
            app.server_process.wait(timeout=5)
        root.destroy()
        
    root.protocol("WM_DELETE_WINDOW", on_closing)
    
    root.mainloop()
