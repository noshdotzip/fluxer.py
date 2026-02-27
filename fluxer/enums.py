from enum import Enum, IntEnum


class Status(str, Enum):
    online = "online"
    offline = "offline"
    idle = "idle"
    dnd = "dnd"
    invisible = "invisible"


class ChannelType(IntEnum):
    text = 0
    dm = 1
    voice = 2
    group_dm = 3
    category = 4
    announcement = 5
