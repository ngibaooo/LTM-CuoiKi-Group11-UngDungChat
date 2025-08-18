from typing import Optional, Tuple
from .storage import Storage

class SearchService:
    def __init__(self, storage: Storage):
        self.storage = storage

    def search(self, peer_type: Optional[str], peer_id: Optional[str], keyword: Optional[str], ts_range: Optional[Tuple[int,int]]):
        return self.storage.search(peer_type, peer_id, keyword, ts_range)