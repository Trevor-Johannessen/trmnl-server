class Window():
    def __init__(self):
        self.html = f"<h1>Uninitalized {self.__name__} Window</h1>"

    def update(self, data):
        raise Exception(f"Update function not implemented for {self.__name__} Window.")

    def render(self):
        return self.html

class Zone():
    """
        Zones are a way to dynamically create flex-boxes in the HTML. A zone is defined as a single line splitting an abstract space into two smaller parts. A zone has two children, zone_one and zone_two. These continue downward until a leaf is hit, the leaf will be a Window object which can render HTML.
    """
    def __init__(
        self,
        direction: str = None,
        percentage: int = None, 
        zone_one = None,
        zone_two = None,
        window: Window = None
    ):
        if window and (direction or percentage or zone_one or zone_two):
            raise Exception("Zone cannot be given subzones and a Window")
        if bool(direction) ^ bool(percentage):
            raise Exception("If one of direction or percentage is specified, both most be specified")
        if direction not in [None, 'row', 'column']:
            raise Exception(f"Invalid value for direction {direction}. Valid values are 'row' or 'column'")

        self.direction = direction
        self.percentage = percentage
        self.zone_one = zone_one
        self.zone_two = zone_two
        self.window = window

    def update(self, window_type: str, data):
        if self.zone_one:
            self.zone_one.update(window_type, data)
        if self.zone_two:
            self.zone_two.update(window_type, data)
        if self.window and window_type == self.window.__class__.__name__:
            self.window.update(data)

    def render(self):
        if self.window:
            print("Rendering leaf zone")
            return self.window.render()
        print("Rendering child zones.")
        zone_one_content = self.zone_one.render() if self.zone_one else ""
        zone_two_content = self.zone_two.render() if self.zone_two else ""
        html=f"""
            <div style="display:flex; flex-direction:{self.direction}; width:100%; height:100%">
                <div style="flex:0 0 {self.percentage}%">{zone_one_content}</div>
                <div style="height={'100%' if self.direction == 'row' else '2px'}; width={'100%' if self.direction == 'column' else '2px'}; background-color:black"></div>
                <div style="flex: 1">{zone_two_content}</div>
            </div>
        """
        return html

