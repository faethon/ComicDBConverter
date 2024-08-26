import sqlite3
import os
import xml.etree.ElementTree as ET
import logging
import tkinter as tk  # Zorg ervoor dat tk wordt geïmporteerd

UPDATE_ALTIJD = 'UPDATE_ALTIJD'
UPDATE_INDIEN_LEEG = 'UPDATE_INDIEN_LEEG'
UPDATE_ALS_GEWIJZIGD = 'UPDATE_ALS_GEWIJZID'

def normalize_path(path):
    return os.path.normcase(os.path.normpath(path)).replace("\\", "/")

def remove_hidden_characters(text):
    return text.encode('ascii', 'ignore').decode('ascii')

def combine_query_and_values(query, values):
    # Vervangt de vraagtekens in de SQL-query door de corresponderende waarden uit de values-lijst.
    for value in values:
        # Als de waarde een string is, zet deze tussen aanhalingstekens
        if isinstance(value, str):
            value = f"'{value}'"
        elif value is None:
            value = 'NULL'
        else:
            value = str(value)
        
        # Vervang het eerste vraagteken door de geformatteerde waarde
        query = query.replace('?', value, 1)
    return query

class GUIHandler(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

        self.text_widget.configure(state='disabled')
        self.text_widget.tag_config('DEBUG', foreground='blue')
        self.text_widget.tag_config('INFO', foreground='green')
        self.text_widget.tag_config('WARNING', foreground='orange')
        self.text_widget.tag_config('ERROR', foreground='red')
        self.text_widget.tag_config('CRITICAL', foreground='magenta')
        self.text_widget.tag_config('BOLD', font=('Helvetica', 10, 'bold'))

    def emit(self, record):
        msg = self.format(record)
        self.text_widget.configure(state='normal')
        tag = record.levelname
        self.text_widget.insert(tk.END, msg + '\n', (tag, 'BOLD'))
        self.text_widget.configure(state='disabled')
        self.text_widget.yview(tk.END)

class CRConverter:
    # lookup tabel, True: update alleen als leeg, False: altijd updaten.
    LOOKUP_TABLE = {
        'Title': ('Title', UPDATE_ALS_GEWIJZIGD),
        'Series': ('Series', UPDATE_ALS_GEWIJZIGD),
        'Volume': ('Volume', UPDATE_ALS_GEWIJZIGD),
        'Number': ('Number', UPDATE_ALS_GEWIJZIGD),
        'Writer': ('Writer', UPDATE_ALS_GEWIJZIGD),
        'Penciller': ('Penciller', UPDATE_ALS_GEWIJZIGD),
        'Inker': ('Inker', UPDATE_ALS_GEWIJZIGD),
        'Publisher': ('Publisher', UPDATE_ALS_GEWIJZIGD),
        'Imprint': ('Imprint', UPDATE_ALS_GEWIJZIGD),
        'CurrentPage': ('CurrentPage', UPDATE_INDIEN_LEEG),
        'Read': ('Read', UPDATE_INDIEN_LEEG),    # schrijf de READ status alleen weg als de comic in ComicRack volledig is gelezen
        'Year': ('Date', UPDATE_ALS_GEWIJZIGD)
    }

    def __init__(self, db_location, xml_location, progress_bar=None, log_text=None, overwrite_all=None, log_level=logging.INFO, verbose=False):
        self.db_location = db_location
        self.xml_location = xml_location
        self.conn = None
        self.root = None
        self.progress_bar = progress_bar
        self.log_text = log_text
        self.overwrite_all = overwrite_all
        self.log_level = log_level
        self.verbose = verbose
        self.number_updated = 0
        self.number_missing = 0
        self.number_nochange = 0

        # Setup logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)

        # check of er niet al een handler is geinstalleerd
        if not self.logger.handlers:
            gui_handler = GUIHandler(log_text)
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            gui_handler.setFormatter(formatter)
            self.logger.addHandler(gui_handler)

        # zet logging level
        self.logger.setLevel(self.log_level)


    def connect_to_db(self):
        try:
            self.conn = sqlite3.connect(self.db_location)
            self.logger.info("Connected to the YAC database.")
        except sqlite3.Error as e:
            self.logger.error(f"Error while connecting to YAC database: {e}")

    def parse_xml(self):
        try:
            tree = ET.parse(self.xml_location)
            self.root = tree.getroot()
            self.logger.info("ComicRack XML file parsed succesfully.")
        except ET.ParseError as e:
            self.logger.error(f"Error while parsing XML file: {e}")


    def find_book_by_file(self, file_name):
        normalized_file_name = remove_hidden_characters(normalize_path(file_name))
        for book in self.root.find('Books').findall('Book'):
            book_file = remove_hidden_characters(normalize_path(book.get('File')))
            if normalized_file_name in book_file:
                return book
        self.logger.debug(f"Did not find XML book entry for {file_name}")
        return None

    def construct_date(self, book):
        # Construeert een datumstring uit de jaar-, maand- en dagvelden.
        # Begin met een lege datumstring
        date_str = None

        year = book.find('Year').text if book.find('Year') is not None else None
        if year is not None:
            date_str = year
            month = book.find('Month').text if book.find('Month') is not None else None
            if month is not None:
                date_str = f"{month}-{date_str}"
                day = book.find('Day').text if book.find('Day') is not None else None
                if day:
                    date_str = f"{day}-{date_str}"

        return date_str

    def update_comic_info(self, comic_id, book, path):
        cursor = self.conn.cursor()
        update_query = "UPDATE comic_info SET "
        update_values = []
        fields_to_update = []

        for xml_field, (sql_field, update_flag) in self.LOOKUP_TABLE.items():

            self.logger.debug(f"\t\tParsing xml_field: {xml_field}")

            # bepaal xml_value, verwerk eerst speciale cases van xml_field
            if xml_field == 'Read':
                last_page_read = book.find('LastPageRead').text if book.find('LastPageRead') is not None else None
                page_count = book.find('PageCount').text if book.find('PageCount') is not None else None
                if last_page_read is not None and page_count is not None:
                    if int(page_count) - int(last_page_read) < 2:
                        xml_value = 1
                    else:
                        xml_value = 0

                    self.logger.debug(f"\t\t\t\tRead status: {last_page_read}/{page_count}, xml_value = {xml_value}")
                else:
                    continue

            elif xml_field == 'Year':
                xml_value = self.construct_date(book)
                self.logger.debug(f"\t\t\t\tDate constructed: {xml_value}")
            else:
                xml_value = book.find(xml_field).text if book.find(xml_field) is not None else None

            # er is een xml_value bepaald voor het betreffende xml_field. 
            if xml_value:
                # Gebruik de overwrite_all variabele om te bepalen of altijd geüpdatet moet worden (uitgezonderd 'CurrentPage')
                if xml_field != 'CurrentPage' and (self.overwrite_all.get() or update_flag == UPDATE_ALTIJD):
                    fields_to_update.append(f"{sql_field} = ?")
                    update_values.append(xml_value)
                else:
                    cursor.execute(f"SELECT {sql_field} FROM comic_info WHERE Id = ?", (comic_id,))
                    current_value = cursor.fetchone()

                    self.logger.debug(f"\t\t\t\tCurrent value in DB: {sql_field} = {current_value}")

                    if (update_flag == UPDATE_INDIEN_LEEG or update_flag == UPDATE_ALS_GEWIJZIGD) and (current_value is None or current_value[0] is None or current_value[0] == '' or current_value[0] == 0):
                        self.logger.debug(f"\t\t\t\tCurrent value is empty, add to  update query: {sql_field} = {xml_value}")
                        fields_to_update.append(f"{sql_field} = ?")
                        update_values.append(xml_value)
                    elif update_flag == UPDATE_ALS_GEWIJZIGD and (current_value[0] != xml_value):
                        self.logger.debug(f"\t\t\t\tCurrent value {current_value} is changed, add to update query: {sql_field} = {xml_value}")
                        fields_to_update.append(f"{sql_field} = ?")
                        update_values.append(xml_value)

        if fields_to_update:
            update_query += ", ".join(fields_to_update)
            update_query += " WHERE Id = ?"
            update_values.append(comic_id)

            if self.verbose is True:
                query = combine_query_and_values(update_query, update_values)
                self.logger.info(f"QUERY: {query}")
            elif self.verbose is False and self.log_level is logging.DEBUG:
                self.logger.debug(f"\t\tUPDATE of DB: {update_query} met {update_values}")

            try:
                cursor.execute(update_query, tuple(update_values))
                self.conn.commit()
                self.number_updated += 1
            except sqlite3.Error as e:
                self.logger.error(f"Error while updating the YAC database: {e}")
        else:
            self.logger.debug(f"\t\tUPDATE: No values found for update of Id: {comic_id} at ({path})")
            self.number_nochange += 1

    def process_comics(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT ComicInfoId, Path FROM comic")
        comics = cursor.fetchall()

        total_comics = len(comics)
        self.logger.info(f"Processing {total_comics} comics...")
        self.progress_bar['value'] = 0
        self.progress_bar['maximum'] = total_comics
        self.number_updated = 0
        self.number_missing = 0
        self.number_nochange = 0

        for index, (comic_id, path) in enumerate(comics):
            book = self.find_book_by_file(path)

            if book is not None:
                xmlbook = book.attrib['File']
                self.logger.debug(f"MATCH:  DB path: {path}, met Id {comic_id:>8} --- XML File: {xmlbook}")
                self.update_comic_info(comic_id, book, path)
            else:
                self.logger.warning(f"No ComicRack info found for ComicInfoId {comic_id:>8}: {path}")
                self.number_missing += 1

            # Update de voortgangsbalk
            self.progress_bar['value'] = index + 1
            self.progress_bar.update()

        self.logger.info(f"Processing {total_comics} comics completed; {self.number_nochange} unchanged, {self.number_updated} updated, and {self.number_missing} not found ComicRack info.")

    def run(self):
        self.connect_to_db()
        self.parse_xml()
       
        if not self.conn or not self.root:
            return

        self.process_comics()
        self.conn.close()
