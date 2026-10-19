"""Küçük kontrol penceresi (tkinter — Python ile birlikte gelir, ek paket gerekmez).

Tarayıcı sekmesi kapatılsa bile sunucu arka planda çalışmaya devam eder. Kullanıcının uygulamayı
nasıl kapatacağını bilmesi için bu pencere görünür kalır: "Kapat" ya da pencerenin X düğmesi
sunucuyu da kapatır. .exe konsolsuz (--windowed) derlendiği için siyah komut penceresi açılmaz.
"""
import os
import subprocess
import sys
import tkinter as tk
import webbrowser
from tkinter import ttk

from desktop.launcher import APP_TITLE, resource_path

BRAND = "#2f7d32"


def open_folder(path):
    """Klasörü dosya gezgininde açar (Windows Gezgini / Finder / Linux dosya yöneticisi)."""
    path = str(path)
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa: S606  (yalnızca kendi veri klasörümüz)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def run_control_window(url, base):
    root = tk.Tk()
    root.title(APP_TITLE)
    root.resizable(False, False)
    try:
        root.iconphoto(True, tk.PhotoImage(file=str(resource_path("desktop", "icon.png"))))
    except tk.TclError:
        pass  # ikon bulunamazsa varsayılan ikonla devam

    frame = ttk.Frame(root, padding=18)
    frame.grid()
    tk.Label(frame, text=APP_TITLE, font=("Segoe UI", 15, "bold"), fg=BRAND).grid(column=0, row=0, columnspan=3, sticky="w")
    ttk.Label(frame, text="Uygulama çalışıyor. Tarayıcı sekmesini kapatsanız da\n"
                          "bu pencere açık kaldıkça uygulama çalışmaya devam eder.").grid(
        column=0, row=1, columnspan=3, sticky="w", pady=(4, 10))

    address = ttk.Entry(frame, width=36)
    address.insert(0, url)
    address.configure(state="readonly")
    address.grid(column=0, row=2, columnspan=3, sticky="we", pady=(0, 12))

    ttk.Button(frame, text="Tarayıcıda aç", command=lambda: webbrowser.open(url)).grid(column=0, row=3, padx=(0, 6))
    ttk.Button(frame, text="Veri klasörü", command=lambda: open_folder(base)).grid(column=1, row=3, padx=6)
    ttk.Button(frame, text="Kapat", command=root.destroy).grid(column=2, row=3, padx=(6, 0))

    ttk.Label(frame, text=f"Veriler: {base}", foreground="#6c757d", font=("Segoe UI", 8)).grid(
        column=0, row=4, columnspan=3, sticky="w", pady=(12, 0))

    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
