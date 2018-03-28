import sys
import os
from os.path import dirname, abspath, basename

from onyx.skills.media import MediaSkill
from adapt.intent import IntentBuilder
from onyx.messagebus.message import Message

import time
import threading

import requests

from onyx.util.log import getLogger

sys.path.append(abspath(dirname(__file__)))
Mopidy = __import__('mopidypost').Mopidy

logger = getLogger(abspath(__file__).split('/')[-2])
__author__ = 'forslund'


class MopidySkill(MediaSkill):
    def __init__(self):
        super(MopidySkill, self).__init__('Mopidy Skill')
        self.volume_is_low = False

    def at_run(self):
        def launch_mopidy():
            os.system('mopidy')
        t = threading.Thread(target=launch_mopidy)
        t.start()

    def install(self):
        def launch_mopidy_install():
            os.system('wget -q -O - https://apt.mopidy.com/mopidy.gpg | sudo apt-key add -')
            os.system('sudo wget -q -O /etc/apt/sources.list.d/mopidy.list https://apt.mopidy.com/jessie.list')
            os.system('sudo apt-get -y update')
            os.system('sudo apt-get install -y mopidy mopidy-spotify')
        t = threading.Thread(target=launch_mopidy_install)
        t.start()

    def _connect(self, message):
        url = "http://localhost:6680"
        try:
            self.mopidy = Mopidy(url)
        except:
            logger.info('Could not connect to server, retrying in 10 sec')
            time.sleep(10)
            self.emitter.emit(Message(self.name + '.connect'))
            return

        self.albums = {}
        self.artists = {}
        self.genres = {}
        self.playlists = {}
        self.radios = {}

        logger.info('Loading content')
        self.albums['gmusic'] = self.mopidy.get_gmusic_albums()
        self.artists['gmusic'] = self.mopidy.get_gmusic_artists()
        self.genres['gmusic'] = self.mopidy.get_gmusic_radio()
        self.playlists['gmusic'] = {}

        self.albums['local'] = self.mopidy.get_local_albums()
        self.artists['local'] = self.mopidy.get_local_artists()
        self.genres['local'] = self.mopidy.get_local_genres()
        self.playlists['local'] = self.mopidy.get_local_playlists()

        self.albums['spotify'] = {}
        self.artists['spotify'] = {}
        self.genres['spotify'] = {}
        self.playlists['spotify'] = self.mopidy.get_spotify_playlists()

        self.playlist = {}
        for loc in ['local', 'gmusic', 'spotify']:
            logger.info(loc)
            self.playlist.update(self.playlists[loc])
            logger.info(loc)
            self.playlist.update(self.genres[loc])
            logger.info(loc)
            self.playlist.update(self.artists[loc])
            logger.info(loc)
            self.playlist.update(self.albums[loc])

        self.register_vocabulary(self.name, 'NameKeyword')
        for p in self.playlist.keys():
            logger.debug("Playlist: " + p)
            self.register_vocabulary(p, 'PlaylistKeyword' + self.name)
        intent = IntentBuilder('PlayPlaylistIntent' + self.name)\
            .require('PlayKeyword')\
            .require('PlaylistKeyword' + self.name)\
            .build()
        self.register_intent(intent, self.handle_play_playlist)
        intent = IntentBuilder('PlayFromIntent' + self.name)\
            .require('PlayKeyword')\
            .require('PlaylistKeyword')\
            .require('NameKeyword')\
            .build()
        self.register_intent(intent, self.handle_play_playlist)

        self.register_regex("for (?P<Source>.*)")
        intent = IntentBuilder('SearchSpotifyIntent' + self.name)\
            .require('SearchKeyword')\
            .optionally('Source')\
            .require('SpotifyKeyword')\
            .build()
        self.register_intent(intent, self.search_spotify)

    def initialize(self):
        logger.info('initializing Mopidy skill')
        super(MopidySkill, self).initialize()
        self.load_data_files(dirname(__file__))

        self.emitter.on(self.name + '.connect', self._connect)
        self.emitter.emit(Message(self.name + '.connect'))

    def play(self, tracks):
        self.mopidy.clear_list()
        self.mopidy.add_list(tracks)
        self.mopidy.play()

    def handle_play_playlist(self, message):
        p = message.data.get('PlaylistKeyword' + self.name)
        self.before_play()
        self.speak("Playing " + str(p), self.lang)
        time.sleep(3)
        if self.playlist[p]['type'] == 'playlist':
            tracks = self.mopidy.get_items(self.playlist[p]['uri'])
        else:
            tracks = self.mopidy.get_tracks(self.playlist[p]['uri'])
        self.play(tracks)

    def stop(self, message=None):
        logger.info('Handling stop request')
        self.mopidy.clear_list()
        self.mopidy.stop()

    def handle_next(self, message):
        self.mopidy.next()

    def handle_prev(self, message):
        self.mopidy.previous()

    def handle_pause(self, message):
        self.mopidy.pause()

    def handle_play(self, message):
        """Resume playback if paused"""
        self.mopidy.resume()

    def lower_volume(self, message):
        logger.info('lowering volume')
        self.mopidy.lower_volume()
        self.volume_is_low = True

    def restore_volume(self, message):
        logger.info('maybe restoring volume')
        self.volume_is_low = False
        time.sleep(2)
        if not self.volume_is_low:
            logger.info('restoring volume')
            self.mopidy.restore_volume()

    def handle_currently_playing(self, message):
        current_track = self.mopidy.currently_playing()
        if current_track is not None:
            self.mopidy.lower_volume()
            time.sleep(1)
            if 'album' in current_track:
                data = {'current_track': current_track['name'],
                        'artist': current_track['album']['artists'][0]['name']}
                self.speak_dialog('currently_playing', data)
            time.sleep(6)
            self.mopidy.restore_volume()

    def search_spotify(self, message):
        logger.info('Search Spotify Intent')
        logger.info(message.metadata)
        name = message.data['Source']
        logger.info(name)
        results = self.mopidy.find_album(name, 'spotify')
        if len(results) > 0:
            tracks = results[0]
        if results is not None:
            logger.info(results)
            self.play(results[0]['uri'])


def create_skill():
    return MopidySkill()
