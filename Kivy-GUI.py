import os
import re
import shutil
import string
import requests
import discogs_client
import moviepy.editor as mp
from lyricsgenius import Genius
from difflib import get_close_matches as match

from mutagen.id3 import ID3NoHeaderError
from mutagen.id3 import ID3, TIT2, TOFN, TOPE, TPE1, WOAR, TSO2, TPE2, TOAL, TSO2, TSOA, TALB,\
TEXT, TCON, TORY, TYER, TPUB, WPUB, TRCK, APIC, USLT

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.button import Button
from kivy.properties import BooleanProperty, ListProperty, StringProperty, ObjectProperty
from kivy.uix.recyclegridlayout import RecycleGridLayout
from kivy.uix.behaviors import FocusBehavior
from kivy.uix.recycleview.layout import LayoutSelectionBehavior
from kivy.uix.popup import Popup

from tkinter import Tk
from tkinter.filedialog import askopenfilenames


# Discog API Info
header = {"User-Agent": "Mozilla/5.0 (Windows NT 6.1; WOW64; rv:40.0) Gecko/20100101 Firefox/40.1"}
discogs_token = 'DISCOG_TOKEN'
d = discogs_client.Client('LibraryApp/0.1', user_token=discogs_token)
# Genius Lyrics API Info
genius_client_ID = 'GENIUS_ID'
genius_client_secret = 'GENIUS_SECRET'
genius_access_token = 'GENIUS_TOKEN'
genius = Genius(genius_access_token)


def get_lyrics(tags, filename=""):
    song_info = genius.search_song(tags.song, tags.artist)
    if not song_info:
        other_name = filename.lower().replace(tags.artist.lower(), "").replace(" - ", "")
        other_name = string.capwords(other_name)
        song_info = genius.search_song(other_name, tags.artist)
    if not song_info:
        song_info = genius.search_genius(search_term=filename)
        try:
            song_info.lyrics
        except AttributeError:
            return ""
    if not song_info:
        song_info.lyrics = ""
    return song_info.lyrics


def get_file_tags(file, path):
    filename = path + "/" + file + ".mp3"
    default_tags = ID3(filename)
    if default_tags._DictProxy__dict.__len__() < 13:
        tags = ""
        return tags

    tags = MusicFile()
    tags.file = filename
    tags.song = default_tags["TIT2"].text[0]
    tags.artist = default_tags["TOPE"].text[0]
    tags.album_artist = default_tags["TPE2"].text[0]
    tags.album = default_tags["TALB"].text[0]
    tags.album_cover = default_tags.getall("APIC")[0].data
    tags.genres = default_tags["TCON"].text[0]
    tags.year = default_tags.getall("TDOR")[0].text[0].text
    tags.lyrics = default_tags.getall("USLT")[0].text
    tags.track_number = default_tags["TRCK"].text[0]
    return tags


def set_file_tags(filename, tags):
    try:
        default_tags = ID3(filename)
    except ID3NoHeaderError:
        # Adding ID3 header
        default_tags = ID3()

    # Tag Breakdown
    # Track: TIT2
    # OG Filename: TOFN # Artist - Song Title.MP3
    # Artist: TOPE, TPE1, WOAR(official), TSO2(itunes), TPE2(band)
    # Lyrics: TEXT
    # Album: TOAL(original), TSO2(itunes), TSOA(sort), TALB
    # Genres: TCON
    # Year: TORY(release), TYER(record)
    # Publisher: TPUB, WPUB(info)

    default_tags["TOFN"] = TOFN(encoding=3, text=os.path.split(filename[0])[1])  # Original Filename
    default_tags["TIT2"] = TIT2(encoding=3, text=tags.song)  # Title
    default_tags["TRCK"] = TRCK(encoding=3, text=tags.track_number)  # Track Number

    # Artist tags
    default_tags["TOPE"] = TOPE(encoding=3, text=tags.artist)  # Original Artist/Performer
    default_tags["TPE1"] = TPE1(encoding=3, text=tags.artist)  # Lead Artist/Performer/Soloist/Group
    default_tags["TPE2"] = TPE2(encoding=3, text=tags.album_artist)  # Band/Orchestra/Accompaniment

    # Album tags
    default_tags["TOAL"] = TOAL(encoding=3, text=tags.album)  # Original Album
    default_tags["TALB"] = TALB(encoding=3, text=tags.album)  # Album Name
    default_tags["TSO2"] = TSO2(encoding=3, text=tags.album)  # iTunes Album Artist Sort
    # tags["TSOA"] = TSOA(encoding=3, text=tags.album[0]) # Album Sort Order key

    default_tags["TCON"] = TCON(encoding=3, text=tags.genres)  # Genre
    default_tags["TDOR"] = TORY(encoding=3, text=str(tags.year))  # Original Release Year
    default_tags["TDRC"] = TYER(encoding=3, text=str(tags.year))  # Year of recording
    default_tags["USLT"] = USLT(encoding=3, text=tags.lyrics)  # Lyrics
    default_tags.save(v2_version=3)

    # Album Cover
    if type(tags.album_cover) == str:
        r = requests.get(tags.album_cover, stream=True)
        r.raise_for_status()
        r.raw.decode_content = True
        with open('img.jpg', 'wb') as out_file:
            shutil.copyfileobj(r.raw, out_file)
        del r

        with open('img.jpg', 'rb') as albumart:
            default_tags.add(APIC(
                              encoding=3,
                              mime="image/jpg",
                              type=3, desc='Cover',
                              data=albumart.read()))
    elif type(tags.album_cover) == bytes:
        default_tags.add(APIC(
                                encoding=3,
                                mime="image/jpg",
                                type=3, desc='Cover',
                                data=tags.album_cover))
    default_tags.save(v2_version=3)


def convert2mp3(filename, path):
    fullpath = os.path.join(path, filename)
    clip = mp.AudioFileClip(fullpath)  # disable if do not want any clipping
    clip.write_audiofile(path)


def find_master(disc_search):
    try:
        master = next(i.master.main_release for i in disc_search if i.master)
    except AttributeError:
        try:
            master = next(i.main_release for i in disc_search if i.main_release)
        except AttributeError:
            try:
                master = next(i.master.main_release for i in disc_search if i.data_quality == "Correct")
            except AttributeError:
                try:
                    master = next(i.main_release for i in disc_search if i.data_quality == "Correct")
                except AttributeError:
                    # no results
                    master = []
    return master


def searchDisc(track_name="", artist="", album="", filename="", search_type="song"):
    music = MusicFile()
    if search_type == "file":
        disc_search = d.search(query=filename)
        # if no search results, return empty
        if not len(disc_search) > 0: return music
        master = find_master(disc_search)
        if not master: return music

        # Check if artist name is duplicate, ie. Artist(2), Artist(3) etc
        multi_check = re.search("\([0-9]\)", master.artists[0].name)
        if multi_check:
            start = multi_check.regs[0][0]
            end = multi_check.regs[0][1]
            multi_str = master.artists[0].name[start:end]
            pos_artist = master.artists[0].name.replace(multi_str, "").rstrip()
        else:
            pos_artist = master.artists[0].name

        pos_track = re.sub(pos_artist, "", filename).replace("- ", "").lstrip()
        pos_track = string.capwords(pos_track)
        try:
            track = next(i for i in master.tracklist if i.title.lower() == pos_track.lower())
            if track:
                music.song = track.title
                music.track_number = track.position
            else:
                music.song = pos_track
        except StopIteration:
            music.song = match(pos_track, [i.title for i in master.tracklist], cutoff=0.4)[0]
            # music.song = string.capwords(music.song)  # capitalize words in string
            music.track_number = next(i.position for i in master.tracklist if i.title == music.song)
        try:
            # Check if track number is for vinyl or cd
            int(music.track_number)
        except ValueError:
            # If track number is for vinyl, grab integer
            music.track_number = [ind for ind, i in enumerate(master.tracklist, 1)
                                  if i.position == music.track_number][0]
            music.track_number = str(music.track_number)  # convert to string

    elif search_type == "song":
        if album:
            disc_search = d.search(track=track_name, artist=artist, release_title=album)
        else:
            disc_search = d.search(track=track_name, artist=artist)
        # if no search results, return empty
        if not len(disc_search) > 0: return music
        master = find_master(disc_search)
        if not master: return music

        music.song = match(track_name, [i.title for i in master.tracklist], cutoff=0.4)[0]
        music.track_number = next(i.position for i in master.tracklist if i.title == music.song)
    elif search_type == "album":
        disc_search = d.search(album, type="Release", artist=artist)
        # if no search results, return empty
        if not len(disc_search) > 0: return music
        master = find_master(disc_search)
        if not master: return music

    music.artist = master.artists[0].name
    music.album_artist = master.artists[0].name
    music.album = master.title
    music.album_tracks = [s.title for s in master.tracklist]

    if master.genres and master.styles:
        music.genres = master.genres + master.styles
    elif master.genres:
        music.genres = master.genres
    elif master.styles:
        music.genres = master.styles

    music.year = master.year
    music.album_cover = master.images[0]['uri']
    music.lyrics = get_lyrics(music, filename=filename)

    # self.test_fun(music)
    return music


class MusicFile():
    def __init__(self, *args, **kwargs):
        self.file = ""
        self.song = ""
        self.artist = ""
        self.album_artist = ""
        self.album = ""
        self.album_tracks = ""
        self.track_number = ""
        self.genres = ""
        self.year = ""
        self.album_cover = ""
        self.lyrics = ""


class TextInputPopup(Popup):
    obj = ObjectProperty(None)
    obj_text = StringProperty("")

    def __init__(self, obj, **kwargs):
        super(TextInputPopup, self).__init__(**kwargs)
        self.obj = obj
        self.obj_text = obj.text


class SearchInputPopup(Popup):
    searchq = ObjectProperty(None)
    song = ObjectProperty(None)
    artist = ObjectProperty(None)
    album = ObjectProperty(None)
    check_state = BooleanProperty(False)

    def album_chkbx(self, value):
        self.check_state = value
        # print("Checkbox State: ", self.check_state, ", ", value)  # Check

    def search_btn(self):
        # print(self.check_state.text)
        if self.check_state.active or not self.song.text: flag = "album"
        else: flag = "song"

        self.searchq = searchDisc(track_name=self.song.text, artist=self.artist.text, album=self.album.text, search_type=flag)


class TagPopup(Popup):
    # TextInput variables
    tag_song = ObjectProperty(None)
    tag_artist = ObjectProperty(None)
    tag_albumartist = ObjectProperty(None)
    tag_album = ObjectProperty(None)
    tag_genres = ObjectProperty(None)
    tag_year = ObjectProperty(None)
    tag_lyrics = ObjectProperty(None)

    def __init__(self, **kwargs):
        super(TagPopup, self).__init__(**kwargs)
        tags = App.get_running_app().tags
        # fill text input boxes with tags from discogs
        self.tag_song.text = tags.song
        self.tag_artist.text = tags.artist
        self.tag_albumartist.text = tags.album_artist
        self.tag_album.text = tags.album
        self.tag_genres.text = ", ".join(tags.genres) if type(tags.genres) == list else tags.genres
        self.tag_year.text = str(tags.year)
        self.tag_lyrics.text = tags.lyrics

    def update_tags(self):
        tags = App.get_running_app().tags
        # update tags with updated text inputs
        tags.song = self.tag_song.text
        tags.artist = self.tag_artist.text
        tags.album_artist = self.tag_albumartist.text
        tags.album = self.tag_album.text
        tags.genres = list(self.tag_genres.text.split(" "))
        tags.year = int(self.tag_year.text)
        tags.lyrics = self.tag_lyrics.text
        set_file_tags(filename=tags.file, tags=tags)


class SelectableRecycleGridLayout(FocusBehavior, LayoutSelectionBehavior,
                                  RecycleGridLayout):
    ''' Adds selection and focus behaviour to the view. '''


class SelectableButton(RecycleDataViewBehavior, Button):
    ''' Add selection support to the Button '''
    index = None
    selected = BooleanProperty(False)
    selectable = BooleanProperty(True)

    def refresh_view_attrs(self, rv, index, data):
        ''' Catch and handle the view changes '''
        self.index = index
        return super(SelectableButton, self).refresh_view_attrs(rv, index, data)

    def on_touch_down(self, touch):
        ''' Add selection on touch down '''
        if super(SelectableButton, self).on_touch_down(touch):
            return True
        if self.collide_point(*touch.pos) and self.selectable:
            return self.parent.select_with_touch(self.index, touch)

    def apply_selection(self, rv, index, is_selected):
        ''' Respond to the selection of items in the view. '''
        self.selected = is_selected

    def on_release(self):
        popup = TextInputPopup(self)
        popup.open()

    def update_changes(self, txt):
        self.text = txt


class RV(BoxLayout):
    data_items = ListProperty([])
    filepath = StringProperty("")

    def __init__(self, **kwargs):
        super(RV, self).__init__(**kwargs)

    def search_popup_btn(self):
        popup = SearchInputPopup()
        popup.open()

    def load_btn(self):
        pass
        Tk().withdraw()
        filepaths = askopenfilenames(filetypes=[("Audio files", ".mp3 .wav .wma .flac"), ("All Files", "*.*")],
                                     title="Select Your Music")
        if not filepaths:
            return
        self.filepath = os.path.split(filepaths[0])[0]  # return only path
        filenames = [os.path.split(filepath)[1].split(".")[0] for filepath in filepaths]  # create list of filenames
        self.data_items = filenames  # save list of filenames in global variable

    def tag_func(self, tag_type=""):
        app = App.get_running_app()
        for file in self.data_items:
            tags = get_file_tags(file=file, path=self.filepath)
            if tags != "":
                # If file already has tags
                app.tags = tags
                if tag_type == "single":
                    # Display tags for editing/approving
                    tag_popup = TagPopup()
                    tag_popup.open()
            else:
                # else search tags
                app.tags = searchDisc(filename=file, search_type="file")  # Search Discogs for tags
                app.tags.file = self.filepath + "/" + file + ".mp3"
                if tag_type == "single":
                    # Display tags for editing/approving
                    tag_popup = TagPopup()
                    tag_popup.open()

                set_file_tags(filename=app.tags.file, tags=app.tags)  # Update tags


class TaggerApp(App):
    title = "Music Tagger"
    tags = MusicFile()

    def build(self):
        return RV()


if __name__ == "__main__":
    TaggerApp().run()