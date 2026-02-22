from renderObjects import Window, Zone
from windows.textWindow import TextWindow
from windows.chatbotWindow import ChatbotWindow
from windows.spotifyWindow import SpotifyWindow

"""
init_screen = Zone(
    direction='row',
    percentage=50,
    zone_one=Zone(window=ChatbotWindow()),
    zone_two=Zone(window=(TextWindow("I'm on the right!")))
)
"""
init_screen = SpotifyWindow()
