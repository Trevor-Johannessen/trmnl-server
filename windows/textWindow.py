from renderObjects import Window

class TextWindow(Window):
    def __init__(self, text="Default text", type="h1", weight="normal"):
        self.type = type
        self.text=text
        self.weight=weight
    
    def update(self, data):
        pass
    
    def render(self):
        return f'<{self.type} style="font-weight:{self.weight}">{self.text}</{self.type}>'
