from renderObjects import Zone
from state import State

class ScreenController():
    def __init__(self, root_zone: Zone = None):
        self.root_zone = root_zone
        self.state = State.ROTATE

    def render(self):
        if self.root_zone:
            return self.root_zone.render()
        return "No root zone provided to controller"

    def update(self, window_name, data):
                        
        if self.root_zone:
            self.root_zone.update(window_name, data)

