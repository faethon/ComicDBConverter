import tkinter as tk
from cr_converter import CRConverter
from tkinter import filedialog, messagebox
from tkinter import ttk  # Voor de voortgangsbalk
import configparser
import os, logging


# Configureer het pad naar je configuratiebestand
CONFIG_FILE = 'ComicDBConverter.ini'

# Build datum wordt aangepast tijdens de build
VERSION = "0.2"
BUILD_DATUM = "2024.08.26.1511"

def expand_path(path):
    # Vervang eventuele %AppData% en andere environment variabelen in een pad.
    return os.path.expandvars(path)

def compress_path(path):
    # Vervang delen van het pad met bekende omgevingsvariabelen, zoals %AppData%.
    appdata_path = os.environ.get('APPDATA')
    if appdata_path and path.startswith(appdata_path):
        return path.replace(appdata_path, '%AppData%')
    return path

class MainApp:
    def __init__(self, root):
        self.root = root
        self.width, self.height, self.db_path, self.xml_path, self.x_pos, self.y_pos, self.verbose_bool = self.read_config()

        # Zet venstergrootte en positie
        self.root.geometry(f'{self.width}x{self.height}+{self.x_pos}+{self.y_pos}')
        self.root.title(f"Convert ComicRack DB to YACLibrary  v{VERSION} - {BUILD_DATUM}")

        self.build_ui()


    def read_config(self):
        config = configparser.RawConfigParser()
        config.read(CONFIG_FILE)
        
        width = config.getint('Window', 'width', fallback=800)
        height = config.getint('Window', 'height', fallback=600)
        x_pos = config.getint('Window', 'x_pos', fallback=100)
        y_pos = config.getint('Window', 'y_pos', fallback=100)
        
        db_path = expand_path(config.get('Paths', 'db_path', fallback=''))
        xml_path = expand_path(config.get('Paths', 'xml_path', fallback=''))

        try:
            verbose_bool = config.getboolean('Options', 'show_query', fallback=False)
        except Exception as e:
            verbose_bool = False
        
        return width, height, db_path, xml_path, x_pos, y_pos, verbose_bool

    def save_config(self):
        config = configparser.RawConfigParser()

        # Haal de huidige waarden op uit de config (of standaardwaarden als ze er niet zijn)
        _, _, old_db_path, old_xml_path, _, _, _ = self.read_config()

        # Controleer of er een nieuwe waarde is geselecteerd, anders gebruik de oude
        new_db_path = self.db_path_entry.get() or old_db_path
        new_xml_path = self.xml_path_entry.get() or old_xml_path

        config['Window'] = {
            'width': self.root.winfo_width(),
            'height': self.root.winfo_height(),
            'x_pos': self.root.winfo_x(),
            'y_pos': self.root.winfo_y()
        }

        config['Paths'] = {
            'db_path': compress_path(new_db_path),
            'xml_path': compress_path(new_xml_path)
        }

        config['Options'] = {
            'show_query': self.verbose_var.get()
        }

        with open(CONFIG_FILE, 'w') as configfile:
            config.write(configfile)

    def build_ui(self):
        # Configureer de grid
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(4, weight=1)

        # Variabele voor het bijhouden van de status van het vinkje
        self.overwrite_all = tk.BooleanVar(value=False)

        # Toevoegen van het vinkje aan de interface
        self.overwrite_checkbutton = tk.Checkbutton(self.root, text="Force overwrite all data", variable=self.overwrite_all)
        self.overwrite_checkbutton.grid(row=2, column=0, padx=10, pady=0, sticky="w")

        # Voeg een selectievakje toe voor query update logging
        self.verbose_var = tk.BooleanVar(value=self.verbose_bool)
        self.verbose_checkbutton = tk.Checkbutton(self.root, text="Show Update Queries", variable=self.verbose_var)
        self.verbose_checkbutton.grid(row=2, column=1, padx=10, pady=0, sticky="w")

        # Voeg een selectievakje toe voor debug logging
        self.debug_var = tk.BooleanVar()
        self.debug_checkbutton = tk.Checkbutton(self.root, text="Debug", variable=self.debug_var)
        self.debug_checkbutton.grid(row=2, column=2, padx=20, pady=0, sticky="e")

        # Invoervelden en knoppen
        tk.Label(self.root, text="YAC Database location:").grid(row=0, column=0, padx=10, pady=2, sticky="w")
        self.db_path_entry = tk.Entry(self.root, width=50)
        self.db_path_entry.insert(0, self.db_path)
        self.db_path_entry.grid(row=0, column=1, padx=10, pady=2, sticky="ew")
        tk.Button(self.root, text="Browse...", command=self.browse_db).grid(row=0, column=2, padx=10, pady=2)

        tk.Label(self.root, text="ComicDB.xml location:").grid(row=1, column=0, padx=10, pady=2, sticky="w")
        self.xml_path_entry = tk.Entry(self.root, width=50)
        self.xml_path_entry.insert(0, self.xml_path)
        self.xml_path_entry.grid(row=1, column=1, padx=10, pady=2, sticky="ew")
        tk.Button(self.root, text="Browse...", command=self.browse_xml).grid(row=1, column=2, padx=10, pady=2)

        # De knop in het midden van de layout plaatsen
        button_frame = tk.Frame(self.root)
        button_frame.grid(row=3, column=0, pady=10)

        script_button = tk.Button(button_frame, text="Update YAC with ComicInfo", command=self.run_CRtoYAC_conversion)
        script_button.pack(expand=True)

        # Log tekstvak met scrollbars
        log_frame = tk.Frame(self.root)
        log_frame.grid(row=4, column=0, columnspan=3, padx=10, pady=10, sticky="nsew")

        self.log_text = tk.Text(log_frame, wrap="none")
        self.log_text.grid(row=0, column=0, sticky="nsew")

        log_scroll_y = tk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        log_scroll_y.grid(row=0, column=1, sticky="ns")

        log_scroll_x = tk.Scrollbar(log_frame, orient="horizontal", command=self.log_text.xview)
        log_scroll_x.grid(row=1, column=0, sticky="ew")

        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        self.log_text.config(xscrollcommand=log_scroll_x.set, yscrollcommand=log_scroll_y.set)

        # Voeg een voortgangsbalk toe
        self.progress_bar = ttk.Progressbar(self.root, orient="horizontal", length=400, mode="determinate")
        self.progress_bar.grid(row=3, column=1, columnspan=3, padx=10, pady=10, sticky="ew")

    def run_CRtoYAC_conversion(self):
        db_location = self.db_path_entry.get()
        xml_location = self.xml_path_entry.get()

        try:
            # Als debug is ingeschakeld, zet het logniveau op DEBUG
            if self.debug_var.get():
                log_level = logging.DEBUG
            else:
                log_level = logging.INFO

            # roep de data conversie van ComicInfoDB naar YAC aan
            converter = CRConverter(db_location, xml_location, self.progress_bar, self.log_text, self.overwrite_all, log_level, self.verbose_var.get())
            converter.run()

        except Exception as e:
            messagebox.showerror("Fout", f"There was an error: {e}")

    def browse_db(self):
        # Open een bestandsdialoog voor het selecteren van de database en stel de initiële directory in op basis van de configuratie.
        # Verkrijg de opgeslagen database locatie uit de configuratie
        _, _, saved_db_path, _, _, _, _ = self.read_config()
        initial_dir = os.path.dirname(saved_db_path) if saved_db_path else ''
        
        # Open de dialoog en stel de initiële directory in
        db_path = filedialog.askopenfilename(filetypes=[("SQLite DB", "*.ydb")], initialdir=initial_dir)
        if db_path:
            self.db_path_entry.delete(0, tk.END)
            self.db_path_entry.insert(0, db_path)

    def browse_xml(self):
        # Open een bestandsdialoog voor het selecteren van de XML-bestand en stel de initiële directory in op basis van de configuratie.
        # Verkrijg de opgeslagen XML locatie uit de configuratie
        _, _, _, saved_xml_path, _, _, _ = self.read_config()
        
        initial_dir = os.path.dirname(saved_xml_path) if saved_xml_path else ''
        
        # Open de dialoog en stel de initiële directory in
        xml_path = filedialog.askopenfilename(filetypes=[("XML Files", "*.xml")], initialdir=initial_dir)
        if xml_path:
            self.xml_path_entry.delete(0, tk.END)
            self.xml_path_entry.insert(0, xml_path)

    def on_closing(self):
        self.save_config()
        self.root.destroy()

def main():
    root = tk.Tk()
    app = MainApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()
