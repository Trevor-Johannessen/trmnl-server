import os
import math
from renderObjects import Window
from datetime import datetime, timedelta
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from requests import get
from datetime import datetime

spotify_logo = '<img style="height:100%; margin-right:10px;" src="https://storage.googleapis.com/pr-newsroom-wp/1/2023/05/Spotify_Primary_Logo_RGB_Black.png"/>'

def create_card(album, card_size):
    return f'<img src="{album}" style="width:{card_size}px; height:{card_size}px;">'

def generate_progress_bar():
    curr_song = get("http://192.168.1.106:3340/spotify/getCurrentSong").json()
    length = curr_song['item']['duration_ms']
    progress = curr_song['progress_ms']
    total_minutes = math.ceil(length//1000/60)
    progress_minutes = math.ceil(progress//1000/60)-1
    margin = 30/total_minutes
    bars = ""
    for i in range(0, total_minutes):
        # Filled Bar
        if i<progress_minutes:
            background = "black"
        # Stripped Bar
        elif i==progress_minutes:
            background = "repeating-linear-gradient(45deg,white,white 1px,black 1px,black 2px);"
        # Blank Bar
        else:
            background = "white"
        bar_style = f"background: {background};height:100%;width:{70/total_minutes}%; margin: 0 {margin/2}% 0 {margin/2}%;border: 2px solid; black; border-radius: 5px;"
        bars+=f'<div style="{bar_style}"></div>'
    return f"""
        <div style="height:100%;width:100%;display:flex;flex-direction:row;justify-content: space-around;">
            {bars}
        </div>
    """

def generate_track_collage(tracks):
    cards = []
    # Sizes in px
    largest_card_size = 256
    card_size = largest_card_size
    card_interval = largest_card_size//((len(tracks)+1)//2)
    # Create background cards
    for i in range(math.ceil(len(tracks)//2), 0, -1):
        card_size = card_size - card_interval
        cards.insert(0, create_card(tracks[i-1]['album_art'], card_size))  
        cards.append(create_card(tracks[len(tracks)-i]['album_art'], card_size))
    # If odd number of tracks cretae middle card
    if len(tracks)%2 == 1:
        midpoint = int((len(tracks)-1)/2)
        cards.insert(midpoint, create_card(tracks[midpoint]['album_art'], largest_card_size))

    return "".join(cards)

def parse_song(song):
    name = song['name']
    artists = ", ".join([artist['name'] for artist in song['artists']])
    album_name = song['album']['name']
    album_art = song['album']['images'][0]['url']
    return {"name": name, "artists": artists, "album_name": album_name, "album_art": album_art}

class SpotifyWindow(Window):
    def __init__(self):
        pass

    def render(self):
        tracks = []

        # Get current + surrounding songs
        queue_res = get("http://192.168.1.106:3340/spotify/getQueuedSongs").json()
        curr_track = queue_res['currently_playing']
        if not curr_track:
            return "<h1>No song is currently playing.</h1>"
        curr_track = parse_song(curr_track)
        next_track = queue_res['queue'][0]
        prev_track = get("http://192.168.1.106:3340/spotify/getRecentSongs").json()['items'][0]['track']
        tracks.append(parse_song(prev_track))
        tracks.append(curr_track)
        tracks.append(parse_song(next_track))

        # Generate elementsa
        header = \
f"""
    <div style="height: 32px; display: flex; direction: row;">
        {spotify_logo}
        <h2 style="height:100cqi">Spotify</h2>
        <div style="margin-left: auto;">
            <h3>{datetime.now().strftime("%I:%M %p")}<h3>
        </div>
    </div>
"""
        track_collage = generate_track_collage(tracks)
        progress_bar = generate_progress_bar()
        
        # Generate output HTML
        return f"""
<div style="display: flex; flex-direction: column;">
    {header}
    <div style="text-align: center"><h1>{curr_track['name']}</h1></div>
  <div style="text-align: center;max-height:15%"><h3 style="max-height:100%">{curr_track['artists']}</h3></div>
  <div style="display: flex; justify-content: space-around; margin-top: 10px;">
        {track_collage}
  </div>
  <div style="width:100vw; height: 15vh; display: flex; align-items: center; justify-content: center;">
    <div style="width:65vw;height:20px;">
        {progress_bar}
    </div>
  </div>
</div>
"""
