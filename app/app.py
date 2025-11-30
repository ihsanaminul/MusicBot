import customtkinter as ctk
import os
import sys
import multiprocessing
import queue
import re
import time
import webbrowser
import threading
import pystray
import nacl
import winreg as reg
from PIL import ImageTk, Image, ImageDraw
import subprocess
import requests
import tempfile
import socket
from packaging.version import parse as parse_version

# OpenCV is used for video playback in the tutorial
import cv2

# --- CONFIGURATION ---
APP_NAME = "Playify"
# ==============================================================================
# VERSION MANAGEMENT:
# Increment this version number for each new release.
# Use semantic versioning (e.g., 1.1.1, 1.2.0, 2.0.0).
# The GitHub release tag MUST match this number, prefixed with 'v' (e.g., v1.2.1).
# ==============================================================================
CURRENT_VERSION = "1.3.0"
UPDATE_REPO_URL = "https://api.github.com/repos/alan7383/playify/releases/latest"

# Centralized path for all application data (config, browsers, etc.)
APP_DATA_DIR = os.path.join(os.getenv('LOCALAPPDATA'), APP_NAME)
os.makedirs(APP_DATA_DIR, exist_ok=True)

CONFIG_FILE = os.path.join(APP_DATA_DIR, "playify_config.env")

# --- STYLE CONFIGURATION ---
STYLE = {
    "theme_bg": "#000000",
    "text": "#EAEAEA",
    "text_secondary": "#B0B0B0",
    "accent": "#9B59B6",         # A modern, elegant purple
    "accent_hover": "#8E44AD",
    "success": "#2ECC71",
    "success_hover": "#25a25a",
    "danger": "#E74C3C",
    "danger_hover": "#c0392b",
    "background_light": "#1a1a1a",
    "background_medium": "#0f0f0f",
    "border": "#2c2c2c"
}

# --- HELPERS ---
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # When not bundled, the path is relative to this script's location
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)

def show_message_dialog(parent, title, message):
    """Creates a simple, centered, modal message box."""
    dialog = ctk.CTkToplevel(parent)
    dialog.title(title)
    
    try:
        dialog.iconbitmap(resource_path("assets/images/playify.ico"))
    except Exception as e:
        print(f"Dialog icon error: {e}")

    parent_x = parent.winfo_x()
    parent_y = parent.winfo_y()
    parent_w = parent.winfo_width()
    parent_h = parent.winfo_height()
    dialog_w = 400
    dialog_h = 150
    dialog.geometry(f"{dialog_w}x{dialog_h}+{parent_x + (parent_w - dialog_w) // 2}+{parent_y + (parent_h - dialog_h) // 2}")

    dialog.resizable(False, False)
    dialog.transient(parent)
    dialog.grab_set()

    dialog.grid_columnconfigure(0, weight=1)
    dialog.grid_rowconfigure(0, weight=1)

    message_label = ctk.CTkLabel(dialog, text=message, wraplength=380, justify="center")
    message_label.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")

    ok_button = ctk.CTkButton(dialog, text="OK", width=100, command=dialog.destroy, 
                              fg_color=STYLE["accent"], hover_color=STYLE["accent_hover"])
    ok_button.grid(row=1, column=0, padx=20, pady=(0, 20))
    dialog.after(100, ok_button.focus)

# --- CONFIGURATION MANAGEMENT ---
def load_config():
    """Reads the configuration file and returns a dictionary."""
    config = {
        "CHECK_FOR_UPDATES": "True",
        "PRESENCE_TYPE": "Playing",
        "PRESENCE_ROTATION_COUNT": "3",
        "PRESENCE_ROTATION_DELAY": "15",
        "PRESENCE_1": "/play [link]",
        "PRESENCE_2": "/help",
        "PRESENCE_3": "alan7383.github.io/playify"
    }
    if not os.path.exists(CONFIG_FILE):
        return config
    try:
        with open(CONFIG_FILE, "r", encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    config[key.strip()] = value.strip()
    except Exception as e:
        print(f"Error loading config file: {e}")
    return config

def save_config(config_data):
    """Saves the given dictionary to the configuration file."""
    try:
        with open(CONFIG_FILE, "w", encoding='utf-8') as f:
            # Credentials
            f.write(f"DISCORD_TOKEN={config_data.get('DISCORD_TOKEN', '')}\n")
            f.write(f"SPOTIFY_CLIENT_ID={config_data.get('SPOTIFY_CLIENT_ID', '')}\n")
            f.write(f"SPOTIFY_CLIENT_SECRET={config_data.get('SPOTIFY_CLIENT_SECRET', '')}\n")
            f.write(f"GENIUS_TOKEN={config_data.get('GENIUS_TOKEN', '')}\n")
            # General Settings
            f.write(f"CHECK_FOR_UPDATES={config_data.get('CHECK_FOR_UPDATES', 'True')}\n")
            # Presence Settings
            f.write(f"PRESENCE_TYPE={config_data.get('PRESENCE_TYPE', 'Playing')}\n")
            f.write(f"PRESENCE_ROTATION_COUNT={config_data.get('PRESENCE_ROTATION_COUNT', '3')}\n")
            f.write(f"PRESENCE_ROTATION_DELAY={config_data.get('PRESENCE_ROTATION_DELAY', '15')}\n")
            f.write(f"PRESENCE_1={config_data.get('PRESENCE_1', '/play [link]')}\n")
            f.write(f"PRESENCE_2={config_data.get('PRESENCE_2', '/help')}\n")
            f.write(f"PRESENCE_3={config_data.get('PRESENCE_3', 'alan7383.github.io/playify')}\n")
        return True
    except Exception as e:
        print(f"Error saving config file: {e}")
        return False

# --- FFmpeg Management ---
def setup_ffmpeg():
    app_path = resource_path(".")
    possible_paths = [
        app_path, os.path.join(app_path, "ffmpeg"), os.path.join(app_path, "bin"),
        os.path.join(app_path, "_internal"), os.path.join(app_path, "_internal", "ffmpeg")
    ]
    for path in possible_paths:
        if os.path.exists(os.path.join(path, "ffmpeg.exe")):
            os.environ["PATH"] = path + os.pathsep + os.environ.get("PATH", "")
            break
    os.environ["PATH"] = app_path + os.pathsep + os.environ.get("PATH", "")

setup_ffmpeg()

# --- FONT SETUP ---
try:
    FONT_PATH = resource_path("assets/fonts/SequelGeoWide.ttf")
    ctk.FontManager.load_font(FONT_PATH)
    TITLE_FONT_FAMILY = "Sequel100Black-75"
except Exception:
    TITLE_FONT_FAMILY = "Arial"

# --- MAIN APPLICATION ---
class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        start_minimized = "--minimized" in sys.argv
        if start_minimized:
            self.withdraw()

        self.title(APP_NAME)
        self.geometry("960x720")
        self.minsize(800, 600)
        self.configure(fg_color=STYLE["theme_bg"])
        try:
            self.iconbitmap(resource_path("assets/images/playify.ico"))
        except Exception as e:
            print(f"Icon error: {e}")

        self.playwright_browser_path = os.path.join(APP_DATA_DIR, "playwright_browsers")
        os.makedirs(self.playwright_browser_path, exist_ok=True)

        self.manager = multiprocessing.Manager()
        self.status_queue = self.manager.Queue()
        self.log_queue = self.manager.Queue()
        self.command_queue = self.manager.Queue()

        self.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.bot_process = None
        self.config = load_config()
        self.is_configured = os.path.exists(CONFIG_FILE) and self.config.get("DISCORD_TOKEN")
        
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", side="bottom", pady=5)
        ctk.CTkLabel(footer, text=f"- made by @alananasssss - v{CURRENT_VERSION} -", font=("Arial", 10), text_color="gray").pack()

        self.tray_icon = None
        self.settings_window = None
        self.update_window = None

        if self.is_configured:            
            self.withdraw()
            self.after(100, self.hide_to_tray)
            
            self.show_dashboard()
            self.start_bot_process()
        else:
            self.show_tutorial()

        self.after(1500, self.check_for_updates)

        if start_minimized:
            self.after(100, self.hide_to_tray)

    def switch_page(self, page_class, *args):
        if hasattr(self, 'current_page') and self.current_page:
            self.current_page.destroy()
        self.current_page = page_class(self.main_container, self, *args)
        self.current_page.pack(fill="both", expand=True)

    def show_tutorial(self):
        self.switch_page(StylishTutorialPage)

    def show_dashboard(self):
        self.switch_page(StylishDashboardPage)

    def start_bot_process(self):
        if self.bot_process and self.bot_process.is_alive():
            print("Terminating existing bot process...")
            self.bot_process.terminate()
            self.bot_process.join(timeout=1.0)
            print("Old process terminated.")

        try:
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = self.playwright_browser_path
            # Dynamically import playify_bot to ensure it's loaded after env vars are set
            import playify_bot
            self.bot_process = multiprocessing.Process(
                target=playify_bot.run_bot, args=(self.status_queue, self.log_queue, self.command_queue,), daemon=False
            )
            self.bot_process.start()
            print("New bot process started (non-daemon mode).")

            if not hasattr(self, '_status_checker_running'):
                self.check_bot_status()
                self._status_checker_running = True
            if not hasattr(self, '_log_checker_running'):
                self.check_log_queue()
                self._log_checker_running = True
        except Exception as e:
            self.log_queue.put(f"Failed to start bot process: {e}\n")
            self.status_queue.put("ERROR")

    def check_bot_status(self):
        try:
            status = self.status_queue.get_nowait()
            if isinstance(self.current_page, StylishDashboardPage):
                self.current_page.update_status(status)
        except queue.Empty:
            pass
        self.after(1000, self.check_bot_status)

    def hide_to_tray(self):
            """Hides the window and ensures the taskbar icon is visible."""
            # Always hide the window.
            self.withdraw()
    
            # If a tray icon already exists and is visible, no further action is needed.
            if self.tray_icon and self.tray_icon.visible:
                return
    
            # If we reach this point, no active tray icon exists. Create one.
            icon_path = resource_path("assets/images/playify.ico")
            if not os.path.exists(icon_path):
                print("Error: Tray icon 'playify.ico' not found.")
                return
    
            icon_image = Image.open(icon_path)
            # The menu uses our NEW version of show_from_tray
            menu = (pystray.MenuItem("Show", self.show_from_tray, default=True),
                    pystray.MenuItem("Quit", self.quit_application))
    
            self.tray_icon = pystray.Icon(APP_NAME, icon_image, APP_NAME, menu)
            self.tray_icon.run_detached()
    
            # Display the notification only if the application was not launched minimized.
            if "--minimized" not in sys.argv:
                # Add a short delay to ensure the icon is created before showing the notification bubble.
                self.after(500, lambda: self.tray_icon.notify("Playify is running in the background.", APP_NAME))            

    def show_from_tray(self, icon=None, item=None):
            """
            Displays the main application window.
            IMPORTANT: This version no longer destroys the taskbar icon.
            """
            self.deiconify()  # Displays the window
            self.lift()       # Brings it to the foreground
            self.focus_force()# Gives it focus     

    def quit_application(self, icon=None, item=None):
        """Schedules the complete and robust shutdown of the application."""
        print("Quit command received. Scheduling shutdown.")
        if self.tray_icon:
            self.tray_icon.stop()
        self.after(0, self._perform_shutdown)

    def _perform_shutdown(self):
        """Gracefully shuts down the application, allowing the bot to save its state."""
        print("Initiating shutdown sequence.")
        if self.tray_icon:
            self.tray_icon.stop()

        if self.bot_process and self.bot_process.is_alive():
            print("Bot process is active. Sending shutdown command...")
            
            try:
                self.command_queue.put('QUIT')
                
                # Wait up to 10 seconds for the bot to shut down cleanly
                self.bot_process.join(timeout=10.0) 
            except Exception as e:
                print(f"An error occurred while waiting for the bot to stop: {e}")

            # If the bot is still alive after the grace period, terminate it
            if self.bot_process.is_alive():
                print("Bot did not respond in time. Forcing termination.")
                self.bot_process.terminate()
                self.bot_process.join(timeout=1.0)
                print("Bot process forcefully terminated.")
            else:
                print("Bot process stopped gracefully.")
        
        print("Closing GUI and exiting program.")
        self.destroy()
        sys.exit(0)

    def check_log_queue(self):
        try:
            while not self.log_queue.empty():
                log_message = self.log_queue.get_nowait()
                if isinstance(self.current_page, StylishDashboardPage):
                    self.current_page.add_log_message(log_message)
        except queue.Empty:
            pass
        finally:
            self.after(200, self.check_log_queue)

    def is_in_startup(self):
        try:
            with reg.OpenKey(reg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run", 0, reg.KEY_READ) as key:
                reg.QueryValueEx(key, APP_NAME)
            return True
        except FileNotFoundError:
            return False
        except Exception as e:
            print(f"Failed to check startup status: {e}")
            return False

    def add_to_startup(self):
        try:
            with reg.OpenKey(reg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run", 0, reg.KEY_SET_VALUE) as key:
                reg.SetValueEx(key, APP_NAME, 0, reg.REG_SZ, f'"{sys.executable}" --minimized')
            print("Added to startup with --minimized flag.")
        except Exception as e:
            print(f"Failed to add to startup: {e}")

    def remove_from_startup(self):
        try:
            with reg.OpenKey(reg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run", 0, reg.KEY_SET_VALUE) as key:
                reg.DeleteValue(key, APP_NAME)
            print("Removed from startup.")
        except FileNotFoundError:
            print("App was not in startup, nothing to remove.")
        except Exception as e:
            print(f"Failed to remove from startup: {e}")

    def check_for_updates(self, manual_check=False):
        """
        Checks for updates. If manual_check is True, it will show a
        dialog to the user for "up-to-date" or "error" states.
        """
        if manual_check:
            print("Manual update check initiated...")
        threading.Thread(target=self._run_update_check, args=(manual_check,), daemon=True).start()

    def _run_update_check(self, manual_check=False):
        """The actual checking logic that runs in a background thread."""
        if not manual_check and self.config.get("CHECK_FOR_UPDATES", "True").lower() != 'true':
            print("Update check is disabled by user.")
            return
        try:
            response = requests.get(UPDATE_REPO_URL, timeout=10)
            response.raise_for_status()
            latest_release = response.json()
            latest_version_str = latest_release.get("tag_name", "v0.0.0").lstrip('v')
            
            if parse_version(latest_version_str) > parse_version(CURRENT_VERSION):
                print(f"New version found: {latest_version_str}")
                assets = latest_release.get("assets", [])
                download_url = next((asset.get("browser_download_url") for asset in assets if asset.get("name", "").lower().startswith("playify_setup")), None)
                if download_url:
                    self.after(0, self.prompt_for_update, latest_version_str, download_url, latest_release.get("body"))
                else:
                    print("Update found, but no setup file was located in the release assets.")
            else:
                print("You are running the latest version.")
                if manual_check:
                    self.after(0, show_message_dialog, self, "No Updates Found", "You are currently running the latest version of Playify.")
        except Exception as e:
            print(f"Could not check for updates: {e}")
            if manual_check:
                error_message = "Could not connect to the server to check for updates.\nPlease check your internet connection and try again."
                self.after(0, show_message_dialog, self, "Update Check Failed", error_message)

    def prompt_for_update(self, version, url, release_notes):
        if self.update_window is None or not self.update_window.winfo_exists():
            self.update_window = UpdatePromptWindow(self, version, url, release_notes)
            self.update_window.grab_set()
        else:
            self.update_window.focus()

    def bring_to_front(self):
            """
            Displays the application window, brings it to the foreground,
            without destroying or modifying the taskbar icon.
            """
            self.deiconify()  # Displays the window if it was minimized
            self.lift()       # Brings it above other windows
            self.focus_force()# Gives focus to the window

class UpdatePromptWindow(ctk.CTkToplevel):
    def __init__(self, controller, new_version, download_url, release_notes):
        super().__init__(controller)
        self.controller = controller
        self.download_url = download_url
        self.new_version = new_version

        self.title("Update Available")
        try:
            self.iconbitmap(resource_path("assets/images/playify.ico"))
        except Exception as e:
            print(f"Update window icon error: {e}")
        self.geometry("500x400")
        self.resizable(False, False)
        self.transient(controller)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        ctk.CTkLabel(header_frame, text=f"New Version Available: {self.new_version}", font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(header_frame, text="A new version of Playify is ready to be installed.", text_color="gray").pack(anchor="w")
        self.main_frame = ctk.CTkFrame(self, fg_color=STYLE["background_light"])
        self.main_frame.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=1)
        self.textbox = ctk.CTkTextbox(self.main_frame, wrap="word", fg_color="transparent")
        self.textbox.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.textbox.insert("end", release_notes or "No release notes provided.")
        self.textbox.configure(state="disabled")
        self.progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.progress_frame.grid_columnconfigure(0, weight=1)
        self.progress_title = ctk.CTkLabel(self.progress_frame, text="Downloading update...", font=ctk.CTkFont(size=14))
        self.progress_title.grid(row=0, column=0, padx=10, pady=(10,5), sticky="w")
        self.progress_bar = ctk.CTkProgressBar(self.progress_frame, height=12, progress_color=STYLE["accent"])
        self.progress_bar.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        self.progress_bar.set(0)
        self.progress_details = ctk.CTkLabel(self.progress_frame, text="0%  (0.0 MB / 0.0 MB)", text_color="gray")
        self.progress_details.grid(row=2, column=0, padx=10, pady=5, sticky="e")
        self.button_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.button_frame.grid(row=2, column=0, padx=20, pady=(10, 20), sticky="ew")
        self.install_button = ctk.CTkButton(self.button_frame, text="Install Now", command=self.start_download, 
                                             fg_color=STYLE["accent"], hover_color=STYLE["accent_hover"])
        self.install_button.pack(side="right", padx=(10, 0))
        self.remind_later_button = ctk.CTkButton(self.button_frame, text="Remind Me Later", command=self.on_close,
                                                 fg_color=STYLE["background_light"], hover_color=STYLE["border"])
        self.remind_later_button.pack(side="right", padx=(10, 0))
        self.never_button = ctk.CTkButton(self.button_frame, text="Never Ask Again", fg_color="transparent", text_color="gray", hover=False, command=self.disable_updates)
        self.never_button.pack(side="left")

    def on_close(self):
        self.destroy()

    def disable_updates(self):
        self.controller.config["CHECK_FOR_UPDATES"] = "False"
        save_config(self.controller.config)
        self.destroy()

    def start_download(self):
        self.install_button.configure(state="disabled")
        self.remind_later_button.configure(state="disabled")
        self.never_button.configure(state="disabled")
        self.main_frame.grid_remove()
        self.progress_frame.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        threading.Thread(target=self.download_and_install, daemon=True).start()
    
    def update_progress(self, progress_percent, downloaded_mb, total_mb):
        self.progress_bar.set(progress_percent / 100)
        self.progress_details.configure(text=f"{progress_percent:.1f}%  ({downloaded_mb:.2f} MB / {total_mb:.2f} MB)")

    def download_and_install(self):
        try:
            temp_dir = tempfile.gettempdir()
            filename = self.download_url.split('/')[-1]
            if not filename:
                filename = "playify_setup_update.exe"
            setup_path = os.path.join(temp_dir, filename)

            print(f"Starting download of {self.download_url} to {setup_path}")

            with requests.get(self.download_url, stream=True, timeout=60) as r:
                r.raise_for_status()
                total_size = int(r.headers.get('content-length', 0))
                bytes_downloaded = 0
                last_progress_int = -1

                with open(setup_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            bytes_downloaded += len(chunk)
                            if total_size > 0:
                                progress = (bytes_downloaded / total_size) * 100
                                current_progress_int = int(progress)
                                if current_progress_int > last_progress_int:
                                    downloaded_mb = bytes_downloaded / 1e6
                                    total_mb_float = total_size / 1e6
                                    self.after(0, self.update_progress, progress, downloaded_mb, total_mb_float)
                                    last_progress_int = current_progress_int

            print("Download complete. Scheduling installer launch.")
            self.after(100, self._launch_installer_and_exit, setup_path)

        except Exception as e:
            print(f"Failed to download update: {e}")
            self.after(0, self._handle_update_error, f"Download Error: {e}")

    def _launch_installer_and_exit(self, setup_path):
        """
        Final production version. Creates and launches a silent batch script
        to handle the update process invisibly.
        """
        try:
            self.progress_title.configure(text="Update downloaded. Closing to install...")
            print("Creating final, silent update script...")

            updater_bat_path = os.path.join(tempfile.gettempdir(), "playify_silent_updater.bat")

            batch_script_content = f"""
    @echo off
    rem This script waits for the main app to close, then runs the installer.

    rem Wait for 3 seconds to ensure the main application has fully closed.
    timeout /t 3 /nobreak > NUL

    rem Launch the installer silently and in the background.
    start "" "{setup_path}" /SILENT /NORESTART

    rem A trick to make the script delete itself after execution.
    (goto) 2>nul & del "%~f0"
    """
            with open(updater_bat_path, "w", encoding='utf-8') as f:
                f.write(batch_script_content)

            print(f"Silent update script created at: {updater_bat_path}")

            command_string = f'start /b "" "{updater_bat_path}"'
            subprocess.Popen(command_string, shell=True)

            print("Silent update script launched. Playify will now exit.")
            self.controller._perform_shutdown()

        except Exception as e:
            print(f"Failed to create or launch the silent update script: {e}")
            self._handle_update_error(f"Launch Error: {e}")

    def _handle_update_error(self, error_message):
        """Displays a clear error message in the update window."""
        self.progress_title.configure(text="Error: Could not complete update.", text_color=STYLE["danger"])
        error_text = (error_message[:100] + '...') if len(error_message) > 100 else error_message
        self.progress_details.configure(text=error_text)
        self.remind_later_button.configure(state="normal")


# =========================================================================================
# === STYLISH TUTORIAL PAGE - REDESIGNED ==================================================
# =========================================================================================
class StylishTutorialPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color="transparent")
        self.controller = controller
        self.current_step = 0
        self.config_data = {}
        self.widgets = [] # To hold widgets that need to be cleared between steps

        # --- Fonts ---
        self.title_font = ctk.CTkFont(family=TITLE_FONT_FAMILY, size=28, weight="bold")
        self.step_font = ctk.CTkFont(family="Arial", size=16, weight="bold")
        self.desc_font = ctk.CTkFont(family="Arial", size=14)
        self.link_font = ctk.CTkFont(family="Arial", size=12, underline=True)

        # --- Central Card Layout ---
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        # This card will hold all the content for a step
        self.card_frame = ctk.CTkFrame(self, fg_color=STYLE["background_medium"], corner_radius=12)
        self.card_frame.grid(row=0, column=0, padx=50, pady=30, sticky="nsew")
        self.card_frame.grid_columnconfigure(0, weight=1)
        self.card_frame.grid_rowconfigure(2, weight=1) # The content area will expand

        # --- Card Header ---
        header_frame = ctk.CTkFrame(self.card_frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=30, pady=(20, 10), sticky="ew")
        header_frame.grid_columnconfigure(1, weight=1)

        self.step_label = ctk.CTkLabel(header_frame, text="", font=self.step_font, text_color=STYLE["accent"])
        self.step_label.grid(row=0, column=0, sticky="w")
        
        self.title_label = ctk.CTkLabel(header_frame, text="", font=self.title_font, text_color=STYLE["text"])
        self.title_label.grid(row=1, column=0, columnspan=2, sticky="w")

        # Visual progress indicator (dots)
        self.progress_indicator_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        self.progress_indicator_frame.grid(row=0, column=1, sticky="e", padx=10)

        # Separator line
        separator = ctk.CTkFrame(self.card_frame, height=1, fg_color=STYLE["border"])
        separator.grid(row=1, column=0, padx=30, pady=10, sticky="ew")

        # --- Main Content Area ---
        self.content_container = ctk.CTkFrame(self.card_frame, fg_color="transparent")
        self.content_container.grid(row=2, column=0, padx=30, pady=10, sticky="nsew")
        
        # --- Footer / Navigation ---
        footer_frame = ctk.CTkFrame(self.card_frame, fg_color="transparent")
        footer_frame.grid(row=3, column=0, padx=30, pady=(10, 20), sticky="ew")
        footer_frame.grid_columnconfigure(1, weight=1)
        
        self.prev_button = ctk.CTkButton(footer_frame, text="< Previous", command=self.prev_step, width=120, fg_color="transparent", border_color=STYLE["border"], border_width=2, hover_color=STYLE["background_light"], text_color=STYLE["text"])
        self.prev_button.grid(row=0, column=0, sticky="w")
        
        self.next_button = ctk.CTkButton(footer_frame, text="Next >", command=self.next_step, width=120, fg_color=STYLE["accent"], hover_color=STYLE["accent_hover"], text_color=STYLE["theme_bg"], font=("Arial", 12, "bold"))
        self.next_button.grid(row=0, column=2, sticky="e")

        # --- Step Data ---
        self.steps_info = [
            {"title": "Welcome to Playify!", "desc": "This quick one-time setup will guide you through connecting the bot to Discord and other services. Let's get started!", "video": "1_discord_app.mp4"},
            {"title": "Get Your Bot Token", "desc": "Your bot's token is its secret password. Go to the 'Bot' tab, reset the token, and copy it.\n\nIMPORTANT: Never share this with anyone!", "video": "2_discord_token.mp4", "input": "DISCORD_TOKEN", "regex": r"[\w-]{24,26}\.[\w-]{6,7}\.[\w-]{27,38}", "links": {"Discord Developer Portal": "https://discord.com/developers/applications"}},
            {"title": "Set Up Spotify (Optional)", "desc": "To enable music playback from Spotify, create a Spotify application. In its settings, add the 'Redirect URI' below. This step is optional.", "video": "3_spotify_app.mp4", "links": {"Spotify Developer Dashboard": "https://developer.spotify.com/dashboard"}, "copy_fields": [{"label": "Redirect URI:", "value": "http://127.0.0.1:8000/callback"}], "input": "SPOTIFY_CLIENT_ID", "optional": True},
            {"title": "Get Genius Token (Optional)", "desc": "For lyrics, we need a Genius API Client. The 'App Website URL' isn't critical. This step is optional if you don't need lyrics.", "video": "4_genius_app.mp4", "links": {"Genius API Clients": "https://genius.com/api-clients"}, "copy_fields": [{"label": "Example Website URL:", "value": "https://example.com"}], "input": "GENIUS_TOKEN", "optional": True},
            {"title": "Invite Your Bot", "desc": "Generate an invite link from the 'OAuth2 -> URL Generator' tab. Select the 'bot' & 'applications.commands' scopes, then grant it the necessary permissions to function on your server.", "video": "5_invite_bot.mp4"},
            {"title": "Streaming Services", "desc": "Do you need support for Apple Music, Amazon Music, or Tidal? This requires installing additional components (Playwright).", "choice": "streaming_services"},
            {"title": "Ready to Launch", "desc": "Configuration is complete! Choose your final settings below and click 'Finish' to save everything and start the bot.", "video": None}
        ]
        
        self.update_step_display()

    def _create_progress_indicator(self):
        # Clear previous indicator
        for widget in self.progress_indicator_frame.winfo_children():
            widget.destroy()
        
        for i in range(len(self.steps_info)):
            dot = ctk.CTkFrame(self.progress_indicator_frame, width=8, height=8, corner_radius=4, 
                               fg_color=STYLE["accent"] if i == self.current_step else STYLE["border"])
            dot.pack(side="left", padx=3)
    
    def on_right_frame_configure(self, event):
        if hasattr(self, 'desc_label') and self.desc_label.winfo_exists():
            self.desc_label.configure(wraplength=event.width - 10)

    def open_link(self, url):
        webbrowser.open_new_tab(url)

    def copy_to_clipboard(self, text, button):
        self.controller.clipboard_clear()
        self.controller.clipboard_append(text)
        original_text = button.cget("text")
        button.configure(text="Copied!", state="disabled", fg_color=STYLE["success"], border_color=STYLE["success"])
        self.after(2000, lambda: button.configure(text=original_text, state="normal", fg_color="transparent", border_color=STYLE["border"]))

    def update_step_display(self):
        for widget in self.widgets: widget.destroy()
        self.widgets.clear()
        
        step = self.steps_info[self.current_step]

        # Update header and progress
        self._create_progress_indicator()
        self.step_label.configure(text=f"STEP {self.current_step + 1} OF {len(self.steps_info)}")
        self.title_label.configure(text=step['title'])

        # Configure layout: 50/50 or 100% width
        has_video = "video" in step and step["video"] is not None
        self.content_container.grid_columnconfigure(0, weight=1 if has_video else 0)
        self.content_container.grid_columnconfigure(1, weight=1 if has_video else 1)
        self.content_container.grid_rowconfigure(0, weight=1)

        # Left Panel (Video or Logo)
        left_frame = ctk.CTkFrame(self.content_container, fg_color=STYLE["background_light"], corner_radius=12)
        if has_video:
            left_frame.grid(row=0, column=0, padx=(0, 20), sticky="nsew")
        left_frame.grid_rowconfigure(0, weight=1); left_frame.grid_columnconfigure(0, weight=1)
        self.widgets.append(left_frame)

        if has_video:
            path = resource_path(os.path.join("assets", "videos", step["video"]))
            if os.path.exists(path):
                video_player = VideoPlayerOpenCV(left_frame, path)
                video_player.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
                self.after(100, video_player.play); self.widgets.append(video_player)
            else:
                ctk.CTkLabel(left_frame, text=f"❌\nVideo not found:\n{step['video']}", font=self.desc_font).grid(row=0, column=0)
        else: # Final step has no video
            logo_path = resource_path("assets/images/playify_logo.png")
            if os.path.exists(logo_path):
                logo_label = ctk.CTkLabel(left_frame, image=ctk.CTkImage(Image.open(logo_path), size=(128, 128)), text="")
                logo_label.grid(row=0, column=0, sticky="nsew")
                self.widgets.append(logo_label)

        # Right Panel (Instructions and Inputs)
        right_frame = ctk.CTkScrollableFrame(self.content_container, fg_color="transparent", label_text=None)
        right_frame.grid(row=0, column=1, padx=(10 if has_video else 0, 0), sticky="nsew")
        self.widgets.append(right_frame)

        self.desc_label = ctk.CTkLabel(right_frame, text=step.get("desc", ""), font=self.desc_font, text_color=STYLE["text_secondary"], justify="left")
        self.desc_label.pack(fill="x", pady=(0, 20), anchor="n")
        right_frame.bind("<Configure>", self.on_right_frame_configure)

        if step.get("choice") == "streaming_services": self.handle_streaming_services_step(right_frame)
        else: self.next_button.configure(state="normal")
        
        if "links" in step:
            links_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
            links_frame.pack(fill="x", pady=(0, 20), anchor="n")
            for text, url in step["links"].items():
                link = ctk.CTkLabel(links_frame, text=text, font=self.link_font, text_color="#3498db", cursor="hand2")
                link.pack(side="left", padx=(0, 15)); link.bind("<Button-1>", lambda e, u=url: self.open_link(u))

        if "copy_fields" in step:
            copy_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
            copy_frame.pack(fill="x", pady=(0, 20), anchor="n")
            for field in step["copy_fields"]:
                field_label = ctk.CTkLabel(copy_frame, text=field["label"], font=self.desc_font, text_color="gray"); field_label.pack(fill="x", pady=(5, 2))
                inner_frame = ctk.CTkFrame(copy_frame, fg_color="transparent"); inner_frame.pack(fill="x")
                entry = ctk.CTkEntry(inner_frame, border_width=1, border_color=STYLE["border"], fg_color=STYLE["background_light"]); entry.insert(0, field["value"]); entry.configure(state="readonly"); entry.pack(side="left", expand=True, fill="x", ipady=5)
                button = ctk.CTkButton(inner_frame, text="Copy", width=70, fg_color="transparent", border_width=1, border_color=STYLE["border"]); button.configure(command=lambda v=field["value"], b=button: self.copy_to_clipboard(v, b)); button.pack(side="left", padx=(10, 0))

        if "input" in step:
            input_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
            input_frame.pack(fill="x", pady=(0, 20), anchor="n")
            placeholder_map = {"DISCORD_TOKEN": "Paste your Bot Token here", "SPOTIFY_CLIENT_ID": "Paste your Client ID here (optional)", "GENIUS_TOKEN": "Paste your Genius Token here (optional)"}
            self.entry = ctk.CTkEntry(input_frame, placeholder_text=placeholder_map.get(step["input"]), height=40, border_color=STYLE["border"], fg_color=STYLE["background_light"], corner_radius=8)
            self.entry.pack(fill="x"); self.widgets.append(self.entry)
            if step["input"] == "SPOTIFY_CLIENT_ID":
                self.entry_secret = ctk.CTkEntry(input_frame, placeholder_text="Paste your Client Secret here (optional)", height=40, border_color=STYLE["border"], fg_color=STYLE["background_light"], corner_radius=8)
                self.entry_secret.pack(fill="x", pady=(10, 0)); self.widgets.append(self.entry_secret)
        
        if self.current_step == len(self.steps_info) - 1:
            if not has_video: left_frame.grid_forget() # Hide the empty left frame
            opts_frame = ctk.CTkFrame(right_frame, fg_color="transparent"); opts_frame.pack(fill="x", pady=10, anchor="w")
            self.startup_checkbox = ctk.CTkCheckBox(opts_frame, text="Launch Playify when my computer starts", text_color=STYLE["text_secondary"], checkmark_color=STYLE["text"], fg_color=STYLE["accent"], hover_color=STYLE["accent_hover"]); self.startup_checkbox.pack(pady=(5,10), anchor="w"); self.startup_checkbox.select(); self.widgets.append(self.startup_checkbox)
            self.update_checkbox = ctk.CTkCheckBox(opts_frame, text="Automatically check for updates", text_color=STYLE["text_secondary"], checkmark_color=STYLE["text"], fg_color=STYLE["accent"], hover_color=STYLE["accent_hover"]); self.update_checkbox.pack(pady=(10,5), anchor="w"); self.update_checkbox.select(); self.widgets.append(self.update_checkbox)

        self.prev_button.configure(state="normal" if self.current_step > 0 else "disabled")
        self.next_button.configure(text="Finish" if self.current_step == len(self.steps_info) - 1 else "Next >")
    
    def handle_streaming_services_step(self, parent_frame):
        self.next_button.configure(state="disabled")
        choice_frame = ctk.CTkFrame(parent_frame, fg_color="transparent")
        choice_frame.pack(pady=10); self.widgets.append(choice_frame)
        yes_button = ctk.CTkButton(choice_frame, text="Yes, Install", command=lambda: self.install_playwright(parent_frame, choice_frame), fg_color=STYLE["accent"], hover_color=STYLE["accent_hover"]); yes_button.pack(side="left", padx=10)
        no_button = ctk.CTkButton(choice_frame, text="No, Skip", command=self.skip_playwright_install, fg_color="transparent", border_color=STYLE["border"], border_width=1); no_button.pack(side="left", padx=10)
    
    def install_playwright(self, parent_frame, choice_frame):
        choice_frame.pack_forget()
        console_frame = ctk.CTkFrame(parent_frame, fg_color=STYLE["theme_bg"], corner_radius=8)
        console_frame.pack(fill="both", expand=True, pady=10); self.widgets.append(console_frame)
        self.console_output = ctk.CTkTextbox(console_frame, wrap="word", font=("Courier New", 12), fg_color=STYLE["theme_bg"], text_color="#FFFFFF", activate_scrollbars=True)
        self.console_output.pack(fill="both", expand=True, padx=10, pady=10)
        self.console_output.insert("end", "Preparing installation...\n"); self.console_output.configure(state="disabled")
        self.continue_button = ctk.CTkButton(parent_frame, text="Installing...", state="disabled", command=self.next_step)
        self.continue_button.pack(pady=10); self.widgets.append(self.continue_button)
        threading.Thread(target=self._run_playwright_install, daemon=True).start()
    
    def _run_playwright_install(self):
        try:
            env = os.environ.copy(); env["PLAYWRIGHT_BROWSERS_PATH"] = self.controller.playwright_browser_path; process = subprocess.Popen("playwright install", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, shell=True, creationflags=subprocess.CREATE_NO_WINDOW, env=env, encoding='utf-8', errors='replace')
            for line in iter(process.stdout.readline, ''): self.after(0, self.update_console, line)
            process.wait()
            if process.returncode == 0: self.after(0, self.update_console, "\nInstallation complete! You can now continue.\n"); self.after(0, lambda: self.continue_button.pack_forget()); self.after(0, lambda: self.next_button.configure(state="normal"))
            else: self.after(0, self.update_console, f"\nInstallation failed with exit code {process.returncode}.\n"); self.after(0, lambda: self.continue_button.configure(text="Continue Anyway", fg_color=STYLE["danger"], state="normal")); self.after(0, lambda: self.next_button.configure(state="normal"))
        except Exception as e: self.after(0, self.update_console, f"\nAn unexpected error occurred: {e}\n"); self.after(0, lambda: self.continue_button.configure(text="Continue Anyway", fg_color=STYLE["danger"], state="normal")); self.after(0, lambda: self.next_button.configure(state="normal"))

    def update_console(self, text): self.console_output.configure(state="normal"); self.console_output.insert("end", text); self.console_output.see("end"); self.console_output.configure(state="disabled")
    def skip_playwright_install(self): self.current_step += 1; self.update_step_display()
    
    def next_step(self):
        step = self.steps_info[self.current_step]
        if "input" in step:
            is_valid = True; is_optional = step.get("optional", False)
            val = self.entry.get().strip()
            if step["input"] == "SPOTIFY_CLIENT_ID":
                sec = self.entry_secret.get().strip()
                if is_optional and not val and not sec: self.config_data['SPOTIFY_CLIENT_ID'] = ''; self.config_data['SPOTIFY_CLIENT_SECRET'] = ''
                elif (val and not sec) or (not val and sec): self.entry.configure(border_color=STYLE["danger"] if not val else STYLE["border"]); self.entry_secret.configure(border_color=STYLE["danger"] if not sec else STYLE["border"]); is_valid = False
                else: self.entry.configure(border_color=STYLE["border"]); self.entry_secret.configure(border_color=STYLE["border"]); self.config_data['SPOTIFY_CLIENT_ID'] = val; self.config_data['SPOTIFY_CLIENT_SECRET'] = sec
            else:
                if is_optional and not val: self.config_data[step["input"]] = ""
                elif not val or ("regex" in step and not re.match(step["regex"], val)): self.entry.configure(border_color=STYLE["danger"]); is_valid = False
                else: self.entry.configure(border_color=STYLE["border"]); self.config_data[step["input"]] = val
            if not is_valid: return
        if self.current_step < len(self.steps_info) - 1: self.current_step += 1; self.update_step_display()
        else: self.finish_setup()
    
    def prev_step(self):
        if self.current_step > 0: self.current_step -= 1; self.update_step_display()
    
    def finish_setup(self):
        final_config = {'DISCORD_TOKEN': self.config_data.get('DISCORD_TOKEN', ''), 'SPOTIFY_CLIENT_ID': self.config_data.get('SPOTIFY_CLIENT_ID', ''), 'SPOTIFY_CLIENT_SECRET': self.config_data.get('SPOTIFY_CLIENT_SECRET', ''), 'GENIUS_TOKEN': self.config_data.get('GENIUS_TOKEN', ''), 'CHECK_FOR_UPDATES': str(self.update_checkbox.get() == 1)}; save_config(final_config)
        if self.startup_checkbox.get(): self.controller.add_to_startup()
        else: self.controller.remove_from_startup()
        self.controller.is_configured = True; self.controller.config = final_config; self.controller.show_dashboard(); self.controller.start_bot_process()

# =========================================================================================
# === END OF REDESIGNED TUTORIAL ==========================================================
# =========================================================================================


class VideoPlayerOpenCV(ctk.CTkFrame):
    def __init__(self, parent, video_path):
        super().__init__(parent, fg_color="black"); self.cap = cv2.VideoCapture(video_path); self.is_playing = False; self.delay = 1/(self.cap.get(cv2.CAP_PROP_FPS) or 30); self.video_label = ctk.CTkLabel(self, text=""); self.video_label.pack(expand=True, fill="both")
    def play(self):
        if not self.is_playing: self.is_playing = True; threading.Thread(target=self._play_video, daemon=True).start()
    def destroy(self): self.is_playing = False; self.cap.release(); super().destroy()
    def _play_video(self):
        while self.is_playing:
            start_time = time.time()
            if not self.cap.isOpened(): break
            ret, frame = self.cap.read()
            if not ret: self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0); continue
            container_w, container_h = self.winfo_width(), self.winfo_height()
            if container_w < 2 or container_h < 2: time.sleep(0.01); continue
            frame_h, frame_w = frame.shape[:2]; scale = min(container_w / frame_w, container_h / frame_h)
            new_w, new_h = int(frame_w * scale), int(frame_h * scale)
            if new_w > 0 and new_h > 0:
                resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA); photo = ImageTk.PhotoImage(image=Image.fromarray(cv2.cvtColor(resized, cv2.COLOR_BGR2RGB))); self.after(0, self._update_frame, photo)
            sleep_time = self.delay - (time.time() - start_time);
            if sleep_time > 0: time.sleep(sleep_time)
    def _update_frame(self, photo):
        if self.winfo_exists(): self.video_label.configure(image=photo); self.video_label.image = photo

class StylishDashboardPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color="transparent"); self.controller = controller; self.grid_rowconfigure(1, weight=1); self.grid_columnconfigure(0, weight=1)
        top_card = ctk.CTkFrame(self, fg_color=STYLE["background_medium"], corner_radius=12); top_card.grid(row=0, column=0, padx=20, pady=20, sticky="ew"); top_card.grid_columnconfigure(1, weight=1)
        logo_path = resource_path("assets/images/playify_logo.png")
        if os.path.exists(logo_path): ctk.CTkLabel(top_card, image=ctk.CTkImage(Image.open(logo_path), size=(60, 60)), text="").grid(row=0, column=0, rowspan=2, padx=20, pady=10)
        ctk.CTkLabel(top_card, text="Bot Status", font=("Arial", 14), text_color="gray").grid(row=0, column=1, sticky="w", padx=10, pady=(10, 0))
        self.status_label = ctk.CTkLabel(top_card, text="CONNECTING...", text_color="#FFA726", font=(TITLE_FONT_FAMILY, 24, "bold")); self.status_label.grid(row=1, column=1, sticky="w", padx=10, pady=(0, 10))
        btn_frame = ctk.CTkFrame(top_card, fg_color="transparent"); btn_frame.grid(row=0, column=2, rowspan=2, padx=20)
        
        ctk.CTkButton(btn_frame, text="Restart Bot", command=self.restart_bot, width=120, fg_color=STYLE["accent"], hover_color=STYLE["accent_hover"]).pack(side="right", padx=(10,0))
        ctk.CTkButton(btn_frame, text="Settings", command=self.open_settings, width=120, fg_color="transparent", border_color=STYLE["border"], border_width=1, hover_color=STYLE["background_light"]).pack(side="right")
        
        console_card = ctk.CTkFrame(self, fg_color=STYLE["background_medium"], corner_radius=12); console_card.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew"); console_card.grid_rowconfigure(1, weight=1); console_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(console_card, text="Live Console", font=("Arial", 14), text_color="gray").grid(row=0, column=0, sticky="w", padx=20, pady=(10, 5))
        self.console_textbox = ctk.CTkTextbox(console_card, font=("Consolas", 12), border_width=0, fg_color=STYLE["theme_bg"], text_color=STYLE["text"], state="disabled", activate_scrollbars=True); self.console_textbox.grid(row=1, column=0, padx=20, pady=(5, 20), sticky="nsew")
    
    def open_settings(self):
        if self.controller.settings_window is None or not self.controller.settings_window.winfo_exists(): self.controller.settings_window = SettingsWindow(self.controller); self.controller.settings_window.grab_set()
        else: self.controller.settings_window.focus()
    
    def add_log_message(self, message): self.console_textbox.configure(state="normal"); self.console_textbox.insert("end", message); self.console_textbox.see("end"); self.console_textbox.configure(state="disabled")
    
    def update_status(self, status): 
        status_text = status.upper()
        color = {"ONLINE": STYLE["success"], "OFFLINE": STYLE["danger"], "ERROR": STYLE["danger"], "RESTARTING": "#FFC107", "CONNECTING": "#FFA726"}.get(status_text, "#FFA726")
        self.status_label.configure(text=status_text, text_color=color)

    def restart_bot(self):
        """When clicking the "Restart Bot" button."""
        self.add_log_message("--- Sending restart command to bot... ---\n")
        self.update_status("SHUTTING DOWN")
        
        # Launch the restart in a separate thread to prevent the interface from freezing.
        threading.Thread(target=self._restart_sequence, daemon=True).start()

    def _restart_sequence(self):
        """This function contains the new restart logic."""
        # Verify that the bot is currently running
        if self.controller.bot_process and self.controller.bot_process.is_alive():
            
            # 1. Send the "RESTART" command to the intercom (the queue)
            print("Sending 'RESTART' command...")
            self.controller.command_queue.put('RESTART')
            
            # 2. Politely wait for the bot to finish shutting down (up to 10s)
            self.controller.bot_process.join(timeout=10)

            # 3. If after 10s it still hasn't responded, use the emergency switch
            if self.controller.bot_process.is_alive():
                print("Bot did not shut down gracefully. Forcing termination.")
                self.controller.bot_process.terminate()
                self.controller.bot_process.join()

        # 4. Once the old bot is properly stopped, request the application to restart it
        # "self.controller.after" ensures this is done by the main thread of the interface
        print("Restarting bot process...")
        self.controller.after(0, self.controller.start_bot_process)

# =========================================================================================
# === FULLY CORRECTED AND FUNCTIONAL SETTINGS WINDOW ======================================
# =========================================================================================
class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, controller):
        super().__init__(controller)
        self.controller = controller
        self.title("Playify Settings")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        try:
            self.iconbitmap(resource_path("assets/images/playify.ico"))
        except Exception as e:
            print(f"Settings window icon error: {e}")
        self.geometry("600x650") 
        self.resizable(False, False)
        self.configure(fg_color=STYLE["background_medium"]) 
        self.transient(controller)
        
        self.link_font = ctk.CTkFont(family="Arial", size=12, underline=True)
        self.desc_font = ctk.CTkFont(family="Arial", size=14)
        
        self.config = load_config()

        # Tab view setup
        self.tab_view = ctk.CTkTabview(self,
                                       anchor="w",
                                       fg_color="transparent",
                                       segmented_button_fg_color=STYLE["background_medium"],
                                       segmented_button_selected_color=STYLE["accent"],
                                       segmented_button_selected_hover_color=STYLE["accent_hover"],
                                       segmented_button_unselected_color=STYLE["background_medium"],
                                       segmented_button_unselected_hover_color=STYLE["background_light"])
        self.tab_view.grid(row=0, column=0, padx=20, pady=10, sticky="nsew")
        
        # Add tabs
        self.tab_view.add("General")
        self.tab_view.add("Presence")
        self.tab_view.add("Credentials")
        self.tab_view.add("About")

        # Create the content for each tab
        self._create_general_tab()
        self._create_presence_tab()
        self._create_credentials_tab()
        self._create_about_tab()
        
        # Bottom button container using .grid()
        button_container = ctk.CTkFrame(self, fg_color="transparent")
        button_container.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="ew")
        button_container.grid_columnconfigure(0, weight=1) # Allow status label to take space

        self.save_status_label = ctk.CTkLabel(button_container, text="")
        self.save_status_label.grid(row=0, column=0, sticky="w", padx=5)
        
        ctk.CTkButton(button_container, text="Save and Restart Bot", command=self.save_all_settings, fg_color=STYLE["accent"], hover_color=STYLE["accent_hover"]).grid(row=0, column=1, sticky="e")
        
        self.tab_view.set("General")

    def _create_general_tab(self):
        """Creates the General settings tab using .grid() exclusively."""
        tab = self.tab_view.tab("General")
        tab.configure(fg_color="transparent")
        tab.grid_columnconfigure(0, weight=1)

        # Startup Card
        startup_frame = ctk.CTkFrame(tab, fg_color=STYLE["background_light"], corner_radius=8)
        startup_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        self.startup_var = ctk.BooleanVar(value=self.controller.is_in_startup())
        startup_checkbox = ctk.CTkCheckBox(startup_frame, text="Launch Playify on startup", variable=self.startup_var, command=self.toggle_startup, text_color=STYLE["text_secondary"], checkmark_color=STYLE["text"], fg_color=STYLE["accent"], hover_color=STYLE["accent_hover"])
        startup_checkbox.grid(row=0, column=0, padx=15, pady=15, sticky="w")
        
        # Update Card
        update_frame = ctk.CTkFrame(tab, fg_color=STYLE["background_light"], corner_radius=8)
        update_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
        self.update_var = ctk.BooleanVar(value=self.config.get("CHECK_FOR_UPDATES", "True").lower() == 'true')
        update_checkbox = ctk.CTkCheckBox(update_frame, text="Auto-check for updates", variable=self.update_var, command=self.toggle_update_check, text_color=STYLE["text_secondary"], checkmark_color=STYLE["text"], fg_color=STYLE["accent"], hover_color=STYLE["accent_hover"])
        update_checkbox.grid(row=0, column=0, padx=15, pady=15, sticky="w")

    def _create_presence_tab(self):
        """Creates the redesigned UI for presence customization using .grid() exclusively."""
        tab = self.tab_view.tab("Presence")
        tab.configure(fg_color="transparent")
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        scrollable_frame = ctk.CTkScrollableFrame(tab, fg_color="transparent", label_text=None)
        scrollable_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        scrollable_frame.grid_columnconfigure(0, weight=1)

        config_card = ctk.CTkFrame(scrollable_frame, fg_color=STYLE["background_light"], corner_radius=8)
        config_card.grid(row=0, column=0, sticky="ew", padx=10, pady=(0, 10))
        # THE FIX - PART 1: Do NOT configure column weights here. This prevents the grid from
        # distributing extra space, which was the root cause of the stretching.

        # --- Activity Type Widgets ---
        ctk.CTkLabel(config_card, text="Activity Type", font=("Arial", 14, "bold"), text_color=STYLE["text"]).grid(row=0, column=0, sticky="w", padx=15, pady=(10, 5))
        self.presence_type_var = ctk.StringVar(value=self.config.get("PRESENCE_TYPE", "Playing"))
        
        self.presence_type_menu = ctk.CTkOptionMenu(config_card,
                                                    variable=self.presence_type_var,
                                                    values=["Playing", "Listening", "Watching", "Competing"],
                                                    fg_color=STYLE["background_medium"], 
                                                    button_color=STYLE["accent"], 
                                                    button_hover_color=STYLE["accent_hover"], 
                                                    text_color=STYLE["text"])
        self.presence_type_menu.grid(row=1, column=0, sticky="w", padx=15, pady=(0, 15))

        # --- Number of Statuses Widgets ---
        ctk.CTkLabel(config_card, text="Number of Statuses", font=("Arial", 14, "bold"), text_color=STYLE["text"]).grid(row=0, column=1, sticky="w", padx=15, pady=(10, 5))
        self.rotation_count_var = ctk.StringVar(value=self.config.get("PRESENCE_ROTATION_COUNT", "3"))

        button_group_frame = ctk.CTkFrame(config_card, fg_color=STYLE["background_medium"], corner_radius=8)
        button_group_frame.grid(row=1, column=1, sticky="w", padx=15, pady=(0, 15))

        self.status_buttons = {}
        for i, count in enumerate(["1", "2", "3"]):
            btn = ctk.CTkButton(button_group_frame,
                                text=count,
                                command=lambda c=count: self.select_status_count(c),
                                border_width=0,
                                corner_radius=6,
                                fg_color=STYLE["background_medium"],
                                hover_color=STYLE["background_light"],
                                # THE FIX - PART 2: Explicitly set a small, fixed width for the buttons.
                                width=40)
            btn.grid(row=0, column=i, sticky="", padx=2, pady=2)
            self.status_buttons[count] = btn
        
        self._update_status_button_styles(self.rotation_count_var.get())

        # The rest of the tab content remains unchanged
        delay_card = ctk.CTkFrame(scrollable_frame, fg_color=STYLE["background_light"], corner_radius=8)
        delay_card.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
        delay_card.grid_columnconfigure(0, weight=1)
        
        delay_label_frame = ctk.CTkFrame(delay_card, fg_color="transparent")
        delay_label_frame.grid(row=0, column=0, padx=15, pady=(10, 0), sticky="ew")
        ctk.CTkLabel(delay_label_frame, text="Rotation Speed", font=("Arial", 14, "bold"), text_color=STYLE["text"]).pack(side="left")
        self.delay_label = ctk.CTkLabel(delay_label_frame, text=f"{self.config.get('PRESENCE_ROTATION_DELAY', '15')} seconds", text_color=STYLE["text_secondary"])
        self.delay_label.pack(side="right")
        
        ctk.CTkLabel(delay_card, text="Delay in seconds between each status change.", font=("Arial", 11), text_color=STYLE["text_secondary"]).grid(row=1, column=0, sticky="w", padx=15)

        initial_delay = int(self.config.get("PRESENCE_ROTATION_DELAY", 15))
        self.delay_slider = ctk.CTkSlider(delay_card, from_=5, to=60, number_of_steps=55, command=self.update_delay_label, button_color=STYLE["accent"], button_hover_color=STYLE["accent_hover"], progress_color=STYLE["accent"])
        self.delay_slider.set(initial_delay)
        self.delay_slider.grid(row=2, column=0, padx=15, pady=(5, 15), sticky="ew")

        ctk.CTkLabel(scrollable_frame, text="Status Messages", font=("Arial", 16, "bold"), text_color=STYLE["text"]).grid(row=2, column=0, sticky="w", padx=15, pady=(15, 5))
        
        self.entries_frame = ctk.CTkFrame(scrollable_frame, fg_color="transparent")
        self.entries_frame.grid(row=3, column=0, sticky="ew")
        self.entries_frame.grid_columnconfigure(0, weight=1)
        
        self.presence_entry_1, self.presence_frame_1 = self._populate_presence_entry(self.entries_frame, "Status 1", self.config.get("PRESENCE_1", "/play [link]"))
        self.presence_entry_2, self.presence_frame_2 = self._populate_presence_entry(self.entries_frame, "Status 2", self.config.get("PRESENCE_2", "/help"))
        self.presence_entry_3, self.presence_frame_3 = self._populate_presence_entry(self.entries_frame, "Status 3", self.config.get("PRESENCE_3", "alan7383.github.io/playify"))
        
        self.toggle_presence_entries()

    def _populate_presence_entry(self, parent, label_text, value):
        """Creates and populates a styled card for a status entry field."""
        frame = ctk.CTkFrame(parent, fg_color=STYLE["background_light"], corner_radius=8)
        frame.grid_columnconfigure(0, weight=1)

        label = ctk.CTkLabel(frame, text=label_text, font=("Arial", 12), text_color=STYLE["text_secondary"])
        label.grid(row=0, column=0, sticky="w", padx=15, pady=(8, 2))
        
        entry = ctk.CTkEntry(frame, height=35, placeholder_text="Enter your status message here...", border_color=STYLE["border"], fg_color=STYLE["background_medium"])
        entry.insert(0, value)
        entry.grid(row=1, column=0, sticky="ew", padx=15, pady=(0, 10))
        
        return entry, frame
        
    def update_delay_label(self, value):
        self.delay_label.configure(text=f"{int(value)} seconds")
        
    def toggle_presence_entries(self, value=None):
        """Shows or hides status entry fields using grid layout."""
        count = int(self.rotation_count_var.get())
        
        if count >= 1: self.presence_frame_1.grid(row=0, column=0, sticky="ew", padx=10, pady=8)
        else: self.presence_frame_1.grid_remove()

        if count >= 2: self.presence_frame_2.grid(row=1, column=0, sticky="ew", padx=10, pady=8)
        else: self.presence_frame_2.grid_remove()
        
        if count >= 3: self.presence_frame_3.grid(row=2, column=0, sticky="ew", padx=10, pady=8)
        else: self.presence_frame_3.grid_remove()

    def select_status_count(self, count):
        """Handles click on a status number button and updates styles."""
        self.rotation_count_var.set(count)
        self._update_status_button_styles(count)
        self.toggle_presence_entries() # Update the visibility of presence entry fields

    def _update_status_button_styles(self, selected_count):
        """Iterates through the buttons and applies the correct selected/unselected style."""
        for count, button in self.status_buttons.items():
            if count == selected_count:
                # Style for the selected button
                button.configure(fg_color=STYLE["accent"], hover_color=STYLE["accent_hover"])
            else:
                # Style for unselected buttons
                button.configure(fg_color=STYLE["background_medium"], hover_color=STYLE["background_light"])

    def _create_credentials_tab(self):
        """Creates the Credentials tab using .grid() exclusively."""
        tab = self.tab_view.tab("Credentials")
        tab.configure(fg_color="transparent")
        tab.grid_columnconfigure(0, weight=1)

        # Create entry for Discord Token
        frame1 = ctk.CTkFrame(tab, fg_color=STYLE["background_light"], corner_radius=8)
        frame1.grid(row=0, column=0, sticky="ew", padx=10, pady=8)
        self.discord_token_entry = self._populate_credential_frame(frame1, "Discord Token", self.config.get("DISCORD_TOKEN", ""))

        # Create entry for Spotify Client ID
        frame2 = ctk.CTkFrame(tab, fg_color=STYLE["background_light"], corner_radius=8)
        frame2.grid(row=1, column=0, sticky="ew", padx=10, pady=8)
        self.spotify_id_entry = self._populate_credential_frame(frame2, "Spotify Client ID", self.config.get("SPOTIFY_CLIENT_ID", ""))

        # Create entry for Spotify Client Secret
        frame3 = ctk.CTkFrame(tab, fg_color=STYLE["background_light"], corner_radius=8)
        frame3.grid(row=2, column=0, sticky="ew", padx=10, pady=8)
        self.spotify_secret_entry = self._populate_credential_frame(frame3, "Spotify Client Secret", self.config.get("SPOTIFY_CLIENT_SECRET", ""))

        # Create entry for Genius Token
        frame4 = ctk.CTkFrame(tab, fg_color=STYLE["background_light"], corner_radius=8)
        frame4.grid(row=3, column=0, sticky="ew", padx=10, pady=8)
        self.genius_token_entry = self._populate_credential_frame(frame4, "Genius Token", self.config.get("GENIUS_TOKEN", ""))
    
    def _populate_credential_frame(self, parent_frame, label_text, value, show_button=True):
        """Populates a given frame with credential widgets using .grid()."""
        parent_frame.grid_columnconfigure(0, weight=1)

        label = ctk.CTkLabel(parent_frame, text=label_text, font=("Arial", 12), text_color=STYLE["text"])
        label.grid(row=0, column=0, columnspan=2, sticky="w", padx=15, pady=(10, 2))
        
        show_char = "*" if show_button else ""
        entry = ctk.CTkEntry(parent_frame, height=35, show=show_char, border_color=STYLE["border"], fg_color=STYLE["background_medium"])
        entry.insert(0, value)
        entry.grid(row=1, column=0, sticky="ew", padx=(15, 5), pady=(0, 10))
        
        if show_button:
            button = ctk.CTkButton(parent_frame, text="Show", width=60, command=lambda e=entry: e.configure(show="" if e.cget("show") == "*" else "*"), fg_color="transparent", border_color=STYLE["border"], border_width=1)
            button.grid(row=1, column=1, sticky="w", padx=(0, 15), pady=(0, 10))
        
        return entry
    
    def _create_about_tab(self):
        """Creates the About tab using .grid() exclusively."""
        tab = self.tab_view.tab("About")
        tab.configure(fg_color="transparent")
        tab.grid_columnconfigure(0, weight=1)
        
        container = ctk.CTkFrame(tab, fg_color="transparent")
        container.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        container.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(container, text=f"{APP_NAME} v{CURRENT_VERSION}", font=(TITLE_FONT_FAMILY, 32, "bold"), text_color=STYLE["text"]).grid(row=0, column=0, pady=10)
        ctk.CTkLabel(container, text="Made by @alananasssss", font=self.desc_font, text_color=STYLE["text_secondary"]).grid(row=1, column=0, pady=(0, 10))
        ctk.CTkButton(container, text="Check for Updates", command=lambda: self.controller.check_for_updates(manual_check=True), fg_color=STYLE["accent"], hover_color=STYLE["accent_hover"]).grid(row=2, column=0, pady=(0,20))
        
        support_frame = ctk.CTkFrame(container, fg_color=STYLE["background_light"], corner_radius=8)
        support_frame.grid(row=3, column=0, sticky="ew", pady=10, padx=10)
        support_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(support_frame, text="(ง＾◡＾)ง Contributing & Support", font=("Arial", 16, "bold"), text_color=STYLE["text"]).grid(row=0, column=0, pady=(15,10), padx=20)
        
        self._create_link(support_frame, 1, "Star on GitHub", "https://github.com/alan7383/playify/")
        self._create_link(support_frame, 2, "Join our Discord Server", "https://discord.gg/JeH8g6g3cG")
        self._create_link(support_frame, 3, "Support on Patreon", "https://www.patreon.com/Playify")
        self._create_link(support_frame, 4, "Donate via PayPal", "https://paypal.com/paypalme/alanmussot1")

        ctk.CTkLabel(support_frame, text="Fork the repo, open an issue or pull request—all contributions are welcome!", wraplength=450, text_color=STYLE["text_secondary"], justify="center").grid(row=5, column=0, pady=(10, 20), padx=20)
    
    def _create_link(self, parent, row_index, text, url):
        link = ctk.CTkLabel(parent, text=text, font=self.link_font, text_color="#3498db", cursor="hand2")
        link.grid(row=row_index, column=0, sticky="w", padx=20, pady=5)
        link.bind("<Button-1>", lambda e, u=url: webbrowser.open_new_tab(u))
    
    def toggle_startup(self):
        if self.startup_var.get(): self.controller.add_to_startup()
        else: self.controller.remove_from_startup()
    
    def toggle_update_check(self):
        self.config["CHECK_FOR_UPDATES"] = str(self.update_var.get())
        save_config(self.config)
    
    def save_all_settings(self):
        """Saves ALL settings from all tabs and restarts the bot."""
        # Credentials
        self.config["DISCORD_TOKEN"] = self.discord_token_entry.get()
        self.config["SPOTIFY_CLIENT_ID"] = self.spotify_id_entry.get()
        self.config["SPOTIFY_CLIENT_SECRET"] = self.spotify_secret_entry.get()
        self.config["GENIUS_TOKEN"] = self.genius_token_entry.get()
        
        # Presence
        self.config["PRESENCE_TYPE"] = self.presence_type_var.get()
        self.config["PRESENCE_ROTATION_COUNT"] = self.rotation_count_var.get()
        self.config["PRESENCE_ROTATION_DELAY"] = str(int(self.delay_slider.get()))
        self.config["PRESENCE_1"] = self.presence_entry_1.get()
        self.config["PRESENCE_2"] = self.presence_entry_2.get()
        self.config["PRESENCE_3"] = self.presence_entry_3.get()

        if save_config(self.config): 
            self.save_status_label.configure(text="Saved! Restarting...", text_color=STYLE["success"])
            self.controller.config = self.config
            self.controller.start_bot_process()
        else: 
            self.save_status_label.configure(text="Error saving!", text_color=STYLE["danger"])
        
        self.after(3000, lambda: self.save_status_label.configure(text=""))

# --- SINGLE INSTANCE AND COMMUNICATION SETUP ---

SINGLETON_HOST = "127.0.0.1"  
SINGLETON_PORT = 60101      
SHOW_WINDOW_MSG = b"show_playify_window" 

def start_signal_server(app_instance, server_socket):
    """
    This function runs in the background (thread) and waits for a signal
    to display the application window.
    """
    try:
        server_socket.listen()
        while True:
            conn, addr = server_socket.accept()
            with conn:
                data = conn.recv(1024)
                if data == SHOW_WINDOW_MSG:
                    print("Signal received from another instance: displaying window.")
                app_instance.after(0, app_instance.show_from_tray)
    except (IOError, OSError):
        pass
    finally:
        server_socket.close()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    try:
        server_socket.bind((SINGLETON_HOST, SINGLETON_PORT))
        print("First instance of Playify started. Setting up the signaling server.")
        
    except OSError:
        print("Playify is already running. Sending signal to show window.")
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
                client_socket.connect((SINGLETON_HOST, SINGLETON_PORT))
                client_socket.sendall(SHOW_WINDOW_MSG)
        except Exception as e:
            print(f"Unable to contact existing instance: {e}")
        
        sys.exit(0)

    ctk.set_appearance_mode("dark") 
    app = App()

    listener_thread = threading.Thread(
        target=start_signal_server, 
        args=(app, server_socket), 
        daemon=True
    )
    listener_thread.start()

    app.mainloop()

    print("Closing application and signaling socket.")
    server_socket.close()
