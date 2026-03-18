class SessionStore:
    def __init__(self):
        self.store = {}
    
    def save(self, session_id: str, params: dict):
        self.store[session_id] = params
    
    def get(self, session_id: str) -> dict:
        return self.store.get(session_id, {})