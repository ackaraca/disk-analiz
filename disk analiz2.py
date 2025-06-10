import os
import sys
import shutil
import threading
import subprocess
import string
import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

class DiskAnalyzerApp:
    """
    Disk kullanımını analiz etmek, görselleştirmek ve yönetmek için
    gelişmiş, çoklu tarama ve ilerleme çubuğu özelliklerine sahip GUI uygulaması.
    (Hız optimizasyonu: Multithreading ve Sonuçları Kaydetme/Yükleme)
    """
    SAVE_FILE_NAME = "son_tarama_sonuclari.json"

    def __init__(self, root_window):
        self.root = root_window
        self.root.title("Gelişmiş Python Disk Analiz Programı (Çoklu Çekirdek Destekli)")
        self.root.geometry("1024x768")

        # === Stil Ayarları ===
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure("TButton", padding=6, relief="flat", background="#e1e1e1")
        self.style.configure("Treeview", rowheight=25)
        self.style.configure("TLabelFrame.Label", font=('Helvetica', 11, 'bold'))

        # === Ana Arayüz Yapısı (Bölünmüş Panel) ===
        main_paned_window = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned_window.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)

        # --- Sol Kontrol Paneli ---
        left_frame = ttk.Frame(main_paned_window, width=280)
        main_paned_window.add(left_frame, weight=1)

        # --- Sağ Sonuç Paneli ---
        right_frame = ttk.Frame(main_paned_window)
        main_paned_window.add(right_frame, weight=3)
        
        # === Sol Panel Elemanları ===
        self.setup_left_panel(left_frame)

        # === Sağ Panel Elemanları (Ağaç Görünümü) ===
        self.setup_right_panel(right_frame)

        # === Alt Durum Çubuğu ===
        bottom_frame = ttk.Frame(self.root, padding=(10, 5, 10, 10))
        bottom_frame.pack(fill=tk.X)
        self.status_label = ttk.Label(bottom_frame, text="Hazır. Taramak için sürücü veya klasör seçin.")
        self.status_label.pack(side=tk.LEFT)
        self.progress_bar = ttk.Progressbar(bottom_frame, orient='horizontal', mode='determinate')
        self.progress_bar.pack(side=tk.RIGHT, expand=True, fill=tk.X, padx=(10, 0))

        # Program başlangıcında son tarama sonuçlarını yüklemeyi dene
        self.root.after(100, self._load_last_results)


    def setup_left_panel(self, parent_frame):
        """Sol taraftaki kontrol panelini oluşturur."""
        # Sürücü Seçim Alanı
        drives_frame = ttk.LabelFrame(parent_frame, text="Sürücüler")
        drives_frame.pack(fill=tk.X, padx=5, pady=5)
        self.drive_vars = {}
        for drive in self.get_available_drives():
            var = tk.BooleanVar()
            cb = ttk.Checkbutton(drives_frame, text=f"{drive}", variable=var)
            cb.pack(anchor='w', padx=10, pady=2)
            self.drive_vars[drive] = var

        # Özel Klasör Seçim Alanı
        custom_folder_frame = ttk.LabelFrame(parent_frame, text="Özel Klasörler")
        custom_folder_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=10)
        
        self.folder_listbox = tk.Listbox(custom_folder_frame, height=4)
        self.folder_listbox.pack(expand=True, fill=tk.BOTH, pady=5, padx=5)
        
        folder_button_frame = ttk.Frame(custom_folder_frame)
        folder_button_frame.pack(fill=tk.X, pady=5)
        add_folder_button = ttk.Button(folder_button_frame, text="Klasör Ekle", command=self.add_custom_folder)
        add_folder_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        remove_folder_button = ttk.Button(folder_button_frame, text="Seçileni Kaldır", command=self.remove_custom_folder)
        remove_folder_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        # Tarama Butonu
        self.scan_button = ttk.Button(parent_frame, text="Seçilenleri Tara", command=self.start_scan)
        self.scan_button.pack(fill=tk.X, padx=5, pady=10, ipady=5)

    def setup_right_panel(self, parent_frame):
        """Sağ taraftaki sonuç ağacını oluşturur."""
        self.tree = ttk.Treeview(parent_frame, columns=("size", "full_path"), displaycolumns=("size"))
        self.tree.heading("#0", text="İsim")
        self.tree.heading("size", text="Boyut")
        self.tree.column("size", width=150, anchor='e')
        self.tree.column("#0", minwidth=300)

        vsb = ttk.Scrollbar(parent_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(parent_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(expand=True, fill=tk.BOTH)

        # Sağ Tık Menüsü
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Gezginde Aç", command=self.open_in_explorer)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Seçileni Sil", command=self.delete_selected, foreground='red')
        self.tree.bind("<Button-3>", self.show_context_menu)


    def get_scan_targets(self):
        """Kullanıcının seçtiği tüm sürücüleri ve klasörleri bir liste olarak döndürür."""
        targets = []
        for drive, var in self.drive_vars.items():
            if var.get():
                targets.append(os.path.join(drive, ""))
        for i in range(self.folder_listbox.size()):
            targets.append(self.folder_listbox.get(i))
        return targets

    def start_scan(self):
        """Tarama işlemini başlatır ve arayüzü ayarlar."""
        self.scan_targets = self.get_scan_targets()
        if not self.scan_targets:
            messagebox.showwarning("Uyarı", "Lütfen taramak için en az bir sürücü veya klasör seçin.")
            return

        self.set_ui_state(tk.DISABLED)
        self.tree.delete(*self.tree.get_children())
        self.status_label.config(text="Tarama yapılıyor, lütfen bekleyin...")
        
        self.progress_bar.config(mode='indeterminate')
        self.progress_bar.start(10)
        
        scan_thread = threading.Thread(target=self.scan_thread_manager, args=(self.scan_targets,), daemon=True)
        scan_thread.start()

    def _scan_single_target(self, target_path, shared_results, lock):
        """Bir thread tarafından çalıştırılacak olan tek bir hedefi tarayan worker fonksiyonu."""
        local_results = defaultdict(int)
        try:
            for path, dirs, files in os.walk(target_path, topdown=False):
                try:
                    file_size = sum(os.path.getsize(os.path.join(path, f)) for f in files if not os.path.islink(os.path.join(path, f)))
                    dir_size = sum(local_results[os.path.join(path, d)] for d in dirs)
                    total_size = file_size + dir_size
                    local_results[path] = total_size
                except (PermissionError, FileNotFoundError):
                    local_results[path] = 0
                    continue

            with lock:
                for path, size in local_results.items():
                    shared_results[path] += size

        except Exception as e:
            print(f"Hata ({target_path}): {e}")

    def scan_thread_manager(self, targets):
        """Her bir hedef için worker thread'leri oluşturur ve yönetir."""
        path_sizes = defaultdict(int)
        lock = threading.Lock()

        with ThreadPoolExecutor() as executor:
            futures = [executor.submit(self._scan_single_target, target, path_sizes, lock) for target in targets]
            for future in futures:
                future.result()

        self.root.after(0, self.populate_tree, path_sizes, targets)

    def populate_tree(self, path_sizes, root_paths, from_file=False):
        """Hesaplanan boyutlarla ağaç görünümünü doldurur."""
        self.status_label.config(text="Sonuçlar ağaca yerleştiriliyor...")
        self.tree.delete(*self.tree.get_children())
        
        tree_data = defaultdict(list)
        for path, size in path_sizes.items():
            parent = os.path.dirname(path)
            if parent == path: 
                parent = ""
            tree_data[parent].append({'path': path, 'size': size})

        for root in root_paths:
            name = root
            size = path_sizes.get(root, 0)
            item_id = self.tree.insert("", 'end', text=name, values=(self.format_size(size), root), open=True)
            self._insert_children(root, item_id, tree_data)
        
        if not from_file:
            self._save_results(path_sizes, root_paths)
            self.scan_finished("Tarama tamamlandı.")
        else:
            self.scan_finished("Son tarama sonuçları yüklendi.")


    def _insert_children(self, current_path, parent_id, tree_data):
        """Ağaç verisini özyineli olarak Treeview'a ekler."""
        children = sorted(tree_data.get(current_path, []), key=lambda x: x['size'], reverse=True)
        for child in children:
            path = child['path']
            size = child['size']
            name = os.path.basename(path)
            if not name: continue

            if size > 0:
                item_id = self.tree.insert(parent_id, 'end', text=name, values=(self.format_size(size), path))
                if path in tree_data:
                    self._insert_children(path, item_id, tree_data)
    
    # --- Sonuçları Kaydetme ve Yükleme Fonksiyonları ---

    def _save_results(self, sizes, targets):
        """Tarama sonuçlarını bir JSON dosyasına kaydeder."""
        try:
            data_to_save = {
                'targets': targets,
                'sizes': sizes
            }
            with open(self.SAVE_FILE_NAME, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=4)
        except Exception as e:
            print(f"Hata: Sonuçlar kaydedilemedi - {e}")

    def _load_last_results(self):
        """Program açıldığında son tarama sonuçlarını JSON dosyasından yükler."""
        if os.path.exists(self.SAVE_FILE_NAME):
            try:
                with open(self.SAVE_FILE_NAME, 'r', encoding='utf-8') as f:
                    saved_data = json.load(f)
                
                # defaultdict'a dönüştür, çünkü json'dan normal dict olarak döner
                path_sizes = defaultdict(int, saved_data.get('sizes', {}))
                root_paths = saved_data.get('targets', [])
                
                if path_sizes and root_paths:
                    self.populate_tree(path_sizes, root_paths, from_file=True)
            except Exception as e:
                self.status_label.config(text="Hata: Son tarama sonuçları yüklenemedi.")
                print(f"Yükleme hatası: {e}")
        else:
            self.status_label.config(text="Hazır. Taramak için sürücü veya klasör seçin.")


    # --- Yardımcı ve Event Fonksiyonları ---

    def add_custom_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.folder_listbox.insert(tk.END, path)

    def remove_custom_folder(self):
        selected_indices = self.folder_listbox.curselection()
        for i in reversed(selected_indices):
            self.folder_listbox.delete(i)
            
    def delete_selected(self):
        selected_ids = self.tree.selection()
        if not selected_ids:
            messagebox.showwarning("Uyarı", "Lütfen silmek için bir öğe seçin.")
            return
        
        path_to_delete = self.tree.item(selected_ids[0], 'values')[1]
        
        confirm = messagebox.askyesno(
            "Silme Onayı",
            f"'{path_to_delete}' kalıcı olarak silinecek.\n\nBu işlem geri alınamaz, emin misiniz?",
            icon='warning'
        )

        if confirm:
            try:
                self.status_label.config(text=f"Siliniyor: {path_to_delete}")
                self.root.update_idletasks()
                if os.path.isdir(path_to_delete):
                    shutil.rmtree(path_to_delete)
                else:
                    os.remove(path_to_delete)
                self.tree.delete(selected_ids[0])
                messagebox.showinfo("Başarılı", "Seçilen öğe başarıyla silindi.")
            except Exception as e:
                messagebox.showerror("Hata", f"Silme işlemi başarısız oldu:\n{e}")
            finally:
                self.status_label.config(text="Hazır.")

    def show_context_menu(self, event):
        item_id = self.tree.identify_row(event.y)
        if item_id:
            self.tree.selection_set(item_id)
            self.context_menu.post(event.x_root, event.y_root)

    def open_in_explorer(self):
        selected_id = self.tree.selection()[0]
        path = self.tree.item(selected_id, 'values')[1]
        try:
            if sys.platform == "win32":
                os.startfile(os.path.normpath(path))
            elif sys.platform == "darwin":
                subprocess.run(["open", path])
            else:
                subprocess.run(["xdg-open", path])
        except Exception as e:
            messagebox.showerror("Hata", f"Klasör açılamadı: {e}")

    def set_ui_state(self, state):
        """Tarama sırasında kontrol elemanlarını devre dışı bırakır/etkinleştirir."""
        self.scan_button.config(state=state)
        for child in self.root.winfo_children():
            if isinstance(child, ttk.PanedWindow):
                left_panel = child.winfo_children()[0]
                for widget in left_panel.winfo_children():
                    if hasattr(widget, 'state'):
                        widget.state([state] if state == tk.DISABLED else [f"!{tk.DISABLED}"])
                    for sub_widget in widget.winfo_children():
                         if hasattr(sub_widget, 'state'):
                             sub_widget.state([state] if state == tk.DISABLED else [f"!{tk.DISABLED}"])

    def scan_finished(self, message):
        """Tarama bittiğinde arayüzü tekrar aktif hale getirir."""
        self.status_label.config(text=message)
        self.progress_bar.stop()
        self.progress_bar.config(mode='determinate')
        self.progress_bar['value'] = 0
        self.set_ui_state(tk.NORMAL)

    @staticmethod
    def get_available_drives():
        if sys.platform == "win32":
            return [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:")]
        else:
            return ["/"]

    @staticmethod
    def format_size(size_bytes):
        if size_bytes == 0: return "0 B"
        size_name = ("B", "KB", "MB", "GB", "TB")
        i = 0
        while size_bytes >= 1024 and i < len(size_name) - 1:
            size_bytes /= 1024.0
            i += 1
        return f"{size_bytes:.2f} {size_name[i]}"

if __name__ == "__main__":
    root = tk.Tk()
    app = DiskAnalyzerApp(root)
    root.mainloop()
