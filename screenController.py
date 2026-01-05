from renderObjects import Zone

class ScreenController():
    def __init__(self, root_zone: Zone = None):
        self.root_zone = root_zone

    def render(self):
        if self.root_zone:
            return self.root_zone.render()
        return "No root zone provided to controller"

    def update(self, window_name, data):
        if self.root_zone:
            self.root_zone.update(window_name, data)
