from renderObjects import Window
from datetime import datetime, timedelta

class ChatbotWindow(Window):
    def __init__(self):
        self.html = ""
        self.last_updated = datetime.now()

    def _formatHTML(self, prompt, response=None):
        response_dialogue = ""
        if response:
            response_dialogue = f"<br><br><h3>Bot Response:</h3><h2>{response}</h2>"
        return f"<div><h3>User asks:</h3><h3>{prompt}</h3>{response_dialogue}</div>"

    def _get_last_user_context(self, data):
        for i in range(-len(data['history']), 0):
            if 'role' in data['history'][i+1] and data['history'][i+1]['role'] == 'user':
                return data['history'][i+1]
        return None

    def update(self, data):
        if not data:
            raise Exception("Chatbot window received no data")
        if 'last_updated' not in data or 'history' not in data:
            raise Exception(f"Chatbot window received malformatted data\n{data}")

        self.last_updated = datetime.strptime(data['last_updated'], "%Y-%m-%d %H:%M:%S")
        if data['history'][-1]['role'] == 'user':
            self.html = self._formatHTML(data['history'][-1]['content'])
        elif self._get_last_user_context(data):
            self.html = self._formatHTML(self._get_last_user_context(data)['content'], data['history'][-1]['content'][0]['text'])
        else:
            print("Error parsing data:")
            print(data)
            self.html = "Error parsing ai context history data." 
    
    def render(self):
        now = datetime.now()
        if now-self.last_updated > timedelta(seconds=60):
            self.html = ""
        return self.html
