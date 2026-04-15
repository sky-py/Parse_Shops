import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_PATH = 'c:/Quad Solutions/files/2_ price'


def get_env(var: str) -> str:
    value = os.getenv(var)
    if value is None:
        raise ValueError(f'Environment variable {var} is not set')
    return value


load_dotenv(BASE_DIR / '.env')

PROXY_HOST = get_env('PROXY_HOST')
PROXY_PORT = int(get_env('PROXY_PORT'))
PROXY_USERNAME = get_env('PROXY_USERNAME')
PROXY_PASSWORD = get_env('PROXY_PASSWORD')
