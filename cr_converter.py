import sqlite3
import os
import xml.etree.ElementTree as ET
import logging
import tkinter as tk  # Make sure tk is imported

UPDATE_ALTIJD = 'UPDATE_ALTIJD'
UPDATE_INDIEN_LEEG = 'UPDATE_INDIEN_LEEG'
UPDATE_ALS_GEWIJZIGD = 'UPDATE_ALS_GEWIJZID'

def normalize_path(path):
    return os.path.normcase(os.path.normpath(path)).replace("\\", "/")

def remove_hidden_characters(text):
    return text.encode('ascii', 'ignore').decode('ascii')

def combine_query_and_values(query, values):
    # Replaces the question marks in the SQL query with the corresponding values ​​from the values ​​list.
    for value in values:
        # If the value is a string, enclose it in quotes
        if isinstance(value, str):
            value = f"'{value}'"
        elif value is None:
            value = 'NULL'
        else:
            value = str(value)
        
        # Replace the first question mark with the formatted value
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
    # lookup table, True: update only if empty, False: always update.
    LOOKUP_TABLE = {
        'Title': ('Title', UPDATE_ALS_GEWIJZIGD),
        'Series': ('Series', UPDATE_ALS_GEWIJZIGD),
        'Volume': ('Volume', UPDATE_ALS_GEWIJZIGD),
        'Number': ('Number', UPDATE_ALS_GEWIJZIGD),
        'StoryArc': ('StoryArc', UPDATE_ALS_GEWIJZIGD),
        'Genre': ('Genere', UPDATE_ALS_GEWIJZIGD),
        'Writer': ('Writer', UPDATE_ALS_GEWIJZIGD),
        'Penciller': ('Penciller', UPDATE_ALS_GEWIJZIGD),
        'Inker': ('Inker', UPDATE_ALS_GEWIJZIGD),
        'Colorist': ('Colorist', UPDATE_ALS_GEWIJZIGD),
        'Letterer': ('Letterer', UPDATE_ALS_GEWIJZIGD),
        'CoverArtist': ('CoverArtist', UPDATE_ALS_GEWIJZIGD),
        'Editor': ('Editor', UPDATE_ALS_GEWIJZIGD),
        'Publisher': ('Publisher', UPDATE_ALS_GEWIJZIGD),
        'Imprint': ('Imprint', UPDATE_ALS_GEWIJZIGD),
        'Format': ('Format', UPDATE_ALS_GEWIJZIGD),
        'AgeRating': ('AgeRating', UPDATE_ALS_GEWIJZIGD),
        'Characters': ('Characters', UPDATE_ALS_GEWIJZIGD),
        'Teams': ('Teams', UPDATE_ALS_GEWIJZIGD),
        'MainCharacterOrTeam': ('MainCharacterOrTeam', UPDATE_ALS_GEWIJZIGD),
        'Locations': ('Locations', UPDATE_ALS_GEWIJZIGD),
        'SeriesGroup': ('SeriesGroup', UPDATE_ALS_GEWIJZIGD),
        'AlternateSeries': ('AlternateSeries', UPDATE_ALS_GEWIJZIGD),
        'AlternateNumber': ('AlternateNumber', UPDATE_ALS_GEWIJZIGD),
        'AlternateCount': ('AlternateCount', UPDATE_ALS_GEWIJZIGD),
        'Summary': ('Synopsis', UPDATE_ALS_GEWIJZIGD),
        'Notes': ('Notes', UPDATE_ALS_GEWIJZIGD),
        'Review': ('Review', UPDATE_ALS_GEWIJZIGD),
        'Tags': ('Tags', UPDATE_ALS_GEWIJZIGD),
        'LanguageISO': ('LanguageISO', UPDATE_ALS_GEWIJZIGD),
        'AgeRating': ('AgeRating', UPDATE_ALS_GEWIJZIGD),
        'Rating': ('Rating', UPDATE_ALS_GEWIJZIGD),
        'Manga': ('Manga', UPDATE_ALS_GEWIJZIGD),
        'CurrentPage': ('CurrentPage', UPDATE_INDIEN_LEEG),
        'Read': ('Read', UPDATE_INDIEN_LEEG),  # Only write the READ status when the comic in ComicRack has been completely read.
        'Year': ('Date', UPDATE_ALS_GEWIJZIGD)
    }

    def __init__(self, db_location, xml_location, progress_bar=None, log_text=None, overwrite_all=None, log_level=logging.INFO, verbose=False, syncread=False):
        self.db_location = db_location
        self.xml_location = xml_location
        self.conn = None
        self.root = None
        self.tree = None
        self.progress_bar = progress_bar
        self.log_text = log_text
        self.overwrite_all = overwrite_all
        self.log_level = log_level
        self.verbose = verbose
        self.syncread = syncread
        self.number_updated = 0
        self.number_missing = 0
        self.number_nochange = 0
        self.number_syncread = 0

        # Setup logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)

        # check if a handler is already installed
        if not self.logger.handlers:
            gui_handler = GUIHandler(log_text)
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            gui_handler.setFormatter(formatter)
            self.logger.addHandler(gui_handler)

        # set logging level
        self.logger.setLevel(self.log_level)


    def connect_to_db(self):
        try:
            self.conn = sqlite3.connect(self.db_location)
            cursor = self.conn.cursor()
            cursor.execute("SELECT ComicInfoId, Path FROM comic")
            comics = cursor.fetchall()
            total_comics = len(comics)
            self.logger.info(f"Connected to the YAC database, contains {total_comics} comics.")
        except sqlite3.Error as e:
            self.logger.error(f"Error while connecting to YAC database: {e}")

    def parse_xml(self):
        try:
            self.tree = ET.parse(self.xml_location)
            self.root = self.tree.getroot()
            total_comics = len(self.tree.findall('.//Book'))
            self.logger.info(f"ComicRack XML file parsed succesfully, contains {total_comics} comics.")
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

    def _get_int_tag(self, book, tag):
        """Helper: Reads an XML tag as int; returns None if missing/invalid."""
        elem = book.find(tag)
        if elem is None or elem.text is None or elem.text.strip() == "":
            return None
        try:
            return int(elem.text)
        except ValueError:
            return None

    def construct_date(self, book):
        """
        Combine Day/Month/Year from ComicDB.xml into YACReader format: D.M.YYYY.
        - No leading zeros (e.g. 01 -> 1)
        - Day and/or Month may be missing
        """
        year = self._get_int_tag(book, 'Year')
        if year is None:
            return None
        month = self._get_int_tag(book, 'Month')
        day = self._get_int_tag(book, 'Day')

        parts = []
        if day:
            parts.append(str(day))   # D
        if month:
            parts.append(str(month)) # M
        parts.append(str(year))      # YYYY
        return ".".join(parts)

    def extract_comicvine_id(self, book):
        """
        Searches <Tags> for a token 'CVDB<digits>' (case-insensitive) and
        returns the number as int, or None if not found/invalid.
        Examples that match:
          - 'CVDB132453'
          - 'Action, cvdb98765, Classic'
        """
        import re
        tags_el = book.find('Tags')
        if tags_el is None or tags_el.text is None:
            return None
        text = tags_el.text.strip()
        if not text:
            return None
        m = re.search(r'\bCVDB\s*[-_:]*\s*(\d+)\b', text, flags=re.IGNORECASE)
        if not m:
            return None
        try:
            return int(m.group(1))
        except ValueError:
            return None

    def update_comic_info(self, comic_id, book, path):
        cursor = self.conn.cursor()
        update_query = "UPDATE comic_info SET "
        update_values = []
        fields_to_update = []

        for xml_field, (sql_field, update_flag) in self.LOOKUP_TABLE.items():

            self.logger.debug(f"\t\tParsing xml_field: {xml_field}")

            # determine xml_value, first handle special cases of xml_field
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
            # Special case: when processing 'Tags', also try to extract ComicVineID from Tags.
            extra_field = None
            extra_value = None
            if xml_field == 'Tags':
                cv_id = self.extract_comicvine_id(book)
                if cv_id is not None:
                    extra_field = 'ComicVineID'
                    extra_value = str(cv_id)
                    self.logger.debug(f"\t\t\t\tComicVineID extracted from Tags: {extra_value}")
            # an xml_value has been specified for the xml_field in question.
            if xml_value is not None and xml_value != "":
                # Use the overwrite_all variable to determine whether to always update (except 'CurrentPage')
                if xml_field != 'CurrentPage' and (self.overwrite_all.get() or update_flag == UPDATE_ALTIJD):
                    fields_to_update.append(f"{sql_field} = ?")
                    update_values.append(xml_value)
                else:
                    cursor.execute(f"SELECT {sql_field} FROM comic_info WHERE Id = ?", (comic_id,))
                    current_value = cursor.fetchone()

                    self.logger.debug(f"\t\t\t\tCurrent value in DB: {sql_field} = {current_value}")

                    if (update_flag == UPDATE_INDIEN_LEEG or update_flag == UPDATE_ALS_GEWIJZIGD) and (current_value is None or current_value[0] is None or current_value[0] == '' or current_value[0] == 0):
                        self.logger.debug(f"\t\t\t\tCurrent value is empty, add to update query: {sql_field} = {xml_value}")
                        fields_to_update.append(f"{sql_field} = ?")
                        update_values.append(xml_value)
                    elif update_flag == UPDATE_ALS_GEWIJZIGD and (current_value[0] != xml_value):
                        self.logger.debug(f"\t\t\t\tCurrent value {current_value} is changed, add to update query: {sql_field} = {xml_value}")
                        fields_to_update.append(f"{sql_field} = ?")
                        update_values.append(xml_value)

            if extra_field is not None:
                if self.overwrite_all.get():
                    # Force overwrite enabled: always update ComicVineID
                    self.logger.debug(f"\t\t\t\tForce overwrite ON: set {extra_field} = {extra_value}")
                    fields_to_update.append(f"{extra_field} = ?")
                    update_values.append(extra_value)
                else:
                    # Empty-or-changed behavior (mirror UPDATE_ALS_GEWIJZIGD) with string normalization
                    cursor.execute(f"SELECT {extra_field} FROM comic_info WHERE Id = ?", (comic_id,))
                    current_value = cursor.fetchone()
                    current_str = "" if current_value is None or current_value[0] is None else str(current_value[0]).strip()
                    self.logger.debug(f"\t\t\t\tCurrent value in DB: {extra_field} = {current_str!r}")
                    if current_str == "" or current_str == "0":
                        self.logger.debug(f"\t\t\t\t{extra_field} empty -> set to {extra_value}")
                        fields_to_update.append(f"{extra_field} = ?")
                        update_values.append(extra_value)
                    elif current_str != extra_value:
                        self.logger.debug(f"\t\t\t\t{extra_field} changed ({current_str} -> {extra_value}) -> update")
                        fields_to_update.append(f"{extra_field} = ?")
                        update_values.append(extra_value)

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

    def sync_read_status(self, comic_id, book, path):
        # read the 'Read' value in YAC
        cursor = self.conn.cursor()
        cursor.execute(f"SELECT read FROM comic_info WHERE Id = ?", (comic_id,))
        current_value = cursor.fetchone()

        if current_value is not None and current_value[0] == 1:
            # check whether the status in ComicRack is not Read
            last_page_read = book.find('LastPageRead').text if book.find('LastPageRead') is not None else None
            page_count = book.find('PageCount').text if book.find('PageCount') is not None else None

            if last_page_read is None or (page_count is not None and int(page_count)-int(last_page_read) > 1):
                self.logger.debug(f"READ in YAC, but ComicDB.XML page {last_page_read}/{page_count}: Update XML file for comic_id {comic_id}")

                if last_page_read is not None:
                    # update existing field
                    book.find('LastPageRead').text = str(int(page_count)-1)
                    self.number_syncread += 1
                else:
                    # Add the field if it doesn't exist
                    new_last_page_read = ET.SubElement(book, 'LastPageRead')
                    new_last_page_read.text = str(page_count)
                    self.number_syncread += 1

                self.logger.info(F"SYNC Read status in ComicRack DB for {path}")
                self.tree.write(self.xml_location, encoding='utf-8', xml_declaration=True)

    def process_comics(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT ComicInfoId, Path FROM comic")
        comics = cursor.fetchall()

        total_comics = len(comics)
        self.logger.info(f"Processing all {total_comics} comics from YAC...")
        self.progress_bar['value'] = 0
        self.progress_bar['maximum'] = total_comics
        self.number_updated = 0
        self.number_missing = 0
        self.number_nochange = 0
        self.number_syncread = 0

        for index, (comic_id, path) in enumerate(comics):
            book = self.find_book_by_file(path)

            if book is not None:
                xmlbook = book.attrib['File']
                self.logger.debug(f"MATCH: DB path: {path}, met Id {comic_id:>8} --- XML File: {xmlbook}")
                self.update_comic_info(comic_id, book, path)
                
                # sync read status to ComicRack if the option is enabled
                if self.syncread:
                    self.sync_read_status(comic_id, book, path)

            else:
                self.logger.warning(f"No ComicRack info found for ComicInfoId {comic_id:>8}: {path}")
                self.number_missing += 1

            # Update the progress bar
            self.progress_bar['value'] = index + 1
            self.progress_bar.update()

        self.logger.info(f"Processing {total_comics} comics completed; {self.number_nochange} unchanged, {self.number_updated} updated, and {self.number_missing} no ComicRack info found.")
        if self.syncread:
            self.logger.info(f"Synchronized read status for {self.number_syncread} comics in ComicRack.")
        self.logger.info("All done!")

    def run(self):
        self.connect_to_db()
        self.parse_xml()
       
        if not self.conn or not self.root:
            return

        self.process_comics()
        self.conn.close()
