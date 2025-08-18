from dataclasses import dataclass

@dataclass
class User:
    username: str
    online: bool = False