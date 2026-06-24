from typing import Any, Dict

import requests


CHAN_SONG_URL = "https://chan-song-api.onrender.com/service/data/getChanSong"
DEFAULT_ACCOUNT = "uyen.png"


def get_chan_song(account: str = DEFAULT_ACCOUNT) -> Dict[str, Any]:
    response = requests.post(
        CHAN_SONG_URL,
        json={"ChanSongRequest": {"account": account}},
        timeout=120,
    )
    response.raise_for_status()
    return response.json()
